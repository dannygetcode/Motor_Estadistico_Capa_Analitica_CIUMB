"""ETL de punta a punta (sección 4.3.2, OE4): fuente sintética -> `ana_`, en SQLite.

La fuente se crea con las tablas de la lista blanca de `fuentes.vistas` (solo columnas que el ETL puede leer) y se
llena con `datos_sinteticos.generar` (semilla fija, defectos con conteos exactos). El destino es `ana_` completo.
En PostgreSQL se corre igual con `uv run python -m ciumb_analitica.etl` (ver docs/handoff.md).
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, insert, inspect, select, update
from sqlalchemy.pool import StaticPool

from ciumb_analitica.dw import esquema as dw
from ciumb_analitica.etl import calidad, carga
from ciumb_analitica.fuentes import vistas
from datos_sinteticos.generar import CATALOGO_ESTADOS, FECHA_CORTE, generar

SAL = "sal-de-prueba-etl-1234567890"
HOY = date(2026, 11, 5)
CORTE = date(2026, 10, 31)
DATOS = generar()


def _origen():
    motor = create_engine("sqlite://", poolclass=StaticPool).execution_options(
        schema_translate_map={vistas.ESQUEMA_FUENTE: None}
    )
    vistas.metadatos_fuente.create_all(motor)
    with motor.begin() as con:
        for tabla in vistas.metadatos_fuente.sorted_tables:
            columnas = {c.name for c in tabla.columns}
            con.execute(
                insert(tabla), [{k: v for k, v in f.items() if k in columnas} for f in DATOS.tablas[tabla.name]]
            )
    return motor


def _destino():
    motor = create_engine("sqlite://", poolclass=StaticPool).execution_options(schema_translate_map={"ana_": None})
    dw.metadatos_ana.create_all(motor)
    return motor


def _correr(origen, destino, hoy=HOY):
    with origen.connect() as o, destino.begin() as d:
        return carga.ejecutar_etl(o, d, sal=SAL, hoy=hoy, catalogo_estados=CATALOGO_ESTADOS)


def _conteos(destino) -> dict[str, int]:
    with destino.connect() as con:
        tablas = [t for t in dw.metadatos_ana.sorted_tables if not t.name.startswith("etl_")]
        return {t.name: con.execute(select(func.count()).select_from(t)).scalar() for t in tablas}


@pytest.fixture(scope="module")
def cargado():
    origen, destino = _origen(), _destino()
    resumenes = _correr(origen, destino)
    yield origen, destino, resumenes
    origen.dispose()
    destino.dispose()


def test_la_ejecucion_carga_todas_las_tablas_sin_errores(cargado):
    _, destino, resumenes = cargado
    assert [r.error for r in resumenes] == [None] * len(resumenes)
    esperadas = {t.name for t in (*dw.DIMENSIONES_DW, *dw.HECHOS_DW, *dw.AGREGADOS_DW)}
    assert {r.tabla_destino for r in resumenes} == esperadas
    conteos = _conteos(destino)
    assert all(conteos[t] > 0 for t in esperadas), conteos
    with destino.connect() as con:
        registradas = con.execute(select(func.count()).select_from(dw.etl_ejecucion)).scalar()
    assert registradas == len(resumenes)


def test_ninguna_columna_sensible_llega_a_ana(cargado):
    _, destino, _ = cargado
    columnas = {c["name"] for t in inspect(destino).get_table_names() for c in inspect(destino).get_columns(t)}
    assert not columnas & vistas.COLUMNAS_PROHIBIDAS
    assert "nit" not in columnas and "id_usuario" not in columnas
    with destino.connect() as con:
        seudonimos = con.execute(select(dw.dim_persona_rol.c.seudonimo)).scalars().all()
        estudiantes = con.execute(select(dw.hecho_practica.c.seudonimo_estudiante)).scalars().all()
        nits = con.execute(select(dw.dim_empresa.c.nit_hash)).scalars().all()
    hex64 = re.compile(r"^[0-9a-f]{64}$")
    assert all(hex64.match(s) for s in seudonimos + [e for e in estudiantes if e] + [n for n in nits if n])
    en_claro = {"".join(ch for ch in e["nit"] if ch.isdigit()) for e in DATOS.tablas["empresa"]}
    assert not en_claro & set(nits)


@pytest.mark.parametrize(
    ("entidad", "regla", "claves"),
    [
        ("proyecto_investigacion", calidad.FIN_ANTES_DE_INICIO, ["proyecto_fin_antes_inicio"]),
        ("proyecto_investigacion", calidad.PRESUPUESTO_NEGATIVO, ["proyecto_presupuesto_ejecutado_negativo"]),
        ("proyecto_investigacion", calidad.ESTADO_FUERA_DE_CATALOGO, ["proyecto_estado_fuera_catalogo"]),
        ("practica", calidad.SIN_EMPRESA, ["practica_sin_empresa"]),
        ("practica", calidad.SIN_TUTOR,
         ["practica_sin_tutor_academico", "practica_sin_tutor_empresarial", "practica_sin_tutor_ninguno"]),
        ("convenio", calidad.SIN_FECHA_FIN, ["convenio_sin_fecha_fin"]),
    ],
)  # fmt: skip
def test_las_marcas_de_calidad_registran_los_defectos_sembrados(cargado, entidad, regla, claves):
    _, destino, _ = cargado
    m = dw.etl_marca_calidad
    with destino.connect() as con:
        ids = set(con.execute(select(m.c.id_origen).where(m.c.entidad == entidad, m.c.regla == regla)).scalars())
    assert ids == {i for clave in claves for i in DATOS.defectos[clave]}


def test_los_registros_marcados_se_cargan_no_se_descartan(cargado):
    _, destino, resumenes = cargado
    por_tabla = {r.tabla_destino: r for r in resumenes}
    h = dw.hecho_practica
    with destino.connect() as con:
        marcadas = con.execute(select(func.count()).select_from(h).where(h.c.marca_calidad.is_not(None))).scalar()
        sin_empresa = con.execute(select(func.count()).select_from(h).where(h.c.sk_empresa.is_(None))).scalar()
    assert marcadas == por_tabla["hecho_practica"].filas_marcadas > 0
    assert por_tabla["hecho_practica"].filas_cargadas == len(DATOS.tablas["practica"])
    assert sin_empresa == len(DATOS.defectos["practica_sin_empresa"])  # clave nula, fila cargada


def test_agg_proyecto_linea_mes_coincide_con_hecho_proyecto(cargado):
    _, destino, _ = cargado
    h, a = dw.hecho_proyecto, dw.agg_proyecto_linea_mes
    with destino.connect() as con:
        hecho = con.execute(
            select(func.count(), func.sum(h.c.presupuesto_ejecutado), func.sum(h.c.n_hitos_atrasados)).where(
                h.c.sk_fecha_corte == 20261031, h.c.sk_linea.is_not(None)
            )
        ).one()
        agregado = con.execute(
            select(func.sum(a.c.n_proyectos), func.sum(a.c.presupuesto_ejecutado), func.sum(a.c.n_hitos_atrasados))
            .where(a.c.sk_fecha_corte == 20261031)
        ).one()  # fmt: skip
    assert agregado[0] == hecho[0] == len(DATOS.tablas["proyecto_investigacion"])
    assert float(agregado[1]) == pytest.approx(float(hecho[1]))
    assert agregado[2] == hecho[2]


def test_agg_facturacion_mes_suma_las_facturas_hasta_el_corte(cargado):
    _, destino, _ = cargado
    esperado = sum(Decimal(str(f["valor"])) for f in DATOS.tablas["factura_consultoria"] if f["fecha_factura"] <= CORTE)
    with destino.connect() as con:
        agregado = con.execute(select(func.sum(dw.agg_facturacion_mes.c.valor_facturado))).scalar()
        facturado = con.execute(select(func.sum(dw.hecho_consultoria.c.valor_facturado))).scalar()
        dias = con.execute(select(dw.agg_facturacion_mes.c.sk_fecha)).scalars().all()
    assert float(agregado) == pytest.approx(float(esperado), abs=0.01)
    assert float(facturado) == pytest.approx(float(esperado), abs=0.01)
    assert {d % 100 for d in dias} == {1}  # primer día del mes de la factura (D-18)


def test_medidas_de_hitos_d11(cargado):
    _, destino, _ = cargado
    hitos = [h for h in DATOS.tablas["hito_entregable"] if h["fecha_planeada"] and h["fecha_planeada"] <= CORTE]
    atrasados = sum(
        1
        for h in hitos
        if (h["fecha_planeada"] < CORTE and (h["fecha_real"] is None or h["fecha_real"] > CORTE))
        or (h["fecha_real"] is not None and h["fecha_real"] <= CORTE and h["fecha_real"] > h["fecha_planeada"])
    )
    h = dw.hecho_proyecto
    with destino.connect() as con:
        n, n_atrasados = con.execute(select(func.sum(h.c.n_hitos), func.sum(h.c.n_hitos_atrasados))).one()
    assert (n, n_atrasados) == (len(hitos), atrasados)


def test_dimensiones_de_las_decisiones(cargado):
    _, destino, _ = cargado
    lp, p, c = dw.dim_linea_programa, dw.hecho_practica, dw.hecho_consultoria
    with destino.connect() as con:
        nivel_programa = con.execute(
            select(func.count()).select_from(lp).where(lp.c.linea_investigacion == carga.LINEA_NO_APLICA)
        ).scalar()
        lineas_practica = set(
            con.execute(select(lp.c.linea_investigacion).join(p, p.c.sk_linea == lp.c.sk_linea).distinct()).scalars()
        )
        roles_tutor = set(
            con.execute(
                select(dw.dim_persona_rol.c.tipo_participacion).join(
                    p, p.c.sk_persona == dw.dim_persona_rol.c.sk_persona
                )
            ).scalars()
        )
        roles_consultor = set(
            con.execute(
                select(dw.dim_persona_rol.c.tipo_participacion).join(
                    c, c.c.sk_persona == dw.dim_persona_rol.c.sk_persona
                )
            ).scalars()
        )
    assert nivel_programa == len(DATOS.tablas["facultad_programa"])  # D-13
    assert lineas_practica == {carga.LINEA_NO_APLICA}  # D-13
    assert roles_tutor == {"tutor_academico"}  # D-14
    assert roles_consultor == {"lider"}  # D-12


def test_repetir_el_mismo_dia_es_idempotente_e_incremental():
    origen, destino = _origen(), _destino()
    _correr(origen, destino)
    antes = _conteos(destino)
    segunda = {r.tabla_destino: r for r in _correr(origen, destino)}
    assert _conteos(destino) == antes
    assert segunda["hecho_practica"].modo == carga.MODO_FECHA and segunda["hecho_practica"].filas_leidas == 0
    assert segunda["hecho_hito"].modo == carga.MODO_HUELLA and segunda["hecho_hito"].filas_cargadas == 0
    assert segunda["hecho_consultoria"].filas_cargadas == 0
    assert segunda["dim_macroproyecto"].filas_cargadas == 0


def test_scd2_de_macroproyecto_y_cambio_detectado_por_huella():
    origen, destino = _origen(), _destino()
    _correr(origen, destino)
    macro = DATOS.tablas["macroproyecto"][0]["id_macroproyecto"]
    hito = DATOS.tablas["hito_entregable"][0]["id_hito"]
    nuevo_estado = "suspendido" if DATOS.tablas["macroproyecto"][0]["estado"] != "suspendido" else "activo"
    t_macro = vistas.tabla_fuente("macroproyecto")
    t_hito = vistas.tabla_fuente("hito_entregable")
    with origen.begin() as con:
        con.execute(update(t_macro).where(t_macro.c.id_macroproyecto == macro).values(estado=nuevo_estado))
        con.execute(update(t_hito).where(t_hito.c.id_hito == hito).values(tipo="otro tipo"))
    siguiente = {r.tabla_destino: r for r in _correr(origen, destino, hoy=date(2026, 11, 6))}
    m = dw.dim_macroproyecto
    with destino.connect() as con:
        versiones = con.execute(
            select(m.c.estado_actual, m.c.vigente_desde, m.c.vigente_hasta).where(m.c.id_origen == macro)
            .order_by(m.c.vigente_desde)
        ).all()  # fmt: skip
    assert len(versiones) == 2
    assert versiones[0].vigente_hasta == date(2026, 11, 5) and versiones[1].vigente_hasta is None
    assert versiones[1].estado_actual == nuevo_estado and versiones[1].vigente_desde == date(2026, 11, 6)
    # El tipo del hito no entra en el hecho: su huella no cambia y no se recarga.
    assert siguiente["hecho_hito"].filas_cargadas == 0


def test_una_tabla_que_falla_queda_registrada_y_las_independientes_siguen(monkeypatch):
    origen, destino = _origen(), _destino()

    def falla(*_args, **_kwargs):
        raise RuntimeError("fuente no disponible")

    monkeypatch.setattr(carga, "_cargar_dim_tipo_convenio", falla)
    resumenes = {r.tabla_destino: r for r in _correr(origen, destino)}
    assert "fuente no disponible" in resumenes["dim_tipo_convenio"].error
    assert "dim_tipo_convenio" in resumenes["hecho_convenio"].error  # depende de ella: se omite
    assert resumenes["hecho_proyecto"].error is None and resumenes["hecho_practica"].error is None
    assert Counter(r.error is None for r in resumenes.values())[True] == len(resumenes) - 2
    e = dw.etl_ejecucion
    with destino.connect() as con:
        errores = con.execute(select(e.c.tabla_destino).where(e.c.error.is_not(None))).scalars().all()
        convenios = con.execute(select(func.count()).select_from(dw.hecho_convenio)).scalar()
    assert sorted(errores) == ["dim_tipo_convenio", "hecho_convenio"] and convenios == 0


def test_el_periodo_de_los_datos_sinteticos_coincide_con_el_corte():
    assert FECHA_CORTE == CORTE  # el corte de las pruebas es el último mes cerrado de HOY


def test_catalogo_de_estados_del_servicio_igual_al_del_generador():
    from ciumb_analitica.etl.programacion import CATALOGO_ESTADOS as DEL_SERVICIO

    assert DEL_SERVICIO == CATALOGO_ESTADOS  # copia provisional (D-04) hasta tener el catálogo oficial


def test_ejecutar_una_vez_con_historico(tmp_path):
    from ciumb_analitica.etl.programacion import ejecutar_una_vez, programar

    origen = _origen()
    destino = create_engine(f"sqlite:///{tmp_path / 'ana.db'}").execution_options(schema_translate_map={"ana_": None})
    dw.metadatos_ana.create_all(destino)
    resumenes = ejecutar_una_vez(hoy=HOY, historico_desde=date(2026, 7, 1), origen=origen, destino=destino, sal=SAL)
    assert all(r.error is None for r in resumenes)
    with destino.connect() as con:
        cortes = con.execute(select(dw.hecho_proyecto.c.sk_fecha_corte).distinct()).scalars().all()
    assert sorted(cortes) == [20260731, 20260831, 20260930, 20261031]
    trabajo = programar(lambda: None, hora=3).get_job("etl_nocturno")
    assert "hour='3'" in str(trabajo.trigger)


def test_la_carga_historica_no_repite_las_marcas_de_calidad(tmp_path):
    from ciumb_analitica.etl.programacion import ejecutar_una_vez

    origen = _origen()
    destino = create_engine(f"sqlite:///{tmp_path / 'ana.db'}").execution_options(schema_translate_map={"ana_": None})
    dw.metadatos_ana.create_all(destino)
    ejecutar_una_vez(hoy=HOY, historico_desde=date(2026, 7, 1), origen=origen, destino=destino, sal=SAL)
    m = dw.etl_marca_calidad
    with destino.connect() as con:
        repetidos = con.execute(
            select(func.count())
            .select_from(m)
            .where(m.c.entidad == "proyecto_investigacion", m.c.regla == "presupuesto_negativo")
        ).scalar()
    assert repetidos == len(DATOS.defectos["proyecto_presupuesto_ejecutado_negativo"])
