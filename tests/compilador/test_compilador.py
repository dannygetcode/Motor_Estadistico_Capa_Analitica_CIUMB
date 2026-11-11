"""Compilador spec -> SQL: lista blanca, parámetros, razones, agregados, instantáneas, alcance y huella."""

from __future__ import annotations

import re
from datetime import date

import pandas as pd
import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.dialects import postgresql

from ciumb_analitica.compilador.compilador import (
    COL_REGISTRO,
    ErrorCompilacion,
    LimiteFilasExcedido,
    compilar,
    ejecutar,
    huella_datos,
)
from ciumb_analitica.dw import esquema as dw
from ciumb_analitica.dw.tiempo import sk_fecha
from ciumb_analitica.semantica.semilla import capa_semilla
from ciumb_analitica.spec.modelos import DimensionSpec
from ciumb_analitica.spec.resultado import Estado
from ciumb_analitica.spec.validador import validar
from tests.compilador.conftest import SAL
from tests.conftest import IDS_PROMPTS, fixture_prompt

CAPA = capa_semilla()
HOY = date(2026, 11, 5)
ULTIMO_CORTE = sk_fecha(date(2026, 10, 31))
COMPILABLES = [n for n in IDS_PROMPTS if n != "p10"]
INYECCION = "Ingeniería'; DROP TABLE ana_.hecho_proyecto; --"


def _resolver(spec: dict):
    resultado = validar(spec, CAPA, hoy=HOY)
    assert resultado.estado is Estado.VALIDA, resultado.problemas
    return resultado.spec


def _plan(spec: dict, **kw):
    return compilar(_resolver(spec), CAPA, **kw)


def _spec(**cambios) -> dict:
    base = {
        "esquema": "ciumb.spec/1.0",
        "origen": "prompt",
        "metricas": [{"id": "proyectos"}],
        "dimensiones": [{"id": "facultad"}],
        "periodo": {"desde": "2026-01-01", "hasta": "2026-10-31"},
        "analisis": {"metodo": "frecuencias"},
        "alcance": {"rol": "directivo"},
    }
    return {k: v for k, v in (base | cambios).items() if v is not None}


def _correr(bd, spec: dict, **kw) -> dict[str, pd.DataFrame]:
    plan = _plan(spec, **kw)
    with bd.connect() as con:
        return ejecutar(con, plan)


def _proyectos_al_corte(tablas, corte=ULTIMO_CORTE) -> pd.DataFrame:
    p = tablas["hecho_proyecto"]
    return p[p["sk_fecha_corte"] == corte].merge(tablas["dim_linea_programa"], on="sk_linea")


# --- Determinismo y huella (invariante 6) --------------------------------------------------------------------


@pytest.mark.parametrize("nombre", COMPILABLES)
def test_misma_spec_mismo_sql_misma_huella(nombre):
    spec = fixture_prompt(nombre)["spec"]
    a = _plan(spec)
    b = _plan(dict(reversed(list(spec.items()))))  # otro orden de claves en el JSON
    assert [c.sql for c in a.consultas] == [c.sql for c in b.consultas]
    assert [c.parametros for c in a.consultas] == [c.parametros for c in b.consultas]
    assert a.huella == b.huella and re.fullmatch(r"[0-9a-f]{64}", a.huella)


def test_huellas_distintas_para_specs_distintas():
    huellas = {_plan(fixture_prompt(n)["spec"]).huella for n in COMPILABLES}
    assert len(huellas) == len(COMPILABLES)


def test_cambiar_un_valor_cambia_la_huella_pero_no_el_sql():
    a = _plan(_spec(filtros=[{"campo": "estado", "op": "=", "valor": "en_ejecucion"}]))
    b = _plan(_spec(filtros=[{"campo": "estado", "op": "=", "valor": "finalizado"}]))
    assert a.consultas[0].sql == b.consultas[0].sql
    assert a.consultas[0].parametros != b.consultas[0].parametros and a.huella != b.huella


