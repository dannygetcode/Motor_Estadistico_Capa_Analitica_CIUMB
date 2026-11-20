"""Entorno completo para las pruebas de orquestación y API: fuente sintética -> ETL -> `ana_`, y `rpt_` sembrado.

Todo en SQLite en memoria (tres bases: fuente, `ana_` de solo lectura para el servicio y `rpt_`). El ETL carga el
corte de octubre de 2026 y los cortes mensuales de 2025-01 a 2026-09 (P1, P3, P4 y P9 los necesitan).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pytest
from sqlalchemy import Engine, create_engine, insert
from sqlalchemy.pool import StaticPool

from ciumb_analitica.dw.esquema import metadatos_ana
from ciumb_analitica.etl import carga
from ciumb_analitica.fuentes import vistas
from ciumb_analitica.semantica.almacen import leer_capa, sembrar
from ciumb_analitica.semantica.modelos import CapaSemantica
from ciumb_analitica.trazabilidad.esquema import metadatos_rpt
from datos_sinteticos.generar import CATALOGO_ESTADOS, generar

SAL = "sal-de-prueba-api-1234567890"
HOY = date(2026, 11, 5)


@dataclass
class Entorno:
    ana: Engine
    rpt: Engine
    capa: CapaSemantica


def _motor(esquema: str) -> Engine:
    # TestClient atiende en otro hilo: la base en memoria se comparte entre hilos (solo en pruebas).
    motor = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    return motor.execution_options(schema_translate_map={esquema: None})


@pytest.fixture(scope="session")
def entorno() -> Entorno:
    datos = generar()
    origen = _motor(vistas.ESQUEMA_FUENTE)
    vistas.metadatos_fuente.create_all(origen)
    with origen.begin() as con:
        for tabla in vistas.metadatos_fuente.sorted_tables:
            columnas = {c.name for c in tabla.columns}
            con.execute(
                insert(tabla), [{k: v for k, v in f.items() if k in columnas} for f in datos.tablas[tabla.name]]
            )
    ana = _motor("ana_")
    metadatos_ana.create_all(ana)
    with origen.connect() as o, ana.begin() as d:
        resumenes = carga.ejecutar_etl(o, d, sal=SAL, hoy=HOY, catalogo_estados=CATALOGO_ESTADOS)
        resumenes += carga.cargar_cortes_historicos(
            o, d, sal=SAL, desde=date(2025, 1, 1), hasta=date(2026, 9, 30), catalogo_estados=CATALOGO_ESTADOS
        )
    assert all(r.error is None for r in resumenes)
    origen.dispose()
    rpt = _motor("rpt_")
    metadatos_rpt.create_all(rpt)
    with rpt.begin() as con:
        sembrar(con)
    with rpt.connect() as con:
        capa = leer_capa(con)
    return Entorno(ana=ana, rpt=rpt, capa=capa)
