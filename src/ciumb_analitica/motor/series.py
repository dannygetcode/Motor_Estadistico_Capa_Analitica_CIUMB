"""Series de tiempo (Tabla 8, RF-03, OE1). Librería: pandas.

La agregación mensual, trimestral, semestral o anual ya la hace el compilador (columnas `tiempo_anio`,
`tiempo_mes`…). Aquí se ordena la serie, se completan los periodos faltantes y se calculan variaciones y
acumulados. Pruebas: `tests/motor/test_series.py`.
"""

from __future__ import annotations

import pandas as pd

from ciumb_analitica.motor.resultado import PENDIENTE
from ciumb_analitica.spec.modelos import Granularidad


def a_serie(datos: pd.DataFrame, metrica: str, granularidad: Granularidad, *, completar: bool = True) -> pd.Series:
    """Convierte el resultado del compilador en una serie con índice `pandas.PeriodIndex`.

    Entradas: datos con `tiempo_anio` y la columna de la granularidad (`tiempo_mes`, `tiempo_trimestre` o
    `tiempo_semestre`). Salida: serie ordenada. Frecuencias: mes 'M', trimestre 'Q', semestre '2Q' (semestre 1
    = enero-junio), año 'Y'. Si `completar`, los periodos intermedios sin fila quedan en 0 para métricas
    aditivas; para razones y promedios quedan nulos (pasar `completar=False`).
    """
    raise NotImplementedError(PENDIENTE)


def variacion_porcentual(serie: pd.Series, *, rezago: int = 1) -> pd.Series:
    """Variación porcentual frente al periodo `rezago` posiciones atrás: 100 * (x_t - x_{t-r}) / |x_{t-r}|.

    El primer tramo queda nulo. Si el valor anterior es 0, la variación es nula (no infinito).
    `rezago=12` sobre una serie mensual da la variación interanual mes a mes.
    """
    raise NotImplementedError(PENDIENTE)


def acumulado(serie: pd.Series, *, reiniciar_cada_anio: bool = True) -> pd.Series:
    """Suma acumulada; por defecto se reinicia en enero (acumulado del año). Solo métricas aditivas."""
    raise NotImplementedError(PENDIENTE)


def variacion_interanual(serie: pd.Series) -> dict:
    """Compara el último año de la serie con el mismo tramo del año anterior (P3, Figura 12).

    Entradas: serie mensual, trimestral o semestral que cubre dos años (el último puede estar incompleto).
    Salida: {"actual": suma del tramo del último año, "anterior": suma del MISMO tramo del año previo,
    "variacion_pct": 100 * (actual - anterior) / |anterior| o None si anterior es 0,
    "periodo_maximo": pandas.Period del mayor valor del último año, "valor_maximo": ese valor,
    "n_periodos": número de periodos comparados}.
    Ejemplo: enero-octubre de 2026 frente a enero-octubre de 2025, no frente a todo 2025.
    """
    raise NotImplementedError(PENDIENTE)
