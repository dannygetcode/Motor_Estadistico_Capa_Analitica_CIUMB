"""Estadística descriptiva (Tabla 8, RF-02, OE1). Librería: pandas y NumPy.

Pruebas: `tests/motor/test_descriptiva.py` (contraste con NumPy y SciPy).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ciumb_analitica.motor.resultado import MuestraInsuficiente, ResumenDescriptivo


def _moda(x: np.ndarray) -> float | None:
    """Menor de las modas; `None` si ningún valor se repite (todos distintos)."""
    valores, conteos = np.unique(x, return_counts=True)
    if conteos.max() < 2:
        return None
    return float(valores[conteos == conteos.max()].min())


def resumen(valores: pd.Series, *, percentiles: tuple[int, ...] = (10, 90)) -> ResumenDescriptivo:
    """Media, mediana, moda, desviación estándar muestral, cuartiles y percentiles.

    Entradas: `valores` numéricos (los nulos se ignoran); `percentiles` adicionales (0-100).
    Salida: `ResumenDescriptivo`. Cuartiles y percentiles con interpolación lineal (la de `numpy.percentile`
    por defecto). Lanza `MuestraInsuficiente` si no queda ningún valor.
    """
    x = pd.to_numeric(valores, errors="coerce").dropna().to_numpy(dtype=float)
    if x.size == 0:
        raise MuestraInsuficiente("no hay valores para resumir")
    q1, mediana, q3 = np.percentile(x, [25, 50, 75])
    return ResumenDescriptivo(
        n=int(x.size),
        media=float(np.mean(x)),
        mediana=float(mediana),
        moda=_moda(x),
        desviacion=float(np.std(x, ddof=1)) if x.size >= 2 else None,
        minimo=float(x.min()),
        maximo=float(x.max()),
        q1=float(q1),
        q3=float(q3),
        percentiles={int(p): float(np.percentile(x, p)) for p in percentiles},
    )


_COLUMNAS_GRUPO = ("n", "media", "mediana", "desviacion", "minimo", "maximo", "q1", "q3")


def resumen_por_grupo(datos: pd.DataFrame, columnas_dim: list[str], metrica: str) -> pd.DataFrame:
    """`resumen` de `metrica` por cada combinación de `columnas_dim` (INF-INV-02: ejecución por línea).

    Entradas: datos en nivel registro (salida de `revisar_datos`). Salida: una fila por grupo con las columnas
    de dimensión y n, media, mediana, desviacion, minimo, maximo, q1, q3; ordenada por las dimensiones.
    Una razón por registro se resume como cualquier medida, pero el valor del grupo «total» NO es la media de
    las razones: se recalcula con `razon_total`.
    """
    filas = []
    for clave, grupo in datos.groupby(columnas_dim, sort=True, dropna=False):
        clave = clave if isinstance(clave, tuple) else (clave,)
        try:
            r = resumen(grupo[metrica], percentiles=())
        except MuestraInsuficiente:
            continue
        filas.append(dict(zip(columnas_dim, clave, strict=True)) | {c: getattr(r, c) for c in _COLUMNAS_GRUPO})
    salida = pd.DataFrame(filas, columns=[*columnas_dim, *_COLUMNAS_GRUPO])
    return salida.sort_values(columnas_dim, kind="mergesort").reset_index(drop=True)


def frecuencias(datos: pd.DataFrame, columnas_dim: list[str], metrica: str, *, relativas: bool = False) -> pd.DataFrame:
    """Tabla de frecuencias de una métrica aditiva ya agregada por `columnas_dim`.

    Salida: las columnas de entrada más `frecuencia_relativa` (proporción entre 0 y 1 sobre el total) si
    `relativas`. La suma de las proporciones es 1. Con total 0, la proporción es nula.
    No aplicar a razones: su «total» no es la suma de las celdas.
    """
    salida = datos.copy()
    if relativas:
        total = float(pd.to_numeric(salida[metrica], errors="coerce").sum())
        salida["frecuencia_relativa"] = salida[metrica] / total if total != 0 else np.nan
    return salida


def razon_total(datos: pd.DataFrame, metrica: str, *, factor: float = 100.0) -> float | None:
    """Razón del conjunto completo a partir de sus componentes: factor * sum(`<metrica>__num`) /
    sum(`<metrica>__den`). Devuelve `None` si el denominador es 0. Nunca promedia la columna de la razón
    (4.4.2, paso 3)."""
    num = float(pd.to_numeric(datos[f"{metrica}__num"], errors="coerce").sum())
    den = float(pd.to_numeric(datos[f"{metrica}__den"], errors="coerce").sum())
    if den == 0:
        return None
    return factor * num / den
