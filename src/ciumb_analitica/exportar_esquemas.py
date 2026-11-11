"""Exporta el JSON Schema de la spec y del contrato a `schemas/`.

Uso: `uv run python -m ciumb_analitica.exportar_esquemas`
Los archivos exportados están bajo control de versiones; `tests/test_esquemas.py` falla si quedan desfasados.
"""

from __future__ import annotations

import json
from pathlib import Path

from ciumb_analitica.contrato.modelos import Contrato
from ciumb_analitica.spec.modelos import Especificacion

DIR_SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"

ESQUEMAS = {
    "ciumb.spec-1.0.schema.json": (Especificacion, "urn:ciumb:spec:1.0"),
    "ciumb.informe-2.0.0.schema.json": (Contrato, "urn:ciumb:informe:2.0.0"),
}


def generar() -> dict[str, str]:
    """Devuelve {nombre de archivo: texto JSON} con el esquema de cada interfaz de frontera."""
    salida = {}
    for nombre, (modelo, id_esquema) in ESQUEMAS.items():
        esquema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": id_esquema,
            **modelo.model_json_schema(mode="validation"),
        }
        salida[nombre] = json.dumps(esquema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return salida


def main() -> None:
    for nombre, texto in generar().items():
        (DIR_SCHEMAS / nombre).write_text(texto, encoding="utf-8", newline="\n")
        print(f"escrito schemas/{nombre}")


if __name__ == "__main__":
    main()
