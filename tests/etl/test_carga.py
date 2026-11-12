"""etl.carga: huella de fila y detección de cambios (carga incremental, D-17).

Las funciones que tocan la base (`cargar_dimensiones`, `cargar_hechos`, `recalcular_agregados`, `ejecutar_etl`)
necesitan la fuente `ciumb` y `ana_` en PostgreSQL: sus pruebas de integración quedan por escribir junto con
la implementación (ver docs/handoff.md).
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

import pandas as pd

from ciumb_analitica.etl import carga
from tests.conftest import PENDIENTE

pytestmark = PENDIENTE

FILA = {"id_convenio": 7, "id_empresa": 3, "tipo": "marco", "fecha_fin": date(2026, 12, 31), "valor": Decimal("1.50")}


def test_huella_de_fila_es_un_sha256_estable():
    huella = carga.huella_fila(FILA)
    assert re.fullmatch(r"[0-9a-f]{64}", huella)
    assert carga.huella_fila(dict(reversed(list(FILA.items())))) == huella  # no depende del orden de las claves
    assert carga.huella_fila(FILA | {"valor": Decimal("1.5")}) == huella  # 1.50 y 1.5 son el mismo dato


def test_huella_de_fila_cambia_con_cualquier_campo():
    base = carga.huella_fila(FILA)
    for cambio in (
        {"tipo": "especifico"},
        {"fecha_fin": date(2027, 1, 1)},
        {"valor": Decimal("1.51")},
        {"id_empresa": 4},
    ):
        assert carga.huella_fila(FILA | cambio) != base
    assert carga.huella_fila(FILA | {"tipo": None}) != carga.huella_fila(FILA | {"tipo": ""})
    assert carga.huella_fila(FILA | {"tipo": None}) != carga.huella_fila(FILA | {"tipo": "None"})


def test_filas_cambiadas_devuelve_nuevas_y_modificadas():
    filas = pd.DataFrame(
        [
            {"id_convenio": 1, "tipo": "marco", "estado": "vigente"},
            {"id_convenio": 2, "tipo": "marco", "estado": "vencido"},
            {"id_convenio": 3, "tipo": "especifico", "estado": "vigente"},
        ]
    )
    previas = {
        1: carga.huella_fila(filas.iloc[0].to_dict()),
        2: carga.huella_fila(filas.iloc[1].to_dict() | {"estado": "vigente"}),  # cambió de estado
    }
    cambiadas = carga.filas_cambiadas(filas, "id_convenio", previas)
    assert cambiadas["id_convenio"].tolist() == [2, 3]
    assert cambiadas["_huella"].tolist() == [carga.huella_fila(filas.iloc[i].to_dict()) for i in (1, 2)]
    assert carga.filas_cambiadas(filas, "id_convenio", {}).shape[0] == 3
    todas = {i + 1: carga.huella_fila(filas.iloc[i].to_dict()) for i in range(3)}
    assert carga.filas_cambiadas(filas, "id_convenio", todas).empty
