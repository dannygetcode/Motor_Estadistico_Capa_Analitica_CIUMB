"""Segmentación de empresas por actividad (Tabla 8, INF-EMP-03, P8, OE2). Librería: scikit-learn.

Pruebas: `tests/ml/test_segmentacion.py`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from ciumb_analitica.motor.resultado import MuestraInsuficiente, ResultadoSegmentacion

SEMILLA = 20261111
K_MINIMO, K_MAXIMO = 2, 10


def unir_por_dimension(resultados: dict[str, pd.DataFrame], dimension: str, metricas: list[str]) -> pd.DataFrame:
    """Une las consultas `principal:<tabla>` de un plan con varios hechos (P8) por la dimensión común.

    Entradas: salida de `compilador.ejecutar` ya pasada por `revisar_datos`; `dimension` = columna común
    (p. ej. 'empresa'). Salida: una fila por valor de la dimensión con una columna por métrica; unión externa,
    los faltantes de métricas aditivas valen 0. Las filas con la dimensión nula se descartan.
    """
    unido: pd.DataFrame | None = None
    for nombre in sorted(resultados):
        if not nombre.startswith("principal"):
            continue
        datos = resultados[nombre].dropna(subset=[dimension])
        propias = [m for m in metricas if m in datos.columns]
        if not propias:
            continue
        parte = datos.groupby(dimension, sort=True)[propias].sum().reset_index()
        unido = parte if unido is None else unido.merge(parte, on=dimension, how="outer")
    if unido is None:
        return pd.DataFrame(columns=[dimension, *metricas])
    for m in metricas:
        unido[m] = unido[m].fillna(0) if m in unido.columns else 0
    return unido[[dimension, *metricas]].sort_values(dimension, kind="mergesort").reset_index(drop=True)


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
    ordenados = datos.sort_index(kind="mergesort")
    x_original = ordenados[columnas].apply(pd.to_numeric, errors="coerce")
    if x_original.isna().any().any():
        raise ValueError("la segmentación no admite valores nulos en las columnas usadas")
    n = len(x_original)
    if n < 10:
        raise MuestraInsuficiente(f"la segmentación necesita al menos 10 unidades; hay {n}")
    if len(x_original.drop_duplicates()) < 2:
        raise MuestraInsuficiente("todas las unidades son iguales: no hay grupos que separar")
    x = StandardScaler().fit_transform(x_original.to_numpy(dtype=float))

    def _ajustar(k_: int) -> np.ndarray:
        return KMeans(n_clusters=k_, n_init=10, random_state=semilla).fit_predict(x)

    siluetas: dict[int, float] = {}
    if k is None:
        distintos = len(x_original.drop_duplicates())
        for candidato in range(K_MINIMO, min(K_MAXIMO, n - 1, distintos) + 1):
            siluetas[candidato] = float(silhouette_score(x, _ajustar(candidato)))
        if not siluetas:
            raise MuestraInsuficiente("no hay suficientes unidades distintas para probar k >= 2")
        k = max(siluetas, key=lambda c: (round(siluetas[c], 12), -c))
    etiquetas_crudas = _ajustar(k)
    silueta = siluetas.get(k, float(silhouette_score(x, etiquetas_crudas)))

    # Renumeración determinista: de mayor a menor tamaño; en empate, por el primer centroide descendente.
    centroides_crudos = x_original.groupby(etiquetas_crudas).mean()
    tamanos_crudos = pd.Series(etiquetas_crudas).value_counts()
    orden = sorted(centroides_crudos.index, key=lambda g: (-tamanos_crudos[g], -centroides_crudos.loc[g].iloc[0]))
    nuevo = {viejo: i for i, viejo in enumerate(orden)}
    etiquetas = pd.Series([nuevo[e] for e in etiquetas_crudas], index=ordenados.index, name="grupo")
    etiquetas = etiquetas.reindex(datos.index)
    centroides = centroides_crudos.loc[orden].reset_index(drop=True)
    centroides.index.name = "grupo"
    return ResultadoSegmentacion(
        k=int(k),
        silueta=silueta,
        etiquetas=etiquetas,
        centroides=centroides,
        tamanos=tuple(int(tamanos_crudos[g]) for g in orden),
        siluetas_por_k=siluetas,
    )
