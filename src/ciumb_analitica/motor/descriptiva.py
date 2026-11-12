"""Estadística descriptiva (Tabla 8, RF-02, OE1). Librería: pandas y NumPy.

Pruebas: `tests/motor/test_descriptiva.py` (contraste con NumPy y SciPy).
"""

from __future__ import annotations

import pandas as pd

from ciumb_analitica.motor.resultado import PENDIENTE, ResumenDescriptivo


def resumen(valores: pd.Series, *, percentiles: tuple[int, ...] = (10, 90)) -> ResumenDescriptivo:
    """Media, mediana, moda, desviación estándar muestral, cuartiles y percentiles.

    Entradas: `valores` numéricos (los nulos se ignoran); `percentiles` adicionales (0-100).
    Salida: `ResumenDescriptivo`. Cuartiles y percentiles con interpolación lineal (la de `numpy.percentile`
    por defecto). Lanza `MuestraInsuficiente` si no queda ningún valor.
    """
    raise NotImplementedError(PENDIENTE)


def resumen_por_grupo(datos: pd.DataFrame, columnas_dim: list[str], metrica: str) -> pd.DataFrame:
    """`resumen` de `metrica` por cada combinación de `columnas_dim` (INF-INV-02: ejecución por línea).

    Entradas: datos en nivel registro (salida de `revisar_datos`). Salida: una fila por grupo con las columnas
    de dimensión y n, media, mediana, desviacion, minimo, maximo, q1, q3; ordenada por las dimensiones.
    Una razón por registro se resume como cualquier medida, pero el valor del grupo «total» NO es la media de
    las razones: se recalcula con `razon_total`.
    """
    raise NotImplementedError(PENDIENTE)


def frecuencias(datos: pd.DataFrame, columnas_dim: list[str], metrica: str, *, relativas: bool = False) -> pd.DataFrame:
    """Tabla de frecuencias de una métrica aditiva ya agregada por `columnas_dim`.

    Salida: las columnas de entrada más `frecuencia_relativa` (proporción entre 0 y 1 sobre el total) si
    `relativas`. La suma de las proporciones es 1. Con total 0, la proporción es nula.
    No aplicar a razones: su «total» no es la suma de las celdas.
    """
    raise NotImplementedError(PENDIENTE)


def razon_total(datos: pd.DataFrame, metrica: str, *, factor: float = 100.0) -> float | None:
    """Razón del conjunto completo a partir de sus componentes: factor * sum(`<metrica>__num`) /
    sum(`<metrica>__den`). Devuelve `None` si el denominador es 0. Nunca promedia la columna de la razón
    (4.4.2, paso 3)."""
    raise NotImplementedError(PENDIENTE)
