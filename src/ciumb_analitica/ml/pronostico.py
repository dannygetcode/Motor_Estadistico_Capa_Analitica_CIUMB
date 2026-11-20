"""Pronóstico de series de tiempo (Tabla 8, RF-06, INF-TRA-05, OE2). Librería: statsmodels.

Regla (RNF-13, invariante 7): con menos de 12 puntos el pronóstico NO se publica. `revisar_datos` ya avisa
(`PRONOSTICO_NO_PUBLICABLE`); estas funciones además se niegan a calcularlo.
Pruebas: `tests/ml/test_pronostico.py`.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from ciumb_analitica.motor.resultado import MuestraInsuficiente, ResultadoPronostico
from ciumb_analitica.spec import resultado as r

TECNICAS = ("holt", "regresion_lineal")
PRONOSTICO_SIN_MEJORA = r.PRONOSTICO_SIN_MEJORA
"""El MAE del modelo no es menor que el de la línea base ingenua (código en `spec.resultado`, D-24)."""


def _ajustar_holt(y: np.ndarray):
    # Con series cortas la inicialización estimada emite avisos de convergencia: se silencian solo aquí.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return ExponentialSmoothing(y, trend="add", initialization_method="estimated").fit()


def _punto_a_un_paso(y: np.ndarray, tecnica: str) -> float:
    if tecnica == "holt":
        return float(np.asarray(_ajustar_holt(y).forecast(1))[0])
    ajuste = sm.OLS(y, sm.add_constant(np.arange(y.size, dtype=float))).fit()
    return float(ajuste.params[0] + ajuste.params[1] * y.size)


def _validar_tecnica(tecnica: str) -> None:
    if tecnica not in TECNICAS:
        raise ValueError(f"técnica de pronóstico desconocida: {tecnica} (use {', '.join(TECNICAS)})")


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
    _validar_tecnica(tecnica)
    y = pd.to_numeric(serie, errors="coerce").to_numpy(dtype=float)
    if y.size < r.MIN_PUNTOS_PRONOSTICO or np.isnan(y).any():
        validos = int(np.sum(~np.isnan(y)))
        minimo = r.MIN_PUNTOS_PRONOSTICO
        raise MuestraInsuficiente(f"el pronóstico necesita al menos {minimo} puntos sin nulos; hay {validos}")
    if horizonte < 1:
        raise ValueError("el horizonte debe ser al menos 1")
    if tecnica == "holt":
        ajuste = _ajustar_holt(y)
        punto = np.asarray(ajuste.forecast(horizonte), dtype=float)
        z = float(stats.norm.ppf(1 - (1 - nivel_confianza) / 2))
        s = float(np.std(np.asarray(ajuste.resid, dtype=float), ddof=1))
        margen = z * s * np.sqrt(np.arange(1, horizonte + 1))
        inferior, superior = punto - margen, punto + margen
    else:
        ajuste = sm.OLS(y, sm.add_constant(np.arange(y.size, dtype=float))).fit()
        nuevos = sm.add_constant(np.arange(y.size, y.size + horizonte, dtype=float), has_constant="add")
        marco = ajuste.get_prediction(nuevos).summary_frame(alpha=1 - nivel_confianza)
        punto = marco["mean"].to_numpy(dtype=float)
        inferior = marco["obs_ci_lower"].to_numpy(dtype=float)
        superior = marco["obs_ci_upper"].to_numpy(dtype=float)
    mae_modelo, mae_ingenuo = validar_origen_movil(serie, tecnica=tecnica)
    avisos = ()
    if mae_modelo >= mae_ingenuo:
        avisos = (
            r.Aviso(
                codigo=PRONOSTICO_SIN_MEJORA,
                mensaje=(
                    f"El modelo no mejora la línea base ingenua (MAE {mae_modelo:.2f} frente a {mae_ingenuo:.2f}); "
                    "el pronóstico debe leerse con cautela."
                ),
            ),
        )
    return ResultadoPronostico(
        tecnica=tecnica,
        nivel_confianza=nivel_confianza,
        valores=tuple(float(v) for v in punto),
        inferior=tuple(float(v) for v in inferior),
        superior=tuple(float(v) for v in superior),
        n=int(y.size),
        mae_modelo=mae_modelo,
        mae_ingenuo=mae_ingenuo,
        advertencias=avisos,
    )


def validar_origen_movil(
    serie: pd.Series, *, tecnica: str = "holt", minimo_entrenamiento: int = 8
) -> tuple[float, float]:
    """Validación de origen móvil a un paso (Hyndman y Athanasopoulos, 2021).

    Para cada t desde `minimo_entrenamiento` hasta n-1: ajusta con serie[:t], pronostica un paso y compara
    con serie[t]. Línea base ingenua: el último valor observado, serie[t-1].
    Salida: (MAE del modelo, MAE de la línea base).
    """
    _validar_tecnica(tecnica)
    y = pd.to_numeric(serie, errors="coerce").to_numpy(dtype=float)
    if y.size <= minimo_entrenamiento:
        raise MuestraInsuficiente(
            f"la validación de origen móvil necesita más de {minimo_entrenamiento} puntos; hay {y.size}"
        )
    errores_modelo, errores_ingenuo = [], []
    for t in range(minimo_entrenamiento, y.size):
        errores_modelo.append(abs(y[t] - _punto_a_un_paso(y[:t], tecnica)))
        errores_ingenuo.append(abs(y[t] - y[t - 1]))
    return float(np.mean(errores_modelo)), float(np.mean(errores_ingenuo))