def test_el_alcance_entra_en_la_huella():
    directivo = _plan(_spec())
    coordinador = _plan(_spec(alcance={"rol": "coordinador", "facultad": "Ingeniería"}))
    otro = _plan(_spec(alcance={"rol": "coordinador", "facultad": "Ciencias Sociales"}))
    assert len({directivo.huella, coordinador.huella, otro.huella}) == 3


def test_la_fecha_de_referencia_no_cambia_el_sql_con_periodo_explicito():
    spec = _spec()
    a = compilar(validar(spec, CAPA, hoy=date(2026, 11, 5)).spec, CAPA)
    b = compilar(validar(spec, CAPA, hoy=date(2026, 12, 20)).spec, CAPA)
    assert a.huella == b.huella


# --- Lista blanca y parámetros (invariante 2) ----------------------------------------------------------------


@pytest.mark.parametrize("nombre", COMPILABLES)
def test_solo_select_sobre_ana_con_identificadores_de_la_lista_blanca(nombre):
    plan = _plan(fixture_prompt(nombre)["spec"])
    permitidas = {t.name for t in dw.metadatos_ana.tables.values()}
    for c in plan.consultas:
        assert c.sql.lstrip().upper().startswith("SELECT")
        assert not re.search(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|GRANT|TRUNCATE)\b", c.sql, re.I)
        assert ";" not in c.sql and "--" not in c.sql and "rpt_" not in c.sql
        tablas = set(re.findall(r"ana_\.(\w+)", c.sql))
        assert tablas and tablas <= permitidas
        assert set(re.findall(r" AS (\w+) JOIN| AS (\w+) ON", c.sql)) <= {("cortes", ""), ("", "cortes_tiempo")}
        assert "LIMIT" in c.sql.upper()


@pytest.mark.parametrize("nombre", COMPILABLES)
def test_ningun_valor_de_la_spec_aparece_en_el_sql(nombre):
    spec = fixture_prompt(nombre)["spec"]
    plan = _plan(spec)
    for c in plan.consultas:
        assert "'" not in c.sql  # ningún literal de texto
        assert not re.search(r"\b20(19|2\d)\b", c.sql)  # ni fechas ni años
        for f in spec.get("filtros", []):
            assert str(f["valor"]) not in c.sql
        if "facultad" in spec["alcance"]:
            assert spec["alcance"]["facultad"] not in c.sql
            assert spec["alcance"]["facultad"] in c.parametros.values()
        assert all(re.fullmatch(r"p\d+(_\d+)?", nombre_p) for nombre_p in c.parametros)


@pytest.mark.parametrize(
    "filtro",
    [
        {"campo": "facultad", "op": "=", "valor": INYECCION},
        {"campo": "facultad", "op": "!=", "valor": "x' OR '1'='1"},
        {"campo": "facultad", "op": "en", "valor": ["Ingeniería", "a') OR 1=1 --"]},
        {"campo": "estado", "op": "=", "valor": '"; SELECT seudonimo FROM ana_.dim_persona_rol; --'},
        {"campo": "programa", "op": "=", "valor": "x' UNION SELECT nombre FROM ana_.dim_macroproyecto --"},
        {"campo": "periodo_academico", "op": "=", "valor": "2026-2' OR 1=1; --"},
    ],
    ids=lambda f: f["campo"] + "-" + f["op"],
)
def test_inyeccion_desde_filtros_queda_en_parametros(bd, filtro):
    plan = _plan(_spec(filtros=[filtro]))
    consulta = plan.consultas[0]
    valores = filtro["valor"] if isinstance(filtro["valor"], list) else [filtro["valor"]]
    for v in valores:
        assert v not in consulta.sql
        assert v in consulta.parametros.values()
    assert "DROP" not in consulta.sql and "UNION" not in consulta.sql and "'" not in consulta.sql
    with bd.connect() as con:
        resultado = ejecutar(con, plan)["principal"]
        intacto = con.scalar(select(func.count()).select_from(dw.hecho_proyecto))
    assert intacto == 41  # 5 proyectos en 2025 + 9 en cada uno de los 4 cortes de 2026
    if filtro["op"] == "!=":
        assert resultado["proyectos"].sum() == 9  # el texto se compara como dato: nadie se llama así
    elif filtro["op"] == "en":
        assert resultado["facultad"].tolist() == ["Ingeniería"]
    else:
        assert resultado.empty
    assert set(inspect(bd).get_table_names()) >= {"hecho_proyecto", "dim_persona_rol"}


