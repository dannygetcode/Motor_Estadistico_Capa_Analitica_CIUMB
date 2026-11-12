"""Utilidades compartidas de las pruebas: lectura de fixtures y ejemplos del diseño."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

RAIZ = Path(__file__).resolve().parents[1]
DIR_SCHEMAS = RAIZ / "schemas"
DIR_FIXTURES = DIR_SCHEMAS / "fixtures"
DIR_EJEMPLOS = DIR_SCHEMAS / "ejemplos"

IDS_PROMPTS = [f"p{i:02d}" for i in range(1, 11)]

# Marca de las pruebas del relevo: definen el comportamiento esperado de funciones que aún no existen.
# `strict=True`: cuando la función se implemente y la prueba pase, pytest falla hasta que se quite la marca.
PENDIENTE = pytest.mark.xfail(raises=NotImplementedError, strict=True, reason="pendiente de implementar")


def leer_json(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def fixture_prompt(nombre: str) -> dict:
    """Fixture de la Tabla 22: {id, prompt, fecha_referencia, spec, esperado}."""
    return leer_json(DIR_FIXTURES / f"{nombre}.json")


def rechazados(interfaz: str) -> list[tuple[str, dict]]:
    """Ejemplos rechazados de `schemas/fixtures/rechazados/` para 'spec' o 'contrato'."""
    return [(r.stem, leer_json(r)) for r in sorted((DIR_FIXTURES / "rechazados").glob(f"{interfaz}_*.json"))]


# --- Base de datos de prueba: SQLite en memoria con los esquemas ana_ y rpt_ ------------------------------------

SIN_ESQUEMAS = {"ana_": None, "rpt_": None}


@pytest.fixture
def motor_bd():
    """Motor SQLite en memoria con todas las tablas de `ana_` y `rpt_` (los esquemas se traducen a ninguno)."""
    from ciumb_analitica.dw.esquema import metadatos_ana
    from ciumb_analitica.trazabilidad.esquema import metadatos_rpt

    motor = create_engine("sqlite://", poolclass=StaticPool).execution_options(schema_translate_map=SIN_ESQUEMAS)
    metadatos_ana.create_all(motor)
    metadatos_rpt.create_all(motor)
    yield motor
    motor.dispose()
