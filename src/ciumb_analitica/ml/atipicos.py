"""Detección de valores atípicos (Tabla 8, RF-05, RF-20, OE2). Librería: NumPy y SciPy.

Pruebas: `tests/ml/test_atipicos.py`.
"""

from __future__ import annotations

import pandas as pd

from ciumb_analitica.motor.resultado import PENDIENTE, ResultadoAtipicos


def atipicos_ric(valores: pd.Series, *, k: float = 1.5) -> ResultadoAtipicos:
    """Regla del rango intercuartílico de Tukey: atípico si x < Q1 - k*RIC o x > Q3 + k*RIC.

    Entradas: valores numéricos (los nulos nunca son atípicos y no cuentan en n); `k` configurable.
    Cuartiles con interpolación lineal (`numpy.percentile`); RIC = `scipy.stats.iqr`.
    Salida: `ResultadoAtipicos` con los límites y la máscara `es_atipico` (mismo índice que la entrada).
    Lanza `MuestraInsuficiente` con menos de 4 valores.
    """
    raise NotImplementedError(PENDIENTE)


def atipicos_z(valores: pd.Series, *, umbral: float = 3.0) -> ResultadoAtipicos:
    """Puntaje Z: atípico si |x - media| / desviación muestral (ddof = 1) > `umbral`.

    Referencia: `scipy.stats.zscore(valores, ddof=1)`. Los límites son media ± umbral * desviación.
    Adecuado para distribuciones aproximadamente simétricas; para sesgadas, usar `atipicos_ric`.
    Lanza `MuestraInsuficiente` con menos de 3 valores o desviación 0.
    """
    raise NotImplementedError(PENDIENTE)


def detectar(valores: pd.Series, *, metodo: str = "RIC", k: float = 1.5) -> ResultadoAtipicos:
    """Despacha según `analisis.atipicos.metodo` / `analisis.tecnica` de la spec: 'RIC' o 'puntaje_z'
    (en ese caso `k` es el umbral)."""
    raise NotImplementedError(PENDIENTE)
