"""Los JSON Schema versionados en `schemas/` deben coincidir con los modelos Pydantic."""

from __future__ import annotations

import jsonschema
import pytest

from ciumb_analitica.exportar_esquemas import generar
from tests.conftest import DIR_SCHEMAS, leer_json


@pytest.mark.parametrize("nombre", sorted(generar()))
def test_esquema_exportado_esta_al_dia(nombre):
    en_disco = (DIR_SCHEMAS / nombre).read_text(encoding="utf-8")
    assert en_disco == generar()[nombre], (
        f"schemas/{nombre} está desfasado: corre `uv run python -m ciumb_analitica.exportar_esquemas`. "
        "Si cambió el contrato, hay que subir su versión (invariante 8)."
    )


@pytest.mark.parametrize("nombre", sorted(generar()))
def test_esquema_es_json_schema_valido_y_cerrado(nombre):
    esquema = leer_json(DIR_SCHEMAS / nombre)
    jsonschema.Draft202012Validator.check_schema(esquema)
    assert esquema["additionalProperties"] is False
    for definicion in esquema["$defs"].values():
        if definicion.get("type") == "object":
            assert definicion["additionalProperties"] is False, definicion.get("title")
