"""ciumb.spec/1.0: modelos Pydantic y JSON Schema exportado (Tabla 20)."""

from __future__ import annotations

import jsonschema
import pytest
from pydantic import ValidationError

from ciumb_analitica.spec.modelos import METODOS_ANALISIS, Especificacion, cargar_especificacion
from tests.conftest import DIR_EJEMPLOS, DIR_SCHEMAS, IDS_PROMPTS, fixture_prompt, leer_json, rechazados

ESQUEMA = leer_json(DIR_SCHEMAS / "ciumb.spec-1.0.schema.json")
VALIDADOR = jsonschema.Draft202012Validator(ESQUEMA, format_checker=jsonschema.FormatChecker())

# Rechazos que dependen de reglas entre campos: el modelo los detecta, el JSON Schema no.
SOLO_MODELO = {"spec_coordinador_sin_facultad"}


@pytest.mark.parametrize("nombre", IDS_PROMPTS)
def test_fixture_p1_p10_cumple_modelo_y_esquema(nombre):
    spec = fixture_prompt(nombre)["spec"]
    cargar_especificacion(spec)
    VALIDADOR.validate(spec)


@pytest.mark.parametrize(
    "archivo", ["fig13_spec_p2_torta_practicas", "fig14_spec_p4_calor_hitos_chi2", "fig15_spec_p6_plantilla_inf_inv_02"]
)
def test_figuras_del_diseno_son_validas_sin_modificarlas(archivo):
    spec = leer_json(DIR_EJEMPLOS / f"{archivo}.json")
    cargar_especificacion(spec)
    VALIDADOR.validate(spec)


@pytest.mark.parametrize(("nombre", "caso"), rechazados("spec"), ids=lambda x: x if isinstance(x, str) else "")
def test_rechazados(nombre, caso):
    with pytest.raises(ValidationError):
        cargar_especificacion(caso["documento"])
    if nombre not in SOLO_MODELO:
        assert not VALIDADOR.is_valid(caso["documento"])


def test_hay_al_menos_un_rechazado():
    assert len(rechazados("spec")) >= 5


def _base() -> dict:
    return fixture_prompt("p03")["spec"]


def test_valores_por_defecto():
    spec = cargar_especificacion(
        {
            "esquema": "ciumb.spec/1.0",
            "origen": "prompt",
            "metricas": [{"id": "proyectos"}],
            "alcance": {"rol": "directivo"},
        }
    )
    assert spec.base is None and spec.dimensiones == [] and spec.filtros == []
    assert spec.periodo is None and spec.analisis is None and spec.grafico is None and spec.salida is None


def test_p4_variables_fuera_de_dimensiones_es_valido_d06():
    spec = cargar_especificacion(fixture_prompt("p04")["spec"])
    assert spec.analisis.variables == ["facultad", "estado_hito"]
    assert "estado_hito" not in [d.id for d in spec.dimensiones]


def test_p2_sin_periodo_es_valido_d08():
    assert cargar_especificacion(fixture_prompt("p02")["spec"]).periodo is None


@pytest.mark.parametrize(
    "cambio",
    [
        {"esquema": "ciumb.spec/2.0"},
        {"origen": "plantilla_base", "base": None},
        {"base": "INF-XX-1"},
        {"metricas": []},
        {"metricas": [{"id": "facturacion"}, {"id": "facturacion"}]},
        {"metricas": [{"id": "Facturacion"}]},
        {"metricas": [{"id": "facturacion", "agregacion": "maximo"}]},
        {"dimensiones": [{"id": "tiempo", "granularidad": "dia"}]},
        {"periodo": {"desde": "2026-10-31", "hasta": "2026-01-01"}},
        {"periodo": {"desde": "31/10/2026", "hasta": "2026-12-01"}},
        {"filtros": [{"campo": "facultad", "op": "LIKE", "valor": "%"}]},
        {"filtros": [{"campo": "facultad", "op": "en", "valor": "Ingeniería"}]},
        {"filtros": [{"campo": "facultad", "op": "=", "valor": ["a", "b"]}]},
        {"filtros": [{"campo": "anio", "op": "entre", "valor": [2024]}]},
        {"filtros": [{"campo": "facultad", "op": "=", "valor": {"$ne": 1}}]},
        {"filtros": [{"campo": "facultad", "op": "=", "valor": None}]},
        {"analisis": {"metodo": "chi_cuadrado", "variables": ["facultad"]}},
        {"analisis": {"metodo": "chi_cuadrado", "variables": ["facultad", "facultad"]}},
        {"analisis": {"metodo": "spearman", "variables": ["a", "b"], "alfa": 1.5}},
        {"analisis": {"metodo": "frecuencias", "relativas": "si"}},
        {"analisis": {"metodo": "frecuencias", "alfa": 0.05}},
        {"analisis": {"metodo": "pronostico", "horizonte": 0}},
        {"analisis": {"metodo": "segmentacion", "k": 1}},
        {"analisis": {"metodo": "descriptiva", "atipicos": {"metodo": "DBSCAN"}}},
        {"grafico": {"tipo": "caja"}},
        {"grafico": {"tipo": "torta", "max_sectores": 7}},
        {"grafico": {"tipo": "torta", "origen": "ia"}},
        {"alcance": {"rol": "estudiante"}},
        {"alcance": {"rol": "tutor"}},
        {"alcance": {"rol": "directivo", "sql": "1=1"}},
        {"salida": {"formatos": ["pptx"]}},
    ],
    ids=lambda c: next(iter(c)) + ":" + str(next(iter(c.values())))[:40],
)
def test_cambios_invalidos(cambio):
    spec = _base() | cambio
    with pytest.raises(ValidationError):
        cargar_especificacion(spec)


@pytest.mark.parametrize("metodo", METODOS_ANALISIS)
def test_todos_los_metodos_de_la_tabla_20_tienen_modelo(metodo):
    analisis = {"metodo": metodo}
    if metodo in ("pearson", "spearman", "chi_cuadrado", "t_student", "mann_whitney"):
        analisis["variables"] = ["a", "b"]
    assert cargar_especificacion(_base() | {"analisis": analisis}).analisis.metodo == metodo


def test_la_spec_es_inmutable():
    spec = cargar_especificacion(_base())
    with pytest.raises(ValidationError):
        spec.origen = "guardada"


def test_serializacion_estable_ida_y_vuelta():
    spec = cargar_especificacion(_base())
    volcado = spec.model_dump(mode="json")
    assert cargar_especificacion(volcado) == spec
    assert Especificacion.model_validate_json(spec.model_dump_json()) == spec
