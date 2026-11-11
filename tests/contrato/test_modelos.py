"""Contrato ciumb.informe/2.0.0: modelos, JSON Schema y filtro de PII (sección 4.4.3, Figura 12)."""

from __future__ import annotations

import copy

import jsonschema
import pytest
from pydantic import ValidationError

from ciumb_analitica.contrato.modelos import ID_CONTRATO, VERSION_CONTRATO, cargar_contrato
from ciumb_analitica.contrato.pii import ErrorPII, buscar_pii, depurar_texto
from tests.conftest import DIR_EJEMPLOS, DIR_FIXTURES, DIR_SCHEMAS, leer_json, rechazados

ESQUEMA = leer_json(DIR_SCHEMAS / "ciumb.informe-2.0.0.schema.json")
VALIDADOR = jsonschema.Draft202012Validator(ESQUEMA, format_checker=jsonschema.FormatChecker())

# El esquema los acepta; los bloquea el filtro de PII.
SOLO_PII = {"contrato_pii_correo", "contrato_pii_nit"}


def _valido() -> dict:
    return leer_json(DIR_FIXTURES / "contrato_p03.json")


def test_version():
    assert VERSION_CONTRATO == "2.0.0" and ID_CONTRATO == "ciumb.informe/2.0.0"
    assert ESQUEMA["properties"]["contrato"]["const"] == ID_CONTRATO


def test_fixture_valido_cumple_modelo_esquema_y_pii():
    datos = _valido()
    contrato = cargar_contrato(datos)
    VALIDADOR.validate(datos)
    assert contrato.secciones[0].indicadores[0].valor == 412.6
    assert contrato.secciones[0].indicadores[1].mes == "2026-06"


def test_figura_12_solo_falla_por_la_huella_truncada_d15():
    datos = leer_json(DIR_EJEMPLOS / "fig12_contrato_p_fig10.json")
    with pytest.raises(ValidationError) as error:
        cargar_contrato(datos)
    assert [e["loc"] for e in error.value.errors()] == [("huella_datos",)]


@pytest.mark.parametrize(("nombre", "caso"), rechazados("contrato"), ids=lambda x: x if isinstance(x, str) else "")
def test_rechazados(nombre, caso):
    if nombre in SOLO_PII:
        VALIDADOR.validate(caso["documento"])
        with pytest.raises(ErrorPII):
            cargar_contrato(caso["documento"])
    else:
        with pytest.raises(ValidationError):
            cargar_contrato(caso["documento"])
        assert not VALIDADOR.is_valid(caso["documento"])


def test_metodo_del_indicador_reemplaza_al_de_la_seccion_d07():
    datos = _valido()
    datos["secciones"][0]["indicadores"][1]["metodo"] = "máximo mensual"
    seccion = cargar_contrato(datos).secciones[0]
    assert seccion.indicadores[0].metodo is None and seccion.metodo.startswith("suma mensual")
    assert seccion.indicadores[1].metodo == "máximo mensual"


def test_indicadores_por_grupo():
    datos = _valido()
    datos["secciones"][0]["indicadores"] = [
        {"id": "proyectos", "valor": 12, "grupo": {"facultad": "Ingeniería", "estado": "en_ejecucion"}},
        {"id": "proyectos", "valor": 7, "grupo": {"facultad": "Ciencias Sociales", "estado": "en_ejecucion"}},
    ]
    assert len(cargar_contrato(datos).secciones[0].indicadores) == 2
    datos["secciones"][0]["indicadores"].append(copy.deepcopy(datos["secciones"][0]["indicadores"][0]))
    with pytest.raises(ValidationError):
        cargar_contrato(datos)


@pytest.mark.parametrize(
    "mutar",
    [
        lambda d: d["secciones"].clear(),
        lambda d: d["secciones"][0]["indicadores"].clear(),
        lambda d: d["secciones"][0]["indicadores"][0].update(valor="412,6"),
        lambda d: d["secciones"][0]["indicadores"][0].update(valor=None),
        lambda d: d["secciones"][0]["indicadores"][0].update(n=-1),
        lambda d: d["secciones"][0]["indicadores"][0].update(valor_p=1.2),
        lambda d: d["secciones"][0]["indicadores"][1].update(mes="2026-13"),
        lambda d: d["secciones"][0].pop("metodo"),
        lambda d: d["secciones"].append(copy.deepcopy(d["secciones"][0])),
        lambda d: d["especificacion"].update(id="42"),
        lambda d: d["especificacion"]["grafico"].update(tipo="caja"),
        lambda d: d["periodo"].pop("corte"),
        lambda d: d.update(registros=[{"id_proyecto": 1}]),
        lambda d: d.pop("huella_datos"),
    ],
)
def test_mutaciones_invalidas(mutar):
    datos = _valido()
    mutar(datos)
    with pytest.raises(ValidationError):
        cargar_contrato(datos)


@pytest.mark.parametrize(
    ("texto", "patron"),
    [
        ("escribir a daniel.b@umb.edu.co", "correo"),
        ("NIT 900123456-7", "nit"),
        ("NIT 900.123.456-7", "nit"),
        ("cc 1023456789", "documento"),
        ("documento 1.023.456.789", "documento"),
        ("c.c. 52345678", "documento"),
    ],
)
def test_patrones_de_pii_detectan(texto, patron):
    assert patron in {h.patron for h in buscar_pii({"metodo": texto})}
    assert "[dato retirado]" in depurar_texto(texto)


@pytest.mark.parametrize(
    "texto",
    [
        "suma mensual; variación frente al mismo periodo del año anterior",
        "periodo 2025-01-01 a 2026-10-31",
        "n = 118 consultorías; 412,6 millones COP",
        "INF-INV-02 · T1 a T3 de 2026",
        "chi-cuadrado con 6 grados de libertad, alfa 0,05",
        "2026-2",
    ],
)
def test_patrones_de_pii_no_marcan_texto_analitico(texto):
    assert buscar_pii({"metodo": texto}) == []


def test_pii_en_claves_y_listas_anidadas():
    hallazgos = buscar_pii({"a": [{"b": ["x", "y@z.co"]}], "u@v.co": 1})
    assert {h.ruta for h in hallazgos} == {"$.a[0].b[1]", "$.u@v.co (clave)"}


def test_error_pii_no_repite_el_dato():
    datos = _valido()
    datos["secciones"][0]["advertencias"] = ["contactar a persona.real@correo.com"]
    with pytest.raises(ErrorPII) as error:
        cargar_contrato(datos)
    assert "persona.real" not in str(error.value)
    assert "correo" in str(error.value)
