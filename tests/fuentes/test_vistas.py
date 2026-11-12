"""fuentes.vistas (sección 4.2, Tabla 13): solo lectura, sin campos sensibles, con nombres canónicos."""

from __future__ import annotations

import re

import pytest
from sqlalchemy.dialects import postgresql

from ciumb_analitica.fuentes import vistas
from tests.conftest import PENDIENTE, RAIZ

pytestmark = PENDIENTE

DDL_FUENTE = (RAIZ / "datos_sinteticos" / "ddl.sql").read_text(encoding="utf-8")


def _sql(entidad: str) -> str:
    return str(vistas.vista(entidad).compile(dialect=postgresql.dialect()))


@pytest.mark.parametrize("entidad", vistas.ENTIDADES)
def test_cada_vista_es_un_select_sobre_la_fuente_sin_campos_sensibles(entidad):
    sql = _sql(entidad)
    assert sql.lstrip().upper().startswith("SELECT") and f"{vistas.ESQUEMA_FUENTE}.{entidad}" in sql
    assert "*" not in sql  # columnas explícitas: una columna nueva en la fuente no se extrae sola
    assert not re.search(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE)\b", sql, re.I)
    for prohibida in vistas.COLUMNAS_PROHIBIDAS:
        assert not re.search(rf"\b{prohibida}\b", sql), prohibida
    assert not set(vistas.columnas(entidad)) & vistas.COLUMNAS_PROHIBIDAS


@pytest.mark.parametrize("entidad", vistas.ENTIDADES)
def test_cada_vista_cubre_una_tabla_del_modelo_inferido(entidad):
    assert re.search(rf"CREATE TABLE {entidad} \(", DDL_FUENTE)
    assert len(vistas.columnas(entidad)) >= 2


def test_la_vista_de_usuario_solo_trae_lo_analitico():
    assert set(vistas.columnas("usuario")) == {
        "id_usuario", "id_rol", "estado", "fecha_creacion", "ultimo_acceso", "fecha_vence_contrasena",
    }  # fmt: skip


def test_la_vista_de_empresa_lee_el_nit_solo_para_hacer_el_hash():
    columnas = set(vistas.columnas("empresa"))
    assert "nit" in columnas and "razon_social" not in columnas
    assert {"sector", "ciudad", "tipo", "fecha_registro", "estado"} <= columnas


def test_fecha_de_modificacion_d04():
    con_fecha = {e for e in vistas.ENTIDADES if vistas.tiene_fecha_modificacion(e)}
    assert con_fecha == {"proyecto_investigacion", "practica"}
    assert "fecha_modificacion" in vistas.columnas("practica")
    assert "fecha_modificacion" not in vistas.columnas("convenio")


def test_entidad_desconocida():
    with pytest.raises(KeyError):
        vistas.vista("contrasenas")
