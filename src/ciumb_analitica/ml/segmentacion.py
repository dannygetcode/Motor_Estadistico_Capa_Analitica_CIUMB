"""Segmentación de empresas por actividad (Tabla 8, INF-EMP-03, P8, OE2). Librería: scikit-learn.

Pruebas: `tests/ml/test_segmentacion.py`.
"""

from __future__ import annotations

import pandas as pd

from ciumb_analitica.motor.resultado import PENDIENTE, ResultadoSegmentacion

SEMILLA = 20261111
K_MINIMO, K_MAXIMO = 2, 10


def unir_por_dimension(resultados: dict[str, pd.DataFrame], dimension: str, metricas: list[str]) -> pd.DataFrame:
    """Une las consultas `principal:<tabla>` de un plan con varios hechos (P8) por la dimensión común.

    Entradas: salida de `compilador.ejecutar` ya pasada por `revisar_datos`; `dimension` = columna común
    (p. ej. 'empresa'). Salida: una fila por valor de la dimensión con una columna por métrica; unión externa,
    los faltantes de métricas aditivas valen 0. Las filas con la dimensión nula se descartan.
    """
    raise NotImplementedError(PENDIENTE)


def segmentar(
    datos: pd.DataFrame, columnas: list[str], *, k: int | None = None, semilla: int = SEMILLA
) -> ResultadoSegmentacion:
    """k-medias sobre variables estandarizadas; si `k` es None se elige por coeficiente de silueta.

    Entradas: una fila por unidad (empresa) y las `columnas` numéricas a usar.
    Método: `StandardScaler` + `KMeans(n_clusters=k, n_init=10, random_state=semilla)`. Sin `k`: se prueba
    k = 2..min(10, n - 1) y gana el de mayor `silhouette_score` (en empate, el menor k).
    Salida: `ResultadoSegmentacion`; centroides en unidades originales; grupos renumerados de mayor a menor
    tamaño (en empate, por el primer centroide descendente) para que el resultado no dependa del azar interno.
    Lanza `MuestraInsuficiente` con menos de 10 unidades o si todas las filas son iguales.
    Privacidad: hacia el contrato solo viajan k, la silueta, los tamaños y los centroides; nunca qué empresa
    cae en qué grupo (la dimensión `empresa` tiene `viaja_a_ia = False`).
    """
    raise NotImplementedError(PENDIENTE)