def test_inyeccion_desde_el_alcance_queda_en_parametros(bd):
    plan = _plan(_spec(alcance={"rol": "coordinador", "facultad": INYECCION}))
    assert INYECCION not in plan.consultas[0].sql and INYECCION in plan.consultas[0].parametros.values()
    with bd.connect() as con:
        assert ejecutar(con, plan)["principal"].empty


@pytest.mark.parametrize(
    "falsa",
    ["usuario", "facultad; DROP TABLE x", "dim_persona_rol.seudonimo", "contrasena_hash", "estudiante", "persona"],
)
def test_una_spec_resuelta_forjada_no_compila(falsa):
    """Aunque alguien salte el validador, el compilador solo acepta códigos de la capa semántica sin personas."""
    spec = _resolver(_spec())
    forjada = spec.model_copy(update={"dimensiones": (DimensionSpec.model_construct(id=falsa, granularidad=None),)})
    with pytest.raises(ErrorCompilacion):
        compilar(forjada, CAPA)
    filtro = spec.filtros + (type("F", (), {"campo": falsa, "op": None, "valor": 1})(),)
    with pytest.raises(ErrorCompilacion):
        compilar(spec.model_copy(update={"filtros": filtro}), CAPA)
    metrica = spec.metricas[0].model_copy(update={"id": falsa})
    with pytest.raises(ErrorCompilacion):
        compilar(spec.model_copy(update={"metricas": (metrica,)}), CAPA)


@pytest.mark.parametrize("nombre", COMPILABLES)
def test_el_sql_tambien_compila_en_postgresql(nombre):
    for c in _plan(fixture_prompt(nombre)["spec"]).consultas:
        texto = str(c.sentencia.compile(dialect=postgresql.dialect()))
        assert texto.startswith("SELECT") and "ana_." in texto and re.search(r"%\(p\d+\)s", texto)


# --- Agregados precalculados -------------------------------------------------------------------------------------


def test_p1_prefiere_el_agregado_y_coincide_con_el_hecho_base(bd, tablas):
    plan = _plan(fixture_prompt("p01")["spec"])
    consulta = plan.consulta("principal")
    assert consulta.tabla == "agg_proyecto_linea_mes" and consulta.usa_agregado
    assert "hecho_proyecto" not in consulta.sql
    with bd.connect() as con:
        obtenido = ejecutar(con, plan)["principal"]
    estados = {1: "en_ejecucion", 2: "finalizado"}
    base = _proyectos_al_corte(tablas).assign(estado=lambda d: d["sk_estado"].map(estados))
    esperado = base.groupby(["estado", "facultad"]).size().reset_index(name="proyectos")
    pd.testing.assert_frame_equal(obtenido, esperado, check_dtype=False)
    assert obtenido["proyectos"].sum() == 9  # el último corte, no la suma de todos los cortes


def test_sin_agregado_cuando_no_cubre_la_dimension_o_la_agregacion():
    por_macro = _plan(_spec(dimensiones=[{"id": "macroproyecto"}]))
    assert por_macro.consultas[0].tabla == "hecho_proyecto" and not por_macro.consultas[0].usa_agregado
    promedio = _plan(_spec(metricas=[{"id": "presupuesto_ejecutado", "agregacion": "promedio"}]))
    assert promedio.consultas[0].tabla == "hecho_proyecto"
    suma = _plan(_spec(metricas=[{"id": "presupuesto_ejecutado", "agregacion": "suma"}]))
    assert suma.consultas[0].tabla == "agg_proyecto_linea_mes"
    registro = _plan(_spec(metricas=[{"id": "presupuesto_ejecutado"}], analisis={"metodo": "descriptiva"}))
    assert registro.consultas[0].tabla == "hecho_proyecto"


