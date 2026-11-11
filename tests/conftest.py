"""Utilidades compartidas de las pruebas: lectura de fixtures y ejemplos del diseño."""

from __future__ import annotations

import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DIR_SCHEMAS = RAIZ / "schemas"
DIR_FIXTURES = DIR_SCHEMAS / "fixtures"
DIR_EJEMPLOS = DIR_SCHEMAS / "ejemplos"

IDS_PROMPTS = [f"p{i:02d}" for i in range(1, 11)]


def leer_json(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def fixture_prompt(nombre: str) -> dict:
    """Fixture de la Tabla 22: {id, prompt, fecha_referencia, spec, esperado}."""
    return leer_json(DIR_FIXTURES / f"{nombre}.json")


def rechazados(interfaz: str) -> list[tuple[str, dict]]:
    """Ejemplos rechazados de `schemas/fixtures/rechazados/` para 'spec' o 'contrato'."""
    return [(r.stem, leer_json(r)) for r in sorted((DIR_FIXTURES / "rechazados").glob(f"{interfaz}_*.json"))]
