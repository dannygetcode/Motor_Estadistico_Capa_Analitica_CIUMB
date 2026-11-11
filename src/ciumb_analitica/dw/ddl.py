"""Genera el DDL de PostgreSQL de los esquemas `ana_` y `rpt_` y los permisos del usuario de solo lectura.

Uso: `uv run python -m ciumb_analitica.dw.ddl` (escribe `sql/ana_rpt_postgresql.sql`).
`tests/dw/test_esquema.py` falla si el archivo queda desfasado respecto de los metadatos.

El motor del CIUMB no está confirmado: los metadatos son agnósticos y este archivo es solo el dialecto de
desarrollo. Para otro motor basta compilar los mismos metadatos con su dialecto.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from ciumb_analitica.dw.esquema import ESQUEMA_ANA, metadatos_ana
from ciumb_analitica.trazabilidad.esquema import ESQUEMA_RPT, metadatos_rpt

RUTA_SQL = Path(__file__).resolve().parents[3] / "sql" / "ana_rpt_postgresql.sql"

ROL_LECTOR = "ciumb_lector"

_CABECERA = f"""\
-- =====================================================================
-- Esquemas {ESQUEMA_ANA} (datawarehouse) y {ESQUEMA_RPT} (servicio de informes) - PostgreSQL
-- GENERADO por `uv run python -m ciumb_analitica.dw.ddl`. No editar a mano:
-- la fuente son src/ciumb_analitica/dw/esquema.py y trazabilidad/esquema.py.
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS {ESQUEMA_ANA};
CREATE SCHEMA IF NOT EXISTS {ESQUEMA_RPT};
"""

_PERMISOS = f"""
-- ---------------------------------------------------------------------
-- Usuario de solo lectura del motor (invariante 3): solo SELECT y solo sobre {ESQUEMA_ANA}.
-- El rol se crea sin contraseña; se asigna fuera de git:
--   ALTER ROLE {ROL_LECTOR} LOGIN PASSWORD '...';
-- ---------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROL_LECTOR}') THEN
        CREATE ROLE {ROL_LECTOR} NOLOGIN;
    END IF;
END
$$;
REVOKE ALL ON SCHEMA {ESQUEMA_RPT} FROM {ROL_LECTOR};
GRANT USAGE ON SCHEMA {ESQUEMA_ANA} TO {ROL_LECTOR};
GRANT SELECT ON ALL TABLES IN SCHEMA {ESQUEMA_ANA} TO {ROL_LECTOR};
ALTER DEFAULT PRIVILEGES IN SCHEMA {ESQUEMA_ANA} GRANT SELECT ON TABLES TO {ROL_LECTOR};
ALTER ROLE {ROL_LECTOR} SET default_transaction_read_only = on;
ALTER ROLE {ROL_LECTOR} SET statement_timeout = '30s';
"""  # noqa: S608 - DDL estático, sin datos externos


def generar_sql() -> str:
    dialecto = postgresql.dialect()
    partes = [_CABECERA]
    for metadatos in (metadatos_ana, metadatos_rpt):
        for tabla in metadatos.sorted_tables:
            partes.append(str(CreateTable(tabla).compile(dialect=dialecto)).strip() + ";\n")
    partes.append(_PERMISOS)
    return "\n".join(partes)


def main() -> None:
    RUTA_SQL.parent.mkdir(exist_ok=True)
    RUTA_SQL.write_text(generar_sql(), encoding="utf-8", newline="\n")
    print(f"escrito {RUTA_SQL.relative_to(RUTA_SQL.parents[1])}")


if __name__ == "__main__":
    main()