def test_p3_facturacion_mensual_desde_el_agregado(bd, tablas):
    obtenido = _correr(bd, fixture_prompt("p03")["spec"])["principal"]
    assert obtenido.columns.tolist() == ["tiempo_anio", "tiempo_mes", "facturacion"]
    assert len(obtenido) == 22  # enero de 2025 a octubre de 2026
    f = tablas["agg_facturacion_mes"]
    esperado = f.groupby("sk_fecha")["valor_facturado"].sum().tolist()
    assert obtenido["facturacion"].tolist() == pytest.approx(esperado)
    assert obtenido[["tiempo_anio", "tiempo_mes"]].iloc[[0, -1]].values.tolist() == [[2025, 1], [2026, 10]]


# --- Razones: se recalculan desde sus componentes ----------------------------------------------------------------


def test_p4_razon_recalculada_por_celda_y_ultimo_corte_de_cada_trimestre(bd, tablas):
    obtenido = _correr(bd, fixture_prompt("p04")["spec"])["principal"]
    assert obtenido.columns.tolist() == [
        "facultad", "tiempo_anio", "tiempo_trimestre",
        "pct_hitos_atrasados", "pct_hitos_atrasados__num", "pct_hitos_atrasados__den",
    ]  # fmt: skip
    # T1 y T2 de 2026 no tienen cortes cargados; T3 usa el corte del 30 de septiembre (no julio ni agosto).
    assert obtenido["tiempo_trimestre"].unique().tolist() == [3]
    base = _proyectos_al_corte(tablas, sk_fecha(date(2026, 9, 30)))
    esperado = base.groupby("facultad")[["n_hitos_atrasados", "n_hitos"]].sum()
    for fila in obtenido.itertuples():
        num, den = esperado.loc[fila.facultad]
        assert (fila.pct_hitos_atrasados__num, fila.pct_hitos_atrasados__den) == (num, den)
        assert fila.pct_hitos_atrasados == pytest.approx(100 * num / den)
    # No es el promedio de los porcentajes de cada proyecto.
    promedio_de_razones = (100 * base["n_hitos_atrasados"] / base["n_hitos"]).groupby(base["facultad"]).mean()
    assert not obtenido.set_index("facultad")["pct_hitos_atrasados"].sub(promedio_de_razones).abs().lt(1e-9).all()


def test_p4_consulta_de_prueba_agrupa_por_las_variables_no_por_las_dimensiones(bd, tablas):
    plan = _plan(fixture_prompt("p04")["spec"])
    assert [c.nombre for c in plan.consultas] == ["principal", "prueba"]
    prueba = plan.consulta("prueba")
    assert prueba.columnas == (
        "facultad",
        "pct_hitos_atrasados",
        "pct_hitos_atrasados__num",
        "pct_hitos_atrasados__den",
    )
    with bd.connect() as con:
        tabla = ejecutar(con, plan)["prueba"]
    base = _proyectos_al_corte(tablas, sk_fecha(date(2026, 9, 30)))
    esperado = base.groupby("facultad")[["n_hitos_atrasados", "n_hitos"]].sum()
    assert tabla["pct_hitos_atrasados__num"].tolist() == esperado["n_hitos_atrasados"].tolist()
    assert tabla["pct_hitos_atrasados__den"].tolist() == esperado["n_hitos"].tolist()


def test_chi_cuadrado_de_dos_dimensiones_usa_el_conteo(bd):
    spec = _spec(analisis={"metodo": "chi_cuadrado", "variables": ["facultad", "estado"]})
    resultados = _correr(bd, spec)
    assert resultados["prueba"].columns.tolist() == ["facultad", "estado", "proyectos"]
    assert resultados["prueba"]["proyectos"].sum() == 9
    assert resultados["principal"].columns.tolist() == ["facultad", "proyectos"]


