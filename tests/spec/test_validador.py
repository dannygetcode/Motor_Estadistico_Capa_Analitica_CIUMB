"""Validador de especificaciones: los 7 pasos de la sección 4.4.2 sobre P1–P10 (Tabla 22) y casos límite."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from ciumb_analitica.semantica.semilla import PLANTILLAS, capa_semilla
from ciumb_analitica.spec import resultado as r
from ciumb_analitica.spec.modelos import Agregacion, Granularidad, OrigenGrafico, TipoGrafico
from ciumb_analitica.spec.resultado import Estado, Nivel
from ciumb_analitica.spec.validador import revisar_datos, validar
from tests.conftest import IDS_PROMPTS, fixture_prompt

CAPA = capa_semilla()
HOY = date(2026, 11, 5)


def _validar(spec: dict, **kw):
    return validar(spec, CAPA, hoy=kw.pop("hoy", HOY), **kw)


def _spec(**cambios) -> dict:
    base = {
        "esquema": "ciumb.spec/1.0",
        "origen": "prompt",
        "metricas": [{"id": "proyectos"}],
        "dimensiones": [{"id": "facultad"}],
        "periodo": {"desde": "2026-01-01", "hasta": "2026-10-31"},
        "alcance": {"rol": "directivo"},
    }
    return {k: v for k, v in (base | cambios).items() if v is not None}


def _codigos(resultado) -> set[str]:
    return {p.codigo for p in resultado.problemas}


# --- P1–P10 (Tabla 22) ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("nombre", IDS_PROMPTS)
def test_p1_p10_resultado_grafico_y_avisos(nombre):
    caso = fixture_prompt(nombre)
    esperado = caso["esperado"]
    resultado = _validar(caso["spec"], hoy=date.fromisoformat(caso["fecha_referencia"]))

    assert resultado.estado.value == esperado["resultado"]
    assert resultado.motivo == esperado["motivo"]
    if esperado["resultado"] == "valida":
        assert resultado.spec.grafico.tipo.value == esperado["grafico_final"]
        assert resultado.spec.grafico.origen.value == esperado["grafico_origen"]
        assert sorted(a.codigo for a in resultado.avisos) == sorted(esperado["avisos"])
    else:
        assert resultado.spec is None
        for sugerida in esperado.get("dimensiones_sugeridas_incluyen", []):
            assert sugerida in resultado.problemas[0].opciones


def test_p1_periodo_recortado_al_ultimo_mes_cerrado():
    spec = _validar(fixture_prompt("p01")["spec"]).spec
    assert (spec.periodo.desde, spec.periodo.hasta) == (date(2026, 1, 1), date(2026, 10, 31))
    assert spec.corte == date(2026, 10, 31)
    assert spec.nivel is Nivel.AGREGADO


def test_p2_filtro_temporal_cuenta_como_periodo_y_torta_de_seis_sectores():
    resultado = _validar(fixture_prompt("p02")["spec"])
    assert resultado.spec.periodo is None and resultado.spec.corte == date(2026, 10, 31)
    assert resultado.spec.grafico.max_sectores == 6
    assert resultado.avisos == ()


def test_p4_razon_no_aditiva_y_variable_fuera_de_dimensiones():
    spec = _validar(fixture_prompt("p04")["spec"]).spec
    assert spec.metricas[0].agregacion is Agregacion.RAZON
    assert spec.analisis.variables == ["facultad", "estado_hito"]
    assert spec.dimensiones[1].granularidad is Granularidad.TRIMESTRE


def test_p5_y_p6_se_leen_registro_a_registro():
    p5 = _validar(fixture_prompt("p05")["spec"]).spec
    assert p5.nivel is Nivel.REGISTRO and [m.agregacion for m in p5.metricas] == [None, None]
    assert (p5.periodo.desde, p5.periodo.hasta) == (date(2026, 1, 1), date(2026, 10, 31))
    p6 = _validar(fixture_prompt("p06")["spec"]).spec
    assert p6.nivel is Nivel.REGISTRO and p6.base == "INF-INV-02"


def test_p7_recomienda_lineas_y_p8_agrupa_tres_hechos():
    p7 = _validar(fixture_prompt("p07")["spec"]).spec
    assert (p7.grafico.tipo, p7.grafico.origen) == (TipoGrafico.LINEAS, OrigenGrafico.RECOMENDADO)
    p8 = _validar(fixture_prompt("p08")["spec"]).spec
    assert p8.nivel is Nivel.AGREGADO and len(p8.metricas) == 3


def test_p9_guarda_el_tipo_pedido():
    resultado = _validar(fixture_prompt("p09")["spec"])
    assert resultado.spec.grafico.pedido is TipoGrafico.TORTA
    assert "torta" in resultado.avisos[0].mensaje and "líneas" in resultado.avisos[0].mensaje


def test_p10_explica_y_ofrece_lo_que_si_existe():
    resultado = _validar(fixture_prompt("p10")["spec"])
    problema = resultado.problemas[0]
    assert problema.paso == 7 and "identifica personas" in problema.mensaje
    assert {"programa", "facultad", "estado"} <= set(problema.opciones)
    assert not {"estudiante", "persona", "estado_hito"} & set(problema.opciones)


@pytest.mark.parametrize("plantilla", PLANTILLAS, ids=lambda p: p["codigo_informe"])
def test_las_plantillas_base_son_validas(plantilla):
    resultado = _validar(plantilla["spec"], plantillas={p["codigo_informe"] for p in PLANTILLAS})
    assert resultado.estado is Estado.VALIDA, resultado.problemas


# --- Paso 1 ---------------------------------------------------------------------------------------------------


def test_paso1_campo_desconocido_es_error_de_la_ia():
    resultado = _validar(_spec(sql="SELECT 1"))
    assert resultado.estado is Estado.CORREGIBLE
    assert [(p.codigo, p.paso, p.para, p.campo) for p in resultado.problemas] == [(r.ESQUEMA_INVALIDO, 1, "ia", "sql")]


def test_paso1_sin_metricas_se_repregunta_al_usuario():
    for metricas in (None, []):
        resultado = _validar(_spec(metricas=metricas) if metricas is None else _spec() | {"metricas": []})
        assert resultado.estado is Estado.CORREGIBLE
        assert (resultado.problemas[0].codigo, resultado.problemas[0].para) == (r.FALTA_METRICA, "usuario")


def test_paso1_no_repite_valores_del_prompt_en_el_mensaje():
    resultado = _validar(_spec(alcance={"rol": "directivo", "correo": "persona@correo.com"}))
    assert "persona@correo.com" not in " ".join(p.mensaje for p in resultado.problemas)


@pytest.mark.parametrize("basura", [None, [], "texto", 5])
def test_paso1_entrada_que_no_es_un_objeto(basura):
    assert _validar(basura).estado is Estado.CORREGIBLE


# --- Paso 2 ---------------------------------------------------------------------------------------------------


def test_paso2_metrica_que_no_existe_queda_fuera_de_alcance():
    resultado = _validar(_spec(metricas=[{"id": "interacciones_facebook"}]))
    assert resultado.estado is Estado.FUERA_DE_ALCANCE and resultado.motivo == r.METRICA_INEXISTENTE


def test_paso2_metrica_parecida_se_repregunta_y_nunca_se_adivina():
    resultado = _validar(_spec(metricas=[{"id": "proyecto"}]))
    assert resultado.estado is Estado.CORREGIBLE and resultado.motivo == r.METRICA_PARECIDA
    assert "proyectos" in resultado.problemas[0].opciones and resultado.spec is None


def test_paso2_dimension_filtro_y_variable_inexistentes():
    assert _validar(_spec(dimensiones=[{"id": "color"}])).motivo == r.DIMENSION_INEXISTENTE
    assert _validar(_spec(filtros=[{"campo": "correo", "op": "=", "valor": "x"}])).estado is Estado.FUERA_DE_ALCANCE
    resultado = _validar(_spec(analisis={"metodo": "chi_cuadrado", "variables": ["facultad", "zzz"]}))
    assert resultado.problemas[0].campo == "analisis.variables.1"


def test_paso2_plantilla_inexistente():
    spec = _spec(origen="plantilla_base", base="INF-ZZZ-99")
    assert _validar(spec, plantillas={"INF-INV-02"}).motivo == r.PLANTILLA_INEXISTENTE
    assert _validar(spec).estado is Estado.VALIDA  # sin catálogo no se puede comprobar


def test_paso2_metrica_inactiva_no_existe():
    inactiva = CAPA.metricas["proyectos"].model_copy(update={"activa": False})
    capa = CAPA.model_copy(update={"metricas": CAPA.metricas | {"proyectos": inactiva}})
    assert validar(_spec(), capa, hoy=HOY).estado is not Estado.VALIDA


# --- Paso 3 ---------------------------------------------------------------------------------------------------


def test_paso3_cruce_que_la_matriz_de_bus_no_permite():
    resultado = _validar(_spec(metricas=[{"id": "convenios"}], dimensiones=[{"id": "linea_investigacion"}]))
    assert resultado.estado is Estado.FUERA_DE_ALCANCE and resultado.motivo == r.INCOMPATIBLE
    assert "tipo_convenio" in resultado.problemas[0].opciones
    assert "linea_investigacion" not in resultado.problemas[0].opciones


def test_paso3_filtro_incompatible_y_practicas_por_linea_d13():
    filtro = [{"campo": "tipo_convenio", "op": "=", "valor": "marco"}]
    assert _validar(_spec(filtros=filtro)).motivo == r.INCOMPATIBLE
    assert _validar(_spec(metricas=[{"id": "practicas"}], dimensiones=[{"id": "linea_investigacion"}])).motivo == (
        r.INCOMPATIBLE
    )


@pytest.mark.parametrize("agregacion", ["suma", "promedio", "conteo", "mediana"])
def test_paso3_una_razon_no_se_suma_ni_se_promedia(agregacion):
    resultado = _validar(_spec(metricas=[{"id": "pct_ejecucion", "agregacion": agregacion}]))
    assert resultado.estado is Estado.CORREGIBLE and resultado.motivo == r.AGREGACION_INVALIDA
    assert resultado.problemas[0].opciones == ("razon",)
    assert "componentes" in resultado.problemas[0].mensaje


def test_paso3_agregacion_por_defecto_y_agregacion_invalida_en_un_conteo():
    assert _validar(_spec()).spec.metricas[0].agregacion is Agregacion.CONTEO
    assert _validar(_spec(metricas=[{"id": "proyectos", "agregacion": "suma"}])).motivo == r.AGREGACION_INVALIDA


def test_paso3_dimension_binaria_solo_como_variable_de_prueba():
    assert _validar(_spec(metricas=[{"id": "pct_hitos_atrasados"}], dimensiones=[{"id": "estado_hito"}])).motivo == (
        r.DIMENSION_SOLO_PRUEBA
    )
    con_otra_metrica = _spec(analisis={"metodo": "chi_cuadrado", "variables": ["facultad", "estado_hito"]})
    assert _validar(con_otra_metrica).motivo == r.INCOMPATIBLE


@pytest.mark.parametrize(
    ("filtro", "codigo"),
    [
        ({"campo": "facultad", "op": ">", "valor": "A"}, r.OPERADOR_INVALIDO),
        ({"campo": "facultad", "op": "entre", "valor": ["A", "B"]}, r.OPERADOR_INVALIDO),
        ({"campo": "facultad", "op": "=", "valor": 3}, r.VALOR_INVALIDO),
        ({"campo": "anio", "op": "=", "valor": "2026"}, r.VALOR_INVALIDO),
        ({"campo": "anio", "op": "=", "valor": True}, r.VALOR_INVALIDO),
        ({"campo": "tiempo", "op": ">=", "valor": "ayer"}, r.VALOR_INVALIDO),
        ({"campo": "tiempo", "op": ">=", "valor": "2026-13-01"}, r.VALOR_INVALIDO),
    ],
)
def test_paso3_filtros_mal_formados(filtro, codigo):
    resultado = _validar(_spec(filtros=[filtro]))
    assert resultado.motivo == codigo and resultado.problemas[0].para == "ia"


def test_paso3_filtros_bien_formados():
    filtros = [
        {"campo": "anio", "op": "entre", "valor": [2024, 2026]},
        {"campo": "tiempo", "op": ">=", "valor": "2026-03-01"},
        {"campo": "estado", "op": "en", "valor": ["en_ejecucion", "aprobado"]},
        {"campo": "facultad", "op": "!=", "valor": "Derecho"},
    ]
    assert _validar(_spec(filtros=filtros)).estado is Estado.VALIDA


def test_paso3_granularidad_solo_en_tiempo():
    assert _validar(_spec(dimensiones=[{"id": "facultad", "granularidad": "mes"}])).motivo == r.GRANULARIDAD_NO_APLICA
    spec = _validar(_spec(dimensiones=[{"id": "tiempo"}])).spec
    assert spec.dimensiones[0].granularidad is Granularidad.MES and spec.granularidad() is Granularidad.MES


# --- Paso 4 ---------------------------------------------------------------------------------------------------

COORDINADOR = {"rol": "coordinador", "facultad": "Ingeniería"}


def test_paso4_el_prompt_puede_estrechar_el_alcance_pero_no_ampliarlo():
    dentro = _spec(alcance=COORDINADOR, filtros=[{"campo": "programa", "op": "=", "valor": "Ingeniería de Software"}])
    assert _validar(dentro).estado is Estado.VALIDA
    misma = _spec(alcance=COORDINADOR, filtros=[{"campo": "facultad", "op": "=", "valor": "Ingeniería"}])
    assert _validar(misma).estado is Estado.VALIDA
    for valor, op in (("Derecho", "="), (["Ingeniería", "Derecho"], "en")):
        fuera = _spec(alcance=COORDINADOR, filtros=[{"campo": "facultad", "op": op, "valor": valor}])
        resultado = _validar(fuera)
        assert resultado.estado is Estado.FUERA_DE_ALCANCE and resultado.motivo == r.ALCANCE_EXCEDIDO


def test_paso4_el_alcance_viaja_intacto_en_la_spec_resuelta():
    assert _validar(_spec(alcance=COORDINADOR)).spec.alcance.facultad == "Ingeniería"


def test_paso4_si_el_alcance_no_se_puede_aplicar_se_niega():
    resultado = _validar(_spec(alcance=COORDINADOR, metricas=[{"id": "consultorias"}], dimensiones=[]))
    assert resultado.estado is Estado.FUERA_DE_ALCANCE and resultado.motivo == r.ALCANCE_NO_APLICABLE


@pytest.mark.parametrize(
    ("rol", "metrica", "valida"),
    [
        ("tutor", "practicas", True),
        ("tutor", "proyectos", False),
        ("tutor", "consultorias", False),
        ("consultor", "consultorias", True),
        ("consultor", "facturacion", False),
        ("consultor", "practicas", False),
        ("administrador", "accesos", True),
        ("directivo", "consultorias", True),
    ],
)
def test_paso4_roles_con_alcance_personal(rol, metrica, valida):
    alcance = {"rol": rol} | ({"id_usuario": 412} if rol in ("tutor", "consultor") else {})
    resultado = _validar(_spec(alcance=alcance, metricas=[{"id": metrica}], dimensiones=[]))
    assert (resultado.estado is Estado.VALIDA) == valida
    if not valida:
        assert resultado.motivo == r.ALCANCE_NO_APLICABLE


def test_periodo_por_defecto_es_determinista_y_depende_de_la_fecha_de_referencia():
    spec = _spec(periodo=None)
    a = _validar(spec, hoy=date(2026, 11, 5))
    b = _validar(spec, hoy=date(2026, 11, 28))
    c = _validar(spec, hoy=date(2027, 1, 10))
    assert a.spec == b.spec and a.spec.huella() == b.spec.huella()
    assert (c.spec.periodo.desde, c.spec.periodo.hasta) == (date(2026, 1, 1), date(2026, 12, 31))
    assert [x.codigo for x in a.avisos] == [r.PERIODO_POR_DEFECTO] and "2026-10-31" in a.avisos[0].mensaje


def test_periodo_futuro_es_corregible():
    resultado = _validar(_spec(periodo={"desde": "2027-01-01", "hasta": "2027-06-30"}))
    assert resultado.estado is Estado.CORREGIBLE and resultado.motivo == r.PERIODO_FUTURO


def test_el_corte_nunca_supera_el_ultimo_cierre():
    spec = _validar(_spec(periodo={"desde": "2026-01-01", "hasta": "2026-06-30", "corte": "2026-12-31"})).spec
    assert spec.corte == date(2026, 10, 31) and spec.periodo.hasta == date(2026, 6, 30)


# --- Paso 5 ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("metodo", ["serie", "variacion", "variacion_interanual", "pronostico"])
def test_paso5_los_metodos_de_series_exigen_tiempo(metodo):
    resultado = _validar(_spec(analisis={"metodo": metodo}))
    assert resultado.estado is Estado.CORREGIBLE and resultado.motivo == r.FALTA_DIMENSION_TEMPORAL
    assert "mes" in resultado.problemas[0].opciones
    assert _validar(_spec(analisis={"metodo": metodo}, dimensiones=[{"id": "tiempo"}])).estado is Estado.VALIDA


def test_paso5_pearson_exige_dos_metricas_numericas_de_la_spec():
    malo = _spec(analisis={"metodo": "pearson", "variables": ["facultad", "estado"]})
    assert _validar(malo).motivo == r.VARIABLES_INVALIDAS
    ausente = _spec(
        metricas=[{"id": "satisfaccion"}],
        dimensiones=[],
        analisis={"metodo": "pearson", "variables": ["satisfaccion", "n_consultores"]},
    )
    assert _validar(ausente).motivo == r.VARIABLES_INVALIDAS


def test_paso5_correlacion_entre_hechos_distintos_exige_una_dimension_comun():
    spec = _spec(
        metricas=[{"id": "satisfaccion"}, {"id": "presupuesto_ejecutado"}],
        dimensiones=[],
        analisis={"metodo": "pearson", "variables": ["satisfaccion", "presupuesto_ejecutado"]},
    )
    assert _validar(spec).motivo == r.METRICAS_DE_HECHOS_DISTINTOS
    comun = _spec(
        metricas=[{"id": "practicas"}, {"id": "consultorias"}],
        dimensiones=[{"id": "empresa"}],
        analisis={"metodo": "spearman", "variables": ["practicas", "consultorias"]},
    )
    resultado = _validar(comun)
    assert resultado.estado is Estado.VALIDA and resultado.spec.nivel is Nivel.AGREGADO
    assert resultado.spec.grafico.tipo is TipoGrafico.DISPERSION


def test_paso5_chi_cuadrado():
    conteo = _spec(
        dimensiones=[{"id": "facultad"}, {"id": "estado"}],
        analisis={"metodo": "chi_cuadrado", "variables": ["facultad", "estado"]},
    )
    assert _validar(conteo).estado is Estado.VALIDA
    con_tiempo = _spec(analisis={"metodo": "chi_cuadrado", "variables": ["facultad", "tiempo"]})
    assert _validar(con_tiempo).motivo == r.VARIABLES_INVALIDAS
    con_razon = _spec(
        metricas=[{"id": "pct_ejecucion"}], analisis={"metodo": "chi_cuadrado", "variables": ["facultad", "estado"]}
    )
    assert _validar(con_razon).motivo == r.METODO_NO_APLICABLE


def test_paso5_t_student_y_mann_whitney():
    bien = _spec(
        metricas=[{"id": "satisfaccion"}],
        dimensiones=[],
        analisis={"metodo": "mann_whitney", "variables": ["satisfaccion", "sector"]},
    )
    resultado = _validar(bien)
    assert resultado.estado is Estado.VALIDA and resultado.spec.nivel is Nivel.REGISTRO
    conteo = _spec(dimensiones=[], analisis={"metodo": "t_student", "variables": ["proyectos", "facultad"]})
    assert _validar(conteo).motivo == r.METODO_NO_APLICABLE
    al_reves = _spec(
        metricas=[{"id": "satisfaccion"}],
        dimensiones=[],
        analisis={"metodo": "t_student", "variables": ["sector", "satisfaccion"]},
    )
    assert _validar(al_reves).motivo == r.VARIABLES_INVALIDAS


def test_paso5_segmentacion_exige_unidad_de_analisis():
    assert _validar(_spec(dimensiones=[], analisis={"metodo": "segmentacion"})).motivo == r.FALTA_UNIDAD_DE_ANALISIS


def test_paso5_nivel_de_lectura():
    assert _validar(_spec()).spec.nivel is Nivel.AGREGADO  # descriptiva sobre un conteo: valores por grupo
    medida = _validar(_spec(metricas=[{"id": "presupuesto_ejecutado"}]))
    assert medida.spec.nivel is Nivel.REGISTRO and medida.spec.metricas[0].agregacion is None
    suma = _validar(_spec(metricas=[{"id": "presupuesto_ejecutado"}], analisis={"metodo": "frecuencias"}))
    assert suma.spec.nivel is Nivel.AGREGADO and suma.spec.metricas[0].agregacion is Agregacion.SUMA
    mediana = _validar(
        _spec(
            metricas=[{"id": "satisfaccion", "agregacion": "mediana"}],
            dimensiones=[{"id": "sector"}],
            analisis={"metodo": "frecuencias"},
        )
    )
    assert mediana.spec.nivel is Nivel.REGISTRO and mediana.spec.metricas[0].agregacion is Agregacion.MEDIANA
    mezcla = _spec(metricas=[{"id": "proyectos"}, {"id": "presupuesto_ejecutado", "agregacion": "mediana"}])
    assert _validar(mezcla).motivo == r.METODO_NO_APLICABLE


# --- Paso 6 (Tabla 21) ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cambios", "esperado"),
    [
        ({}, "barras"),
        ({"dimensiones": [{"id": "facultad"}, {"id": "estado"}]}, "barras"),
        ({"dimensiones": [{"id": "tiempo"}], "analisis": {"metodo": "serie"}}, "lineas"),
        ({"dimensiones": [{"id": "anio"}]}, "lineas"),
        ({"metricas": [{"id": "pct_ejecucion"}], "dimensiones": []}, "histograma"),
        (
            {"metricas": [{"id": "presupuesto_ejecutado"}], "dimensiones": [], "analisis": {"metodo": "atipicos"}},
            "histograma",
        ),
        (
            {
                "metricas": [{"id": "n_consultores"}, {"id": "satisfaccion"}],
                "dimensiones": [],
                "analisis": {"metodo": "pearson", "variables": ["n_consultores", "satisfaccion"]},
            },
            "dispersion",
        ),
        (
            {
                "metricas": [{"id": "practicas"}, {"id": "convenios"}],
                "dimensiones": [{"id": "empresa"}],
                "analisis": {"metodo": "segmentacion"},
            },
            "dispersion",
        ),
        (
            {
                "metricas": [{"id": "practicas"}],
                "dimensiones": [{"id": "empresa"}],
                "analisis": {"metodo": "segmentacion"},
            },
            "barras",
        ),
    ],
)
def test_paso6_recomendador_determinista(cambios, esperado):
    spec = _spec(**cambios)
    primero, segundo = _validar(spec), _validar(spec)
    assert primero.estado is Estado.VALIDA, primero.problemas
    assert primero.spec.grafico.tipo.value == esperado
    assert primero.spec.grafico.origen is OrigenGrafico.RECOMENDADO
    assert primero.spec.grafico == segundo.spec.grafico


def test_paso6_la_torta_nunca_se_recomienda():
    for plantilla in PLANTILLAS:
        sin_grafico = {k: v for k, v in plantilla["spec"].items() if k != "grafico"}
        assert _validar(sin_grafico).spec.grafico.tipo is not TipoGrafico.TORTA


@pytest.mark.parametrize(
    ("cambios", "pedido", "final"),
    [
        ({"dimensiones": [{"id": "tiempo"}]}, "torta", "lineas"),
        ({"metricas": [{"id": "pct_ejecucion"}]}, "torta", "barras"),  # la razón no suma un total
        ({"dimensiones": [{"id": "facultad"}, {"id": "estado"}]}, "torta", "barras"),
        ({}, "lineas", "barras"),
        ({}, "dispersion", "barras"),
        ({}, "mapa_calor", "barras"),
        ({}, "histograma", "barras"),
        (
            {
                "metricas": [{"id": "satisfaccion", "agregacion": "promedio"}],
                "dimensiones": [{"id": "sector"}],
                "analisis": {"metodo": "frecuencias"},
            },
            "torta",
            "barras",
        ),
    ],
)
def test_paso6_tipo_pedido_incompatible_se_sustituye_con_aviso(cambios, pedido, final):
    resultado = _validar(_spec(**cambios, grafico={"tipo": pedido}))
    assert resultado.estado is Estado.VALIDA, resultado.problemas
    grafico = resultado.spec.grafico
    assert (grafico.tipo.value, grafico.pedido.value, grafico.origen) == (final, pedido, OrigenGrafico.PROMPT)
    assert [a.codigo for a in resultado.avisos] == [r.GRAFICO_SUSTITUIDO]


@pytest.mark.parametrize(
    ("cambios", "pedido"),
    [
        ({}, "torta"),
        ({}, "barras"),
        ({"dimensiones": [{"id": "tiempo"}]}, "lineas"),
        ({"dimensiones": [{"id": "tiempo"}]}, "barras"),
        ({"dimensiones": [{"id": "facultad"}, {"id": "estado"}]}, "mapa_calor"),
        ({"metricas": [{"id": "pct_ejecucion"}], "dimensiones": []}, "histograma"),
    ],
)
def test_paso6_tipo_pedido_compatible_se_respeta(cambios, pedido):
    resultado = _validar(_spec(**cambios, grafico={"tipo": pedido}))
    assert resultado.spec.grafico.tipo.value == pedido and resultado.spec.grafico.pedido is None
    assert resultado.avisos == ()


def test_el_histograma_pedido_lleva_la_lectura_a_registros():
    spec = _spec(metricas=[{"id": "satisfaccion"}], dimensiones=[], grafico={"tipo": "histograma"})
    assert _validar(spec).spec.nivel is Nivel.REGISTRO


# --- Determinismo y huella -----------------------------------------------------------------------------------


@pytest.mark.parametrize("nombre", [n for n in IDS_PROMPTS if n != "p10"])
def test_misma_spec_misma_huella(nombre):
    spec = fixture_prompt(nombre)["spec"]
    a, b = _validar(spec).spec, _validar(dict(reversed(list(spec.items())))).spec
    assert a == b and a.huella() == b.huella() and len(a.huella()) == 64


def test_specs_distintas_huellas_distintas():
    huellas = {_validar(fixture_prompt(n)["spec"]).spec.huella() for n in IDS_PROMPTS if n != "p10"}
    assert len(huellas) == 9
    assert _validar(_spec()).spec.huella() != _validar(_spec(alcance=COORDINADOR)).spec.huella()


# --- Después de los datos: pasos 5, 6 y 7 --------------------------------------------------------------------


def _resuelta(nombre_o_spec):
    spec = fixture_prompt(nombre_o_spec)["spec"] if isinstance(nombre_o_spec, str) else nombre_o_spec
    return _validar(spec).spec


def test_paso7_suprime_grupos_con_menos_de_cinco_personas():
    spec = _resuelta("p02")
    datos = pd.DataFrame({"programa": ["A", "B", "C", "D"], "practicas": [40, 4, 5, 1], "_n_personas": [38, 4, 5, 1]})
    revision = revisar_datos(spec, datos)
    assert revision.datos.to_dict("list") == {"programa": ["A", "C"], "practicas": [40, 5]}
    assert revision.grupos_suprimidos == 2
    assert [a.codigo for a in revision.avisos] == [r.GRUPOS_SUPRIMIDOS]
    assert "_n_personas" in datos.columns  # no modifica la entrada


def test_paso7_cuenta_personas_distintas_no_filas():
    spec = _resuelta(_spec(metricas=[{"id": "practicas"}], dimensiones=[{"id": "programa"}]))
    # 6 prácticas pero solo 3 personas distintas: se suprime aunque el conteo sea 6.
    datos = pd.DataFrame({"programa": ["A", "B"], "practicas": [6, 6], "_n_personas": [3, 6]})
    assert revisar_datos(spec, datos).datos["programa"].tolist() == ["B"]


def test_paso7_en_nivel_registro_suprime_por_grupo():
    spec = _resuelta(_spec(metricas=[{"id": "duracion_practica"}], dimensiones=[{"id": "programa"}]))
    assert spec.nivel is Nivel.REGISTRO
    datos = pd.DataFrame(
        {
            "programa": ["A"] * 6 + ["B"] * 3 + ["C"] * 5,
            "duracion_practica": range(14),
            "_persona": [f"a{i}" for i in range(6)] + ["b1", "b2", "b3"] + ["c1"] * 5,
        }
    )
    revision = revisar_datos(spec, datos)
    assert set(revision.datos["programa"]) == {"A"} and revision.grupos_suprimidos == 2
    assert "_persona" not in revision.datos.columns


def test_paso7_en_nivel_registro_sin_dimensiones():
    spec = _resuelta(_spec(metricas=[{"id": "duracion_practica"}], dimensiones=[]))
    pocos = pd.DataFrame({"duracion_practica": [10, 20, 30], "_persona": ["a", "b", "c"]})
    revision = revisar_datos(spec, pocos)
    assert revision.datos.empty and revision.grupos_suprimidos == 1
    suficientes = pd.DataFrame({"duracion_practica": range(5), "_persona": list("abcde")})
    assert len(revisar_datos(spec, suficientes).datos) == 5


def test_sin_columna_de_personas_no_se_suprime_nada():
    spec = _resuelta("p01")
    datos = pd.DataFrame({"estado": ["a"], "facultad": ["F"], "proyectos": [1]})
    revision = revisar_datos(spec, datos)
    assert len(revision.datos) == 1 and revision.grupos_suprimidos == 0 and revision.avisos == ()


def test_p2_torta_con_nueve_programas_agrupa_otros():
    datos = pd.DataFrame({"programa": list("ABCDEFGHI"), "practicas": range(10, 19), "_n_personas": range(10, 19)})
    revision = revisar_datos(_resuelta("p02"), datos)
    assert revision.grafico.tipo is TipoGrafico.TORTA
    assert [a.codigo for a in revision.avisos] == [r.TORTA_OTROS]
    assert "las 5 mayores" in revision.avisos[0].mensaje and "las 4 restantes" in revision.avisos[0].mensaje
    seis = revisar_datos(_resuelta("p02"), datos.head(6))
    assert seis.avisos == ()


def test_torta_con_negativos_se_sustituye():
    spec = _resuelta(
        _spec(
            metricas=[{"id": "presupuesto_ejecutado", "agregacion": "suma"}],
            analisis={"metodo": "frecuencias"},
            grafico={"tipo": "torta"},
        )
    )
    datos = pd.DataFrame({"facultad": ["A", "B"], "presupuesto_ejecutado": [10.0, -2.0]})
    revision = revisar_datos(spec, datos)
    assert (revision.grafico.tipo, revision.grafico.pedido) == (TipoGrafico.BARRAS, TipoGrafico.TORTA)
    assert [a.codigo for a in revision.avisos] == [r.GRAFICO_SUSTITUIDO]


def test_p6_histograma_con_nueve_observaciones_lleva_aviso():
    spec = _resuelta("p06")
    nueve = revisar_datos(spec, pd.DataFrame({"pct_ejecucion": range(9)}))
    assert nueve.grafico.tipo is TipoGrafico.HISTOGRAMA and [a.codigo for a in nueve.avisos] == [r.MUESTRA_PEQUENA]
    assert revisar_datos(spec, pd.DataFrame({"pct_ejecucion": range(20)})).avisos == ()


def test_p7_pronostico_con_menos_de_doce_puntos_no_se_publica():
    spec = _resuelta("p07")

    def serie(n):
        return pd.DataFrame(
            {
                "tiempo_anio": [2019 + i // 2 for i in range(n)],
                "tiempo_semestre": [i % 2 + 1 for i in range(n)],
                "practicas": range(50, 50 + n),
                "_n_personas": range(50, 50 + n),
            }
        )

    corta = revisar_datos(spec, serie(11))
    assert corta.publicar_pronostico is False and [a.codigo for a in corta.avisos] == [r.PRONOSTICO_NO_PUBLICABLE]
    assert revisar_datos(spec, serie(12)).publicar_pronostico is True
    # La supresión ocurre antes de contar los puntos.
    con_hueco = serie(12)
    con_hueco.loc[0, "_n_personas"] = 2
    assert revisar_datos(spec, con_hueco).publicar_pronostico is False


def test_p4_mapa_de_calor_exige_tres_por_tres():
    spec = _resuelta("p04")

    def cruce(facultades, trimestres):
        filas = [(f, 2026, t, 10.0, 1, 10) for f in facultades for t in trimestres]
        return pd.DataFrame(
            filas,
            columns=[
                "facultad",
                "tiempo_anio",
                "tiempo_trimestre",
                "pct_hitos_atrasados",
                "pct_hitos_atrasados__num",
                "pct_hitos_atrasados__den",
            ],
        )

    bien = revisar_datos(spec, cruce("ABC", (1, 2, 3)))
    assert bien.grafico.tipo is TipoGrafico.MAPA_CALOR and bien.avisos == ()
    angosto = revisar_datos(spec, cruce("AB", (1, 2, 3)))
    assert (angosto.grafico.tipo, angosto.grafico.pedido) == (TipoGrafico.BARRAS, TipoGrafico.MAPA_CALOR)
    assert [a.codigo for a in angosto.avisos] == [r.GRAFICO_SUSTITUIDO]


def test_cruce_grande_sin_tipo_pedido_pasa_a_mapa_de_calor():
    spec = _resuelta(_spec(dimensiones=[{"id": "facultad"}, {"id": "estado"}]))
    assert spec.grafico.tipo is TipoGrafico.BARRAS

    def cruce(n, m):
        return pd.DataFrame(
            [(f"F{i}", f"E{j}", 1) for i in range(n) for j in range(m)], columns=["facultad", "estado", "proyectos"]
        )

    assert revisar_datos(spec, cruce(6, 6)).grafico.tipo is TipoGrafico.MAPA_CALOR
    assert revisar_datos(spec, cruce(5, 6)).grafico.tipo is TipoGrafico.BARRAS
    assert revisar_datos(spec, cruce(2, 20)).grafico.tipo is TipoGrafico.BARRAS
    pedido = _resuelta(_spec(dimensiones=[{"id": "facultad"}, {"id": "estado"}], grafico={"tipo": "barras"}))
    assert revisar_datos(pedido, cruce(6, 6)).grafico.tipo is TipoGrafico.BARRAS
