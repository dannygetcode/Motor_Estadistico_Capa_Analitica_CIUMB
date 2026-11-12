"""contrato.empaquetador (sección 4.4.3, Figura 12, DA-04, OE4): solo agregados, cero PII."""

from __future__ import annotations

import hashlib
import math
from datetime import date

import pytest

from ciumb_analitica.contrato import empaquetador
from ciumb_analitica.contrato.pii import ErrorPII
from ciumb_analitica.motor.resultado import SeccionCalculada
from ciumb_analitica.semantica.semilla import capa_semilla
from ciumb_analitica.spec.validador import validar
from tests.conftest import DIR_FIXTURES, PENDIENTE, fixture_prompt, leer_json

pytestmark = PENDIENTE

CAPA = capa_semilla()
HUELLA = hashlib.sha256(b"datos de prueba").hexdigest()
ID_SPEC = "esp-20261105-0042"


def _spec(nombre: str):
    return validar(fixture_prompt(nombre)["spec"], CAPA, hoy=date(2026, 11, 5)).spec


def _seccion_p3() -> SeccionCalculada:
    figura = leer_json(DIR_FIXTURES / "contrato_p03.json")["secciones"][0]
    return SeccionCalculada(id=figura["id"], indicadores=figura["indicadores"], metodo=figura["metodo"])


def _empaquetar(nombre="p03", secciones=None, **kw):
    spec = _spec(nombre)
    return empaquetador.empaquetar(
        spec, spec.grafico, secciones or [_seccion_p3()], capa=CAPA, id_spec=ID_SPEC, huella_datos=HUELLA, **kw
    )


def test_id_de_especificacion():
    assert empaquetador.id_especificacion(date(2026, 11, 5), 42) == ID_SPEC
    with pytest.raises(ValueError):
        empaquetador.id_especificacion(date(2026, 11, 5), 10000)


def test_p3_reproduce_la_figura_12():
    contrato = _empaquetar()
    esperado = leer_json(DIR_FIXTURES / "contrato_p03.json") | {"huella_datos": f"sha256:{HUELLA}"}
    del esperado["especificacion"]["base"]  # nulo: no se serializa
    assert contrato.model_dump(mode="json", exclude_none=True) == esperado


def test_el_grafico_del_contrato_es_el_que_ve_el_usuario():
    spec = _spec("p09")  # se pidió torta y se entrega en líneas
    contrato = empaquetador.empaquetar(
        spec, spec.grafico,
        [SeccionCalculada(id="ejecucion", indicadores=[{"id": "total", "valor": 10.5}], metodo="suma mensual",
                          advertencias=["Se pidió un gráfico de torta; se entrega en líneas."])],
        capa=CAPA, id_spec=ID_SPEC, huella_datos=HUELLA,
    )  # fmt: skip
    assert contrato.especificacion.grafico.tipo.value == "lineas"
    assert "torta" in contrato.secciones[0].advertencias[0]


def test_el_alcance_nunca_lleva_el_usuario():
    spec = validar(
        {"esquema": "ciumb.spec/1.0", "origen": "prompt", "metricas": [{"id": "practicas"}],
         "alcance": {"rol": "tutor", "id_usuario": 412}}, CAPA, hoy=date(2026, 11, 5),
    ).spec  # fmt: skip
    seccion = SeccionCalculada(id="practicas", indicadores=[{"id": "practicas", "valor": 12, "n": 12}], metodo="conteo")
    contrato = empaquetador.empaquetar(spec, spec.grafico, [seccion], capa=CAPA, id_spec=ID_SPEC, huella_datos=HUELLA)
    volcado = contrato.model_dump(mode="json", exclude_none=True)
    assert volcado["alcance"] == {"rol": "tutor"} and "412" not in str(volcado)


def test_periodo_desde_el_filtro_temporal_exige_el_rango_de_los_datos():
    spec = _spec("p02")  # sin `periodo`: lo da el filtro por periodo académico (D-08, D-21)
    seccion = SeccionCalculada(
        id="practicas", indicadores=[{"id": "practicas", "valor": 180, "n": 180}], metodo="conteo"
    )
    with pytest.raises(ValueError, match="periodo"):
        empaquetador.empaquetar(spec, spec.grafico, [seccion], capa=CAPA, id_spec=ID_SPEC, huella_datos=HUELLA)
    contrato = empaquetador.empaquetar(
        spec, spec.grafico, [seccion], capa=CAPA, id_spec=ID_SPEC, huella_datos=HUELLA,
        periodo_datos=(date(2026, 7, 1), date(2026, 10, 31)),
    )  # fmt: skip
    assert (contrato.periodo.desde, contrato.periodo.hasta, contrato.periodo.corte) == (
        date(2026, 7, 1), date(2026, 10, 31), date(2026, 10, 31),
    )  # fmt: skip
    assert contrato.alcance.facultad == "Ingeniería"


@pytest.mark.parametrize("dimension", ["empresa", "macroproyecto", "estudiante", "persona"])
def test_una_dimension_interna_o_personal_no_viaja(dimension):
    seccion = SeccionCalculada(
        id="segmentos", indicadores=[{"id": "practicas", "valor": 5, "grupo": {dimension: "1042"}}], metodo="conteo"
    )
    with pytest.raises(empaquetador.DimensionNoExportable, match=dimension):
        _empaquetar("p08", [seccion])


def test_un_grupo_por_dimension_publica_si_viaja():
    seccion = SeccionCalculada(
        id="proyectos",
        indicadores=[{"id": "proyectos", "valor": 12, "grupo": {"facultad": "Ingeniería", "estado": "en_ejecucion"}}],
        metodo="conteo",
    )
    contrato = _empaquetar("p01", [seccion])
    assert contrato.secciones[0].indicadores[0].grupo == {"facultad": "Ingeniería", "estado": "en_ejecucion"}


def test_el_filtro_de_pii_bloquea_el_envio():
    seccion = SeccionCalculada(
        id="proyectos", indicadores=[{"id": "proyectos", "valor": 12}], metodo="conteo",
        advertencias=["Reportado por ana.perez@umb.edu.co"],
    )  # fmt: skip
    with pytest.raises(ErrorPII):
        _empaquetar("p01", [seccion])


def test_nan_e_infinito_no_se_envian():
    seccion = SeccionCalculada(
        id="ejecucion",
        indicadores=[{"id": "pct_ejecucion", "valor": math.nan}, {"id": "maximo", "valor": math.inf},
                     {"id": "media", "valor": 61.4285714285714}],
        metodo="descriptiva",
    )  # fmt: skip
    contrato = _empaquetar("p06", [seccion])
    assert [i.id for i in contrato.secciones[0].indicadores] == ["media"]
    assert contrato.secciones[0].indicadores[0].valor == pytest.approx(61.428571, abs=1e-6)
    assert len(contrato.secciones[0].advertencias) == 1


def test_la_huella_lleva_el_prefijo_sha256():
    assert _empaquetar().huella_datos == f"sha256:{HUELLA}"
    spec = _spec("p03")
    with pytest.raises(ValueError):
        empaquetador.empaquetar(
            spec, spec.grafico, [_seccion_p3()], capa=CAPA, id_spec=ID_SPEC, huella_datos="91c4e07b"
        )