def test_razon_total_sin_dimensiones_y_division_por_cero(bd, tablas):
    total = _correr(bd, _spec(metricas=[{"id": "pct_ejecucion"}], dimensiones=[]))["principal"]
    base = _proyectos_al_corte(tablas)
    assert total["pct_ejecucion"].iloc[0] == pytest.approx(
        100 * base["presupuesto_ejecutado"].sum() / base["presupuesto_asignado"].sum()
    )
    vacio = _spec(metricas=[{"id": "pct_tareas_cumplidas"}], dimensiones=[],
                  filtros=[{"campo": "programa", "op": "=", "valor": "No existe"}])  # fmt: skip
    assert pd.isna(_correr(bd, vacio)["principal"]["pct_tareas_cumplidas"].iloc[0])  # NULLIF: sin error


def test_razon_con_denominador_de_filas(bd, tablas):
    obtenido = _correr(bd, _spec(metricas=[{"id": "pct_practicas_finalizadas"}], dimensiones=[{"id": "programa"}]))
    p = tablas["hecho_practica"].merge(tablas["dim_linea_programa"], on="sk_linea")
    esperado = p.groupby("programa")["finalizada"].agg(["sum", "count"])
    fila = obtenido["principal"].set_index("programa")
    for programa, (num, den) in esperado.iterrows():
        assert fila.loc[programa, "pct_practicas_finalizadas"] == pytest.approx(100 * num / den)
        assert fila.loc[programa, "pct_practicas_finalizadas__den"] == den


# --- Instantáneas periódicas -------------------------------------------------------------------------------------


def test_p9_serie_mensual_toma_el_corte_de_cada_mes(bd, tablas):
    obtenido = _correr(bd, fixture_prompt("p09")["spec"])["principal"]
    p = tablas["hecho_proyecto"]
    esperado = p[p["sk_fecha_corte"] > 20260000].groupby("sk_fecha_corte")["presupuesto_ejecutado"].sum()
    assert obtenido["tiempo_mes"].tolist() == [7, 8, 9, 10]
    assert obtenido["presupuesto_ejecutado"].tolist() == pytest.approx(esperado.tolist())


def test_una_medida_de_instantanea_no_se_suma_entre_cortes(bd, tablas):
    spec = _spec(metricas=[{"id": "presupuesto_ejecutado", "agregacion": "suma"}], dimensiones=[],
                 periodo={"desde": "2025-01-01", "hasta": "2026-10-31"})  # fmt: skip
    total = _correr(bd, spec)["principal"]["presupuesto_ejecutado"].iloc[0]
    p = tablas["hecho_proyecto"]
    assert total == pytest.approx(p[p["sk_fecha_corte"] == ULTIMO_CORTE]["presupuesto_ejecutado"].sum())
    assert total < p["presupuesto_ejecutado"].sum()


def test_el_periodo_define_cual_es_el_ultimo_corte(bd, tablas):
    spec = _spec(dimensiones=[], periodo={"desde": "2025-01-01", "hasta": "2025-12-31"})
    assert _correr(bd, spec)["principal"]["proyectos"].iloc[0] == 5
    anual = _spec(dimensiones=[{"id": "tiempo", "granularidad": "anio"}],
                  periodo={"desde": "2025-01-01", "hasta": "2026-10-31"})  # fmt: skip
    assert _correr(bd, anual)["principal"].values.tolist() == [[2025, 5], [2026, 9]]


def test_filtro_temporal_sin_periodo_acota_el_corte(bd):
    spec = _spec(dimensiones=[], periodo=None, filtros=[{"campo": "anio", "op": "=", "valor": 2025}])
    assert _resolver(spec).periodo is None
    assert _correr(bd, spec)["principal"]["proyectos"].iloc[0] == 5


# --- Alcance del rol (RF-21) -------------------------------------------------------------------------------------


