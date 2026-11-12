"""ml.pronostico (Tabla 8, RF-06, INF-TRA-05, OE2): Holt y regresión lineal contra statsmodels."""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm
from scipy import stats
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from ciumb_analitica.ml import pronostico
from ciumb_analitica.motor.resultado import MuestraInsuficiente
from tests.conftest import PENDIENTE

pytestmark = PENDIENTE

RNG = np.random.default_rng(20261111)
# 16 semestres (2019-1 a 2026-2) con tendencia creciente, como las prácticas de P7.
SERIE = pd.Series(
    80 + 6.5 * np.arange(16) + RNG.normal(0, 5, size=16),
    index=pd.period_range("2019-01", periods=16, freq="2Q"),
).round(0)


def _holt_de_referencia(serie: pd.Series, h: int) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ajuste = ExponentialSmoothing(serie.to_numpy(), trend="add", initialization_method="estimated").fit()
    return np.asarray(ajuste.forecast(h)), np.asarray(ajuste.resid)


def test_holt_coincide_con_statsmodels():
    r = pronostico.pronosticar(SERIE, 2, tecnica="holt", nivel_confianza=0.95)
    punto, residuos = _holt_de_referencia(SERIE, 2)
    assert r.tecnica == "holt" and r.n == 16 and len(r.valores) == 2
    assert list(r.valores) == pytest.approx(punto, rel=1e-6)
    z = stats.norm.ppf(0.975)
    s = np.std(residuos, ddof=1)
    for h in (1, 2):
        assert r.inferior[h - 1] == pytest.approx(punto[h - 1] - z * s * np.sqrt(h), rel=1e-6)
        assert r.superior[h - 1] == pytest.approx(punto[h - 1] + z * s * np.sqrt(h), rel=1e-6)
    assert r.superior[1] - r.inferior[1] > r.superior[0] - r.inferior[0]  # el intervalo se abre con el horizonte


def test_regresion_lineal_coincide_con_statsmodels():
    r = pronostico.pronosticar(SERIE, 3, tecnica="regresion_lineal", nivel_confianza=0.90)
    x = sm.add_constant(np.arange(16.0))
    ajuste = sm.OLS(SERIE.to_numpy(), x).fit()
    nuevos = sm.add_constant(np.arange(16.0, 19.0), has_constant="add")
    marco = ajuste.get_prediction(nuevos).summary_frame(alpha=0.10)
    assert list(r.valores) == pytest.approx(marco["mean"].to_numpy())
    assert list(r.inferior) == pytest.approx(marco["obs_ci_lower"].to_numpy())
    assert list(r.superior) == pytest.approx(marco["obs_ci_upper"].to_numpy())
    assert r.nivel_confianza == 0.90


def test_un_nivel_de_confianza_mayor_da_un_intervalo_mas_ancho():
    a = pronostico.pronosticar(SERIE, 1, nivel_confianza=0.80)
    b = pronostico.pronosticar(SERIE, 1, nivel_confianza=0.99)
    assert a.valores == b.valores
    assert b.superior[0] - b.inferior[0] > a.superior[0] - a.inferior[0]


@pytest.mark.parametrize("n", [0, 5, 11])
def test_con_menos_de_doce_puntos_no_se_pronostica(n):
    with pytest.raises(MuestraInsuficiente):
        pronostico.pronosticar(SERIE.head(n), 2)


def test_con_doce_puntos_si():
    assert len(pronostico.pronosticar(SERIE.head(12), 2).valores) == 2


def test_validacion_de_origen_movil_contra_calculo_directo():
    mae_modelo, mae_ingenuo = pronostico.validar_origen_movil(SERIE, tecnica="regresion_lineal", minimo_entrenamiento=8)
    y = SERIE.to_numpy()
    errores_modelo, errores_ingenuo = [], []
    for t in range(8, 16):
        pendiente, intercepto = np.polyfit(np.arange(t), y[:t], 1)
        errores_modelo.append(abs(y[t] - (intercepto + pendiente * t)))
        errores_ingenuo.append(abs(y[t] - y[t - 1]))
    assert mae_modelo == pytest.approx(np.mean(errores_modelo))
    assert mae_ingenuo == pytest.approx(np.mean(errores_ingenuo))


def test_el_resultado_trae_la_comparacion_con_la_linea_base():
    r = pronostico.pronosticar(SERIE, 2, tecnica="regresion_lineal")
    esperado = pronostico.validar_origen_movil(SERIE, tecnica="regresion_lineal")
    assert (r.mae_modelo, r.mae_ingenuo) == pytest.approx(esperado)
    assert r.mae_modelo < r.mae_ingenuo and r.advertencias == ()  # con tendencia clara, el modelo gana


def test_si_el_modelo_no_mejora_la_linea_base_se_advierte():
    caminata = pd.Series(100 + np.cumsum(np.random.default_rng(7).normal(0, 10, size=30)))
    r = pronostico.pronosticar(caminata, 2, tecnica="regresion_lineal")
    assert r.mae_modelo >= r.mae_ingenuo
    assert len(r.advertencias) == 1 and "línea base" in r.advertencias[0].mensaje


def test_tecnica_desconocida():
    with pytest.raises(ValueError):
        pronostico.pronosticar(SERIE, 2, tecnica="arima")
