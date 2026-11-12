"""Pronóstico de series de tiempo (Tabla 8, RF-06, INF-TRA-05, OE2). Librería: statsmodels.

Regla (RNF-13, invariante 7): con menos de 12 puntos el pronóstico NO se publica. `revisar_datos` ya avisa
(`PRONOSTICO_NO_PUBLICABLE`); estas funciones además se niegan a calcularlo.
Pruebas: `tests/ml/test_pronostico.py`.
"""

from __future__ import annotations

import pandas as pd

from ciumb_analitica.motor.resultado import PENDIENTE, ResultadoPronostico


def pronosticar(
    serie: pd.Series, horizonte: int, *, tecnica: str = "holt", nivel_confianza: float = 0.95
) -> ResultadoPronostico:
    """Pronostica `horizonte` periodos con intervalo de confianza.

    Entradas: `serie` ordenada sin nulos (salida de `motor.series.a_serie`); `tecnica`:
      - 'holt': suavizado exponencial con tendencia aditiva. Punto: `statsmodels.tsa.holtwinters.
        ExponentialSmoothing(serie, trend="add", initialization_method="estimated").fit().forecast(h)`.
        Intervalo: punto ± z * s * sqrt(h), con s = desviación muestral de los residuos y h = 1..horizonte.
      - 'regresion_lineal': MCO contra el índice 0..n-1. Punto e intervalo de PREDICCIÓN:
        `statsmodels.api.OLS(...).fit().get_prediction(...).summary_frame(alpha=1 - nivel_confianza)`
        (columnas `mean`, `obs_ci_lower`, `obs_ci_upper`).
    Salida: `ResultadoPronostico` con `mae_modelo` y `mae_ingenuo` de `validar_origen_movil`. Si
    mae_modelo >= mae_ingenuo agrega una advertencia: el modelo no mejora la línea base.
    Lanza `MuestraInsuficiente` con menos de 12 puntos (`spec.resultado.MIN_PUNTOS_PRONOSTICO`).
    """
    raise NotImplementedError(PENDIENTE)


def validar_origen_movil(
    serie: pd.Series, *, tecnica: str = "holt", minimo_entrenamiento: int = 8
) -> tuple[float, float]:
    """Validación de origen móvil a un paso (Hyndman y Athanasopoulos, 2021).

    Para cada t desde `minimo_entrenamiento` hasta n-1: ajusta con serie[:t], pronostica un paso y compara
    con serie[t]. Línea base ingenua: el último valor observado, serie[t-1].
    Salida: (MAE del modelo, MAE de la línea base).
    """
    raise NotImplementedError(PENDIENTE)