def test_p2_coordinador_solo_ve_su_facultad_y_cuenta_personas(bd, tablas):
    plan = _plan(fixture_prompt("p02")["spec"])
    consulta = plan.consulta("principal")
    assert consulta.columnas == ("programa", "practicas", "_n_personas")
    assert "Ingeniería" in consulta.parametros.values() and "2026-2" in consulta.parametros.values()
    with bd.connect() as con:
        obtenido = ejecutar(con, plan)["principal"]
    p = tablas["hecho_practica"].merge(tablas["dim_linea_programa"], on="sk_linea")
    p = p[(p["facultad"] == "Ingeniería") & (p["sk_fecha"] >= 20260701) & (p["sk_fecha"] <= ULTIMO_CORTE)]
    esperado = p.groupby("programa").agg(practicas=("id_practica", "count"), n=("seudonimo_estudiante", "nunique"))
    assert (
        obtenido["programa"].tolist() == esperado.index.tolist() == ["Ingeniería Electrónica", "Ingeniería de Software"]
    )
    assert obtenido["practicas"].tolist() == esperado["practicas"].tolist()
    assert obtenido["_n_personas"].tolist() == esperado["n"].tolist()
    software = obtenido.set_index("programa").loc["Ingeniería de Software"]
    assert software["_n_personas"] == software["practicas"] - 1  # dos prácticas de la misma persona


def test_el_tutor_solo_ve_sus_practicas(bd, tablas):
    spec = _spec(metricas=[{"id": "practicas"}], dimensiones=[], alcance={"rol": "tutor", "id_usuario": 412})
    plan = _plan(spec, sal=SAL)
    consulta = plan.consultas[0]
    assert 412 not in consulta.parametros.values() and "412" not in consulta.sql
    assert any(isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v) for v in consulta.parametros.values())
    with bd.connect() as con:
        propias = ejecutar(con, plan)["principal"]["practicas"].iloc[0]
        otro = spec | {"alcance": {"rol": "tutor", "id_usuario": 413}}
        ajenas = ejecutar(con, _plan(otro, sal=SAL))["principal"]["practicas"].iloc[0]
        desconocido = spec | {"alcance": {"rol": "tutor", "id_usuario": 999}}
        nadie = ejecutar(con, _plan(desconocido, sal=SAL))["principal"]["practicas"].iloc[0]
    p = tablas["hecho_practica"]
    assert propias == (p["sk_persona"] == 1).sum() and ajenas == (p["sk_persona"] == 2).sum()
    assert propias + ajenas == len(p) and nadie == 0


def test_sin_sal_no_se_compila_un_alcance_personal():
    spec = _spec(metricas=[{"id": "practicas"}], dimensiones=[], alcance={"rol": "tutor", "id_usuario": 412})
    with pytest.raises(ErrorCompilacion, match="sal"):
        _plan(spec)


def test_el_compilador_tambien_niega_un_hecho_fuera_del_rol():
    spec = _resolver(_spec(metricas=[{"id": "practicas"}], dimensiones=[], alcance={"rol": "tutor", "id_usuario": 412}))
    forjada = spec.model_copy(update={"metricas": (spec.metricas[0].model_copy(update={"id": "proyectos"}),)})
    with pytest.raises(ErrorCompilacion, match="rol"):
        compilar(forjada, CAPA, sal=SAL)


def test_el_coordinador_no_alcanza_un_hecho_sin_facultad():
    spec = _resolver(_spec(alcance={"rol": "coordinador", "facultad": "Ingeniería"}))
    forjada = spec.model_copy(
        update={"metricas": (spec.metricas[0].model_copy(update={"id": "consultorias"}),), "dimensiones": ()}
    )
    with pytest.raises(ErrorCompilacion, match="matriz de bus"):
        compilar(forjada, CAPA)


# --- Nivel registro ----------------------------------------------------------------------------------------------


def test_p5_dos_metricas_registro_a_registro(bd, tablas):
    plan = _plan(fixture_prompt("p05")["spec"])
    assert plan.consultas[0].columnas == ("n_consultores", "satisfaccion", COL_REGISTRO)
    with bd.connect() as con:
        obtenido = ejecutar(con, plan)["principal"]
    c = tablas["hecho_consultoria"].sort_values(["sk_fecha", "id_consultoria"])
    assert obtenido[COL_REGISTRO].tolist() == c["id_consultoria"].tolist()
    assert obtenido["satisfaccion"].tolist() == c["satisfaccion"].tolist()
    assert "GROUP BY" not in plan.consultas[0].sql


