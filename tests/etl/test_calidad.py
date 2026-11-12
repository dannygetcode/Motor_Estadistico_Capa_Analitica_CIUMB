"""etl.calidad (sección 4.2.2, INF-TRA-08): las reglas encuentran exactamente los defectos sembrados."""

from __future__ import annotations

from collections import Counter

import pandas as pd
import pytest

from ciumb_analitica.etl import calidad
from datos_sinteticos.generar import CATALOGO_ESTADOS, DEFECTOS, generar
from tests.conftest import PENDIENTE

pytestmark = PENDIENTE

DATOS = generar()
IDS = {
    "proyecto_investigacion": "id_proyecto",
    "practica": "id_practica",
    "convenio": "id_convenio",
    "empresa": "id_empresa",
}


def _evaluar(entidad: str) -> pd.DataFrame:
    filas = pd.DataFrame(DATOS.tablas[entidad]).set_index(IDS[entidad], drop=False)
    return calidad.evaluar(entidad, filas, catalogo_estados=CATALOGO_ESTADOS)


def _marcados(entidad: str, regla: str) -> set[int]:
    evaluacion = _evaluar(entidad)
    return set(evaluacion.index[evaluacion[regla]])


@pytest.mark.parametrize(
    ("entidad", "regla", "claves"),
    [
        ("proyecto_investigacion", calidad.FIN_ANTES_DE_INICIO, ["proyecto_fin_antes_inicio"]),
        ("proyecto_investigacion", calidad.PRESUPUESTO_NEGATIVO, ["proyecto_presupuesto_ejecutado_negativo"]),
        ("proyecto_investigacion", calidad.ESTADO_FUERA_DE_CATALOGO, ["proyecto_estado_fuera_catalogo"]),
        ("practica", calidad.FIN_ANTES_DE_INICIO, ["practica_fin_antes_inicio"]),
        ("practica", calidad.ESTADO_FUERA_DE_CATALOGO, ["practica_estado_fuera_catalogo"]),
        ("practica", calidad.SIN_EMPRESA, ["practica_sin_empresa"]),
        ("practica", calidad.SIN_TUTOR,
         ["practica_sin_tutor_academico", "practica_sin_tutor_empresarial", "practica_sin_tutor_ninguno"]),
        ("convenio", calidad.FIN_ANTES_DE_INICIO, ["convenio_fin_antes_inicio"]),
        ("convenio", calidad.ESTADO_FUERA_DE_CATALOGO, ["convenio_estado_fuera_catalogo"]),
        ("convenio", calidad.SIN_FECHA_FIN, ["convenio_sin_fecha_fin"]),
    ],
)  # fmt: skip
def test_cada_regla_marca_exactamente_los_defectos_sembrados(entidad, regla, claves):
    esperados = {i for clave in claves for i in DATOS.defectos[clave]}
    assert len(esperados) == sum(DEFECTOS[c] for c in claves)
    assert _marcados(entidad, regla) == esperados


def test_nit_repetido_marca_todas_las_filas_que_comparten_nit():
    marcados = _marcados("empresa", calidad.NIT_REPETIDO)
    assert set(DATOS.defectos["empresa_nit_repetido"]) <= marcados
    nits = Counter(e["nit"] for e in DATOS.tablas["empresa"])
    repetidos = {nit for nit, n in nits.items() if n > 1}
    assert marcados == {e["id_empresa"] for e in DATOS.tablas["empresa"] if e["nit"] in repetidos}
    assert len(marcados) - len(repetidos) == DEFECTOS["empresa_nit_repetido"]


def test_nit_se_compara_solo_por_digitos():
    filas = pd.DataFrame({"id_empresa": [1, 2, 3], "nit": ["900.123.456-7", "9001234567", "800111222-1"]})
    assert calidad.evaluar("empresa", filas, catalogo_estados=CATALOGO_ESTADOS)[calidad.NIT_REPETIDO].tolist() == [
        True, True, False,
    ]  # fmt: skip


def test_el_estado_se_compara_de_forma_exacta():
    filas = pd.DataFrame(
        {
            "id_convenio": [1, 2, 3, 4],
            "estado": ["vigente", "Vigente", "vigente ", None],
            "fecha_inicio": pd.to_datetime(["2026-01-01"] * 4),
            "fecha_fin": pd.to_datetime(["2026-12-31"] * 4),
        }
    )
    evaluacion = calidad.evaluar("convenio", filas, catalogo_estados=CATALOGO_ESTADOS)
    assert evaluacion[calidad.ESTADO_FUERA_DE_CATALOGO].tolist() == [False, True, True, True]


def test_marca_de_calidad():
    evaluacion = pd.DataFrame(
        {calidad.SIN_TUTOR: [False, True, True], calidad.FIN_ANTES_DE_INICIO: [False, False, True]}, index=[7, 8, 9]
    )
    marcas = calidad.marca(evaluacion)
    assert marcas.index.tolist() == [7, 8, 9]
    assert marcas.tolist() == [None, "sin_tutor", "fin_antes_de_inicio,sin_tutor"]


def test_una_entidad_sin_reglas_no_marca_nada():
    filas = pd.DataFrame(DATOS.tablas["consultoria"])
    assert calidad.evaluar("consultoria", filas, catalogo_estados=CATALOGO_ESTADOS).shape == (len(filas), 0)
