"""Datawarehouse mínimo en SQLite para probar el compilador contra cálculos independientes con pandas."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from sqlalchemy import insert

from ciumb_analitica.dw import esquema as dw
from ciumb_analitica.dw.tiempo import filas_dim_tiempo, sk_fecha
from ciumb_analitica.seudonimo import seudonimizar

SAL = "sal-de-prueba-0123456789"
CORTES = [date(2025, 10, 31), date(2026, 7, 31), date(2026, 8, 31), date(2026, 9, 30), date(2026, 10, 31)]

LINEAS = [  # sk_linea, id_linea, id_programa, linea, programa, facultad
    (1, 10, 1, "Analítica de datos", "Ingeniería de Software", "Ingeniería"),
    (2, 11, 2, "Internet de las cosas", "Ingeniería Electrónica", "Ingeniería"),
    (3, 12, 3, "Salud mental", "Psicología", "Ciencias Sociales"),
    (4, None, 1, "No aplica", "Ingeniería de Software", "Ingeniería"),
    (5, None, 3, "No aplica", "Psicología", "Ciencias Sociales"),
    (6, None, 2, "No aplica", "Ingeniería Electrónica", "Ingeniería"),
]
ESTADOS = [(1, "investigacion", "en_ejecucion", 0), (2, "investigacion", "finalizado", 1),
           (3, "practicas", "en_curso", 0), (4, "practicas", "finalizada", 1),
           (5, "consultorias", "finalizada", 1), (6, "convenios", "vigente", 0)]  # fmt: skip


def _proyectos() -> pd.DataFrame:
    filas = []
    for k, corte in enumerate(CORTES):
        for p in range(1, 10):  # 9 proyectos
            if corte.year == 2025 and p > 5:
                continue  # en 2025 solo existían cinco
            linea = (p - 1) % 3 + 1
            asignado = 1000.0 * p
            filas.append(
                {
                    "sk_fecha_corte": sk_fecha(corte),
                    "id_proyecto": p,
                    "sk_macroproyecto": None,
                    "sk_linea": linea,
                    "sk_estado": 2 if (p % 4 == 0 and k == len(CORTES) - 1) else 1,
                    "presupuesto_asignado": asignado,
                    "presupuesto_ejecutado": round(asignado * min(1.0, 0.1 * (k + 1) + 0.03 * p), 2),
                    "pct_ejecucion": None,
                    "n_integrantes": 2 + p % 3,
                    "n_hitos": 4 + p,
                    "n_hitos_atrasados": (p + k) % 4,
                    "dias_retraso_promedio": None,
                    "dias_creacion_aprobacion": 10 + p,
                    "marca_calidad": None,
                }
            )
    return pd.DataFrame(filas)


def _practicas() -> pd.DataFrame:
    filas = []
    for i in range(1, 25):  # 24 prácticas
        inicio = date(2026, 2, 1) if i % 3 == 0 else date(2026, 8, (i % 20) + 1)
        filas.append(
            {
                "id_practica": i,
                "sk_fecha": sk_fecha(inicio),
                "sk_macroproyecto": None,
                "sk_linea": 4 if i <= 14 else (5 if i <= 21 else 6),
                "sk_estado": 3 if i % 2 else 4,
                "sk_persona": 1 if i % 2 else 2,
                "sk_empresa": i % 3 + 1,
                "seudonimo_estudiante": f"estudiante-{i if i != 2 else 1}",  # la 1 y la 2 son de la misma persona
                "duracion_dias": 90 + i,
                "tareas_asignadas": 10,
                "tareas_cumplidas": i % 11,
                "finalizada": 0 if i % 2 else 1,
                "marca_calidad": None,
            }
        )
    return pd.DataFrame(filas)


def _consultorias() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "id_consultoria": i,
                "sk_fecha": sk_fecha(date(2026, (i % 9) + 1, 15)),
                "sk_estado": 5,
                "sk_persona": 3 if i % 2 else None,
                "sk_empresa": i % 3 + 1,
                "valor_facturado": 5_000_000.0 * i,
                "satisfaccion": 3.0 + (i % 5) * 0.5,
                "n_consultores": 1 + i % 4,
                "duracion_dias": 30 + 5 * i,
                "marca_calidad": None,
            }
            for i in range(1, 13)
        ]
    )


def _facturacion() -> pd.DataFrame:
    filas = []
    for anio in (2025, 2026):
        for mes in range(1, 13):
            if (anio, mes) > (2026, 10):
                continue
            for empresa in (1, 2):
                filas.append(
                    {
                        "sk_fecha": sk_fecha(date(anio, mes, 1)),
                        "sk_empresa": empresa,
                        "valor_facturado": 1_000_000.0 * mes * empresa + (500_000.0 if anio == 2026 else 0.0),
                        "n_facturas": mes % 3 + 1,
                    }
                )
    return pd.DataFrame(filas)


def _convenios() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "sk_fecha_corte": sk_fecha(date(2026, 10, 31)),
                "id_convenio": i,
                "sk_estado": 6,
                "sk_empresa": i % 3 + 1,
                "sk_tipo_convenio": i % 2 + 1,
                "duracion_dias": 365,
                "dias_para_vencer": 30 * i,
                "renovado": i % 2,
                "docs_completos": 1,
                "n_actividades": i,
                "marca_calidad": None,
            }
            for i in range(1, 8)
        ]
    )


@pytest.fixture(scope="session")
def tablas() -> dict[str, pd.DataFrame]:
    """Los mismos datos que se insertan en la base, como DataFrames para el cálculo independiente."""
    proyectos = _proyectos()
    agregado = (
        proyectos.groupby(["sk_fecha_corte", "sk_linea", "sk_estado"], as_index=False)
        .agg(
            n_proyectos=("id_proyecto", "count"),
            presupuesto_asignado=("presupuesto_asignado", "sum"),
            presupuesto_ejecutado=("presupuesto_ejecutado", "sum"),
            n_hitos=("n_hitos", "sum"),
            n_hitos_atrasados=("n_hitos_atrasados", "sum"),
        )
        .astype({"n_proyectos": int, "n_hitos": int, "n_hitos_atrasados": int})
    )
    lineas = pd.DataFrame(LINEAS, columns=["sk_linea", "id_linea_origen", "id_programa_origen", "linea_investigacion",
                                           "programa", "facultad"])  # fmt: skip
    return {
        "hecho_proyecto": proyectos,
        "agg_proyecto_linea_mes": agregado,
        "hecho_practica": _practicas(),
        "hecho_consultoria": _consultorias(),
        "agg_facturacion_mes": _facturacion(),
        "hecho_convenio": _convenios(),
        "dim_linea_programa": lineas,
    }


def _registros(df: pd.DataFrame) -> list[dict]:
    return [{k: (None if pd.isna(v) else v) for k, v in fila.items()} for fila in df.to_dict("records")]


@pytest.fixture
def bd(motor_bd, tablas):
    """Motor SQLite con el datawarehouse mínimo cargado."""
    with motor_bd.begin() as con:
        con.execute(insert(dw.dim_tiempo), filas_dim_tiempo(date(2025, 1, 1), date(2026, 12, 31)))
        con.execute(insert(dw.dim_linea_programa), _registros(tablas["dim_linea_programa"]))
        con.execute(
            insert(dw.dim_estado),
            [dict(zip(("sk_estado", "modulo", "estado", "es_final"), e, strict=True)) for e in ESTADOS],
        )
        con.execute(
            insert(dw.dim_persona_rol),
            [
                {
                    "sk_persona": 1,
                    "seudonimo": seudonimizar(412, SAL),
                    "rol": "tutor",
                    "tipo_participacion": "tutor_academico",
                },
                {
                    "sk_persona": 2,
                    "seudonimo": seudonimizar(413, SAL),
                    "rol": "tutor",
                    "tipo_participacion": "tutor_academico",
                },
                {
                    "sk_persona": 3,
                    "seudonimo": seudonimizar(500, SAL),
                    "rol": "consultor",
                    "tipo_participacion": "lider",
                },
            ],
        )
        con.execute(
            insert(dw.dim_empresa),
            [{"sk_empresa": i, "id_origen": 100 + i, "sector": s, "ciudad": "Bogotá", "tipo": "privada"}
             for i, s in ((1, "Tecnología"), (2, "Salud"), (3, "Educación"))],
        )  # fmt: skip
        con.execute(insert(dw.dim_tipo_convenio), [{"sk_tipo_convenio": 1, "tipo_convenio": "marco"},
                                                   {"sk_tipo_convenio": 2, "tipo_convenio": "especifico"}])  # fmt: skip
        for nombre in ("hecho_proyecto", "agg_proyecto_linea_mes", "hecho_practica", "hecho_consultoria",
                       "agg_facturacion_mes", "hecho_convenio"):  # fmt: skip
            con.execute(insert(dw.tabla(nombre)), _registros(tablas[nombre]))
    return motor_bd
