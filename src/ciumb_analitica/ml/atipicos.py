"""Detección de valores atípicos (Tabla 8, RF-05, RF-20, OE2). Librería: NumPy y SciPy.

Pruebas: `tests/ml/test_atipicos.py`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from ciumb_analitica.motor.resultado import MuestraInsuficiente, ResultadoAtipicos

MIN_VALORES_RIC = 4
MIN_VALORES_Z = 3


def atipicos_ric(valores: pd.Series, *, k: float = 1.5) -> ResultadoAtipicos:
    """Regla del rango intercuartílico de Tukey: atípico si x < Q1 - k*RIC o x > Q3 + k*RIC.

    Entradas: valores numéricos (los nulos nunca son atípicos y no cuentan en n); `k` configurable.
    Cuartiles con interpolación lineal (`numpy.percentile`); RIC = `scipy.stats.iqr`.
    Salida: `ResultadoAtipicos` con los límites y la máscara `es_atipico` (mismo índice que la entrada).
    Lanza `MuestraInsuficiente` con menos de 4 valores.
    """
    numericos = pd.to_numeric(valores, errors="coerce")
    validos = numericos.dropna().to_numpy(dtype=float)
    if validos.size < MIN_VALORES_RIC:
        raise MuestraInsuficiente(f"la regla del RIC necesita al menos {MIN_VALORES_RIC} valores; hay {validos.size}")
    q1, q3 = np.percentile(validos, [25, 75])
    ric = float(stats.iqr(validos))
    inferior, superior = float(q1 - k * ric), float(q3 + k * ric)
    mascara = ((numericos < inferior) | (numericos > superior)).fillna(False).astype(bool)
    return ResultadoAtipicos(
        metodo="RIC", k=k, limite_inferior=inferior, limite_superior=superior, es_atipico=mascara, n=int(validos.size)
    )


def atipicos_z(valores: pd.Series, *, umbral: float = 3.0) -> ResultadoAtipicos:
    """Puntaje Z: atípico si |x - media| / desviación muestral (ddof = 1) > `umbral`.

    Referencia: `scipy.stats.zscore(valores, ddof=1)`. Los límites son media ± umbral * desviación.
    Adecuado para distribuciones aproximadamente simétricas; para sesgadas, usar `atipicos_ric`.
    Lanza `MuestraInsuficiente` con menos de 3 valores o desviación 0.
    """
    numericos = pd.to_numeric(valores, errors="coerce")
    validos = numericos.dropna().to_numpy(dtype=float)
    if validos.size < MIN_VALORES_Z:
        raise MuestraInsuficiente(f"el puntaje Z necesita al menos {MIN_VALORES_Z} valores; hay {validos.size}")
    media, desviacion = float(np.mean(validos)), float(np.std(validos, ddof=1))
    if desviacion == 0:
        raise MuestraInsuficiente("todos los valores son iguales: el puntaje Z no está definido")
    z = (numericos - media) / desviacion
    mascara = (z.abs() > umbral).fillna(False).astype(bool)
    return ResultadoAtipicos(
        metodo="puntaje_z",
        k=umbral,
        limite_inferior=media - umbral * desviacion,
        limite_superior=media + umbral * desviacion,
        es_atipico=mascara,
        n=int(validos.size),
    )


def detectar(valores: pd.Series, *, metodo: str = "RIC", k: float = 1.5) -> ResultadoAtipicos:
    """Despacha según `analisis.atipicos.metodo` / `analisis.tecnica` de la spec: 'RIC' o 'puntaje_z'
    (en ese caso `k` es el umbral)."""
    if metodo == "RIC":
        return atipicos_ric(valores, k=k)
    if metodo == "puntaje_z":
        return atipicos_z(valores, umbral=k)
    raise ValueError(f"método de atípicos desconocido: {metodo} (use 'RIC' o 'puntaje_z')")