def test_p6_razon_por_proyecto_en_el_ultimo_corte_con_filtro_y_alcance(bd, tablas):
    obtenido = _correr(bd, fixture_prompt("p06")["spec"])["principal"]
    base = _proyectos_al_corte(tablas)
    base = base[(base["linea_investigacion"] == "Analítica de datos") & (base["facultad"] == "Ingeniería")]
    assert obtenido[COL_REGISTRO].tolist() == base["id_proyecto"].tolist() == [1, 4, 7]
    esperado = 100 * base["presupuesto_ejecutado"] / base["presupuesto_asignado"]
    assert obtenido["pct_ejecucion"].tolist() == pytest.approx(esperado.tolist())
    assert obtenido["pct_ejecucion__den"].tolist() == base["presupuesto_asignado"].tolist()


def test_t_student_agrega_la_variable_de_grupo_a_cada_registro(bd):
    spec = _spec(metricas=[{"id": "satisfaccion"}], dimensiones=[],
                 analisis={"metodo": "t_student", "variables": ["satisfaccion", "sector"]})  # fmt: skip
    obtenido = _correr(bd, spec)["principal"]
    assert obtenido.columns.tolist() == ["sector", "satisfaccion", COL_REGISTRO]
    assert len(obtenido) == 12 and set(obtenido["sector"]) == {"Tecnología", "Salud", "Educación"}


def test_metricas_de_personas_llevan_el_seudonimo_solo_como_columna_auxiliar(bd):
    spec = _spec(metricas=[{"id": "duracion_practica"}], dimensiones=[{"id": "programa"}],
                 analisis={"metodo": "descriptiva"})  # fmt: skip
    obtenido = _correr(bd, spec)["principal"]
    assert obtenido.columns.tolist() == ["programa", "duracion_practica", COL_REGISTRO, "_persona"]


# --- Varias tablas, límite y huella de datos -----------------------------------------------------------------


def test_p8_una_consulta_por_hecho_unidas_por_empresa(bd, tablas):
    plan = _plan(fixture_prompt("p08")["spec"])
    assert [c.nombre for c in plan.consultas] == [
        "principal:hecho_practica", "principal:hecho_convenio", "principal:hecho_consultoria",
    ]  # fmt: skip
    assert len(plan.principales) == 3
    with bd.connect() as con:
        r = ejecutar(con, plan)
    assert r["principal:hecho_practica"].columns.tolist() == ["empresa", "practicas", "_n_personas"]
    assert r["principal:hecho_convenio"]["convenios"].sum() == 7
    c = tablas["hecho_consultoria"]
    esperado = c[c["sk_fecha"] <= ULTIMO_CORTE].groupby("sk_empresa").size()
    assert r["principal:hecho_consultoria"]["consultorias"].tolist() == esperado.tolist()


def test_p7_serie_semestral(bd, tablas):
    obtenido = _correr(bd, fixture_prompt("p07")["spec"])["principal"]
    assert obtenido.columns.tolist() == ["tiempo_anio", "tiempo_semestre", "practicas", "_n_personas"]
    assert obtenido.values.tolist() == [[2026, 1, 8, 8]]  # el periodo llega hasta junio de 2026


def test_limite_de_filas(bd):
    spec = _spec(dimensiones=[{"id": "linea_investigacion"}])
    with bd.connect() as con:
        assert len(ejecutar(con, _plan(spec, limite_filas=3))["principal"]) == 3
        with pytest.raises(LimiteFilasExcedido):
            ejecutar(con, _plan(spec, limite_filas=2))


def test_huella_de_datos_estable_y_sensible(bd):
    spec = fixture_prompt("p01")["spec"]
    a, b = _correr(bd, spec), _correr(bd, spec)
    assert huella_datos(a) == huella_datos(b) and re.fullmatch(r"[0-9a-f]{64}", huella_datos(a))
    b["principal"].loc[0, "proyectos"] += 1
    assert huella_datos(a) != huella_datos(b)


def test_sql_texto_para_trazabilidad():
    texto = _plan(fixture_prompt("p04")["spec"]).sql_texto()
    assert "-- principal" in texto and "-- prueba" in texto and "-- parametros:" in texto
