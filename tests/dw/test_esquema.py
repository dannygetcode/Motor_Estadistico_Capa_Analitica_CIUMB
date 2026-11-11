"""Esquema ana_: matriz de bus (Tabla 15), dimensiones (Tabla 16), hechos (Tabla 17) y DDL generado."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import func, insert, inspect, select

from ciumb_analitica.dw import esquema as dw
from ciumb_analitica.dw.ddl import ROL_LECTOR, RUTA_SQL, generar_sql
from ciumb_analitica.dw.tiempo import filas_dim_tiempo, fin_de_mes, sk_fecha, ultimo_mes_cerrado

# Tabla 15, transcrita. Columnas: tiempo, macroproyecto, línea y programa, estado, persona y rol, empresa,
# tipo de convenio.
MATRIZ_DE_BUS = {
    "hecho_macroproyecto": {"dim_tiempo", "dim_macroproyecto", "dim_estado"},
    "hecho_proyecto": {"dim_tiempo", "dim_macroproyecto", "dim_linea_programa", "dim_estado"},
    "hecho_hito": {"dim_tiempo", "dim_estado"},
    "hecho_practica": {
        "dim_tiempo", "dim_macroproyecto", "dim_linea_programa", "dim_estado", "dim_persona_rol", "dim_empresa",
    },
    "hecho_convenio": {"dim_tiempo", "dim_estado", "dim_empresa", "dim_tipo_convenio"},
    "hecho_consultoria": {"dim_tiempo", "dim_estado", "dim_persona_rol", "dim_empresa"},
    "hecho_acceso_diario": {"dim_tiempo", "dim_persona_rol"},
}  # fmt: skip

MEDIDAS = {  # Tabla 17 y Figuras 7-8
    "hecho_macroproyecto": {"pct_avance", "desviacion_dias", "n_proyectos", "n_practicas"},
    "hecho_proyecto": {
        "presupuesto_asignado", "presupuesto_ejecutado", "pct_ejecucion", "n_integrantes", "n_hitos",
        "n_hitos_atrasados", "dias_retraso_promedio", "dias_creacion_aprobacion",
    },
    "hecho_hito": {"dias_retraso", "a_tiempo"},
    "hecho_practica": {"duracion_dias", "tareas_asignadas", "tareas_cumplidas", "finalizada"},
    "hecho_convenio": {"duracion_dias", "dias_para_vencer", "renovado", "docs_completos", "n_actividades"},
    "hecho_consultoria": {"valor_facturado", "satisfaccion", "n_consultores", "duracion_dias"},
    "hecho_acceso_diario": {"n_accesos", "n_fallidos", "bloqueos"},
}  # fmt: skip

TIPOS = {  # Tabla 17
    "hecho_macroproyecto": dw.INSTANTANEA_PERIODICA,
    "hecho_proyecto": dw.INSTANTANEA_PERIODICA,
    "hecho_hito": dw.TRANSACCION,
    "hecho_practica": dw.INSTANTANEA_ACUMULATIVA,
    "hecho_convenio": dw.INSTANTANEA_PERIODICA,
    "hecho_consultoria": dw.INSTANTANEA_ACUMULATIVA,
    "hecho_acceso_diario": dw.TRANSACCION,
}


def _dimensiones_de(hecho) -> set[str]:
    return {fk.column.table.name for col in hecho.columns for fk in col.foreign_keys}


@pytest.mark.parametrize("nombre", sorted(MATRIZ_DE_BUS))
def test_matriz_de_bus_tabla_15(nombre):
    assert _dimensiones_de(dw.tabla(nombre)) == MATRIZ_DE_BUS[nombre]


@pytest.mark.parametrize("nombre", sorted(MEDIDAS))
def test_medidas_y_tipo_tabla_17(nombre):
    hecho = dw.tabla(nombre)
    assert MEDIDAS[nombre] <= set(hecho.c.keys())
    assert hecho.info["tipo"] == TIPOS[nombre]
    assert hecho.info["col_tiempo"] in hecho.c
    assert set(hecho.info["grano"]) <= set(hecho.c.keys())


def test_hay_siete_hechos_y_siete_dimensiones():
    assert {h.name for h in dw.HECHOS_DW} == set(MATRIZ_DE_BUS)
    assert len(dw.DIMENSIONES_DW) == 7


def test_dimensiones_tabla_16_y_decisiones():
    assert {"fecha", "dia", "mes", "nombre_mes", "trimestre", "semestre", "anio", "periodo_academico"} <= set(
        dw.dim_tiempo.c.keys()
    )  # D-09
    assert {"sk_coordinador", "vigente_desde", "vigente_hasta"} <= set(dw.dim_macroproyecto.c.keys())  # D-10
    assert {"linea_investigacion", "programa", "facultad"} <= set(dw.dim_linea_programa.c.keys())
    assert {"modulo", "estado", "es_final"} <= set(dw.dim_estado.c.keys())
    assert {"seudonimo", "rol", "tipo_participacion"} <= set(dw.dim_persona_rol.c.keys())
    assert {"sector", "ciudad", "tipo", "segmento_actividad", "nit_hash"} <= set(dw.dim_empresa.c.keys())


def test_ninguna_columna_guarda_pii_en_claro():
    prohibidas = {"nombre_completo", "documento", "correo", "contrasena_hash", "nit", "razon_social", "titulo"}
    for tabla in dw.metadatos_ana.tables.values():
        assert not prohibidas & set(tabla.c.keys()), tabla.name


def test_agregado_de_proyectos_cubre_un_subconjunto_del_hecho():
    assert _dimensiones_de(dw.agg_proyecto_linea_mes) <= MATRIZ_DE_BUS["hecho_proyecto"]
    assert dw.agg_proyecto_linea_mes.info["agregado_de"] == "hecho_proyecto"


def test_tabla_fuera_de_la_lista_blanca():
    with pytest.raises(KeyError):
        dw.tabla("usuario")


def test_las_tablas_se_crean_y_dim_tiempo_se_llena(motor_bd):
    nombres = set(inspect(motor_bd).get_table_names())
    assert {t.name for t in dw.metadatos_ana.tables.values()} <= nombres
    assert {"rpt_metrica", "rpt_dimension", "rpt_compatibilidad", "rpt_validacion", "rpt_especificacion"} <= nombres
    with motor_bd.begin() as con:
        con.execute(insert(dw.dim_tiempo), filas_dim_tiempo(date(2026, 1, 1), date(2026, 12, 31)))
        assert con.scalar(select(func.count()).select_from(dw.dim_tiempo)) == 365
        fila = con.execute(select(dw.dim_tiempo).where(dw.dim_tiempo.c.sk_fecha == 20260815)).mappings().one()
    assert (fila["trimestre"], fila["semestre"], fila["periodo_academico"], fila["nombre_mes"]) == (
        3, 2, "2026-2", "agosto",
    )  # fmt: skip


def test_dim_tiempo_completa_2015_a_2030():
    filas = filas_dim_tiempo()
    assert len(filas) == (date(2030, 12, 31) - date(2015, 1, 1)).days + 1
    assert filas[0]["sk_fecha"] == 20150101 and filas[-1]["sk_fecha"] == 20301231


def test_utilidades_de_fecha():
    assert sk_fecha(date(2026, 3, 9)) == 20260309
    assert fin_de_mes(date(2024, 2, 10)) == date(2024, 2, 29)
    assert fin_de_mes(date(2026, 12, 1)) == date(2026, 12, 31)
    assert ultimo_mes_cerrado(date(2026, 11, 5)) == date(2026, 10, 31)
    assert ultimo_mes_cerrado(date(2026, 1, 15)) == date(2025, 12, 31)


def test_ddl_postgresql_esta_al_dia_y_restringe_al_lector():
    sql = generar_sql()
    assert RUTA_SQL.read_text(encoding="utf-8") == sql, "corre `uv run python -m ciumb_analitica.dw.ddl`"
    assert "CREATE SCHEMA IF NOT EXISTS ana_" in sql and "CREATE TABLE ana_.hecho_proyecto" in sql
    assert "CREATE TABLE rpt_.rpt_validacion" in sql
    assert f"GRANT SELECT ON ALL TABLES IN SCHEMA ana_ TO {ROL_LECTOR}" in sql
    permisos = sql[sql.index("Usuario de solo lectura") :]
    concesiones = [linea for linea in permisos.splitlines() if "GRANT" in linea and not linea.startswith("--")]
    assert len(concesiones) == 3
    assert all("ana_" in linea and "rpt_" not in linea for linea in concesiones)
    assert all(("SELECT" in linea) or ("USAGE" in linea) for linea in concesiones)
