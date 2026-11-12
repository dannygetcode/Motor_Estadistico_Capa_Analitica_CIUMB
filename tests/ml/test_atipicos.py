"""ml.atipicos (Tabla 8, RF-05, OE2): rango intercuartílico de Tukey y puntaje Z contra NumPy y SciPy."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from ciumb_analitica.ml import atipicos
from ciumb_analitica.motor.resultado import MuestraInsuficiente
from tests.conftest import PENDIENTE

pytestmark = PENDIENTE

RNG = np.random.default_rng(20261111)
VALORES = pd.Series(np.concatenate([RNG.normal(60, 8, size=48), [5.0, 140.0]]), index=range(100, 150))


@pytest.mark.parametrize("k", [1.5, 3.0])
def test_ric_contra_numpy_y_scipy(k):
    r = atipicos.atipicos_ric(VALORES, k=k)
    q1, q3 = np.percentile(VALORES, [25, 75])
    ric = stats.iqr(VALORES)
    assert r.metodo == "RIC" and r.k == k and r.n == 50
    assert r.limite_inferior == pytest.approx(q1 - k * ric) and r.limite_superior == pytest.approx(q3 + k * ric)
    esperado = (q1 - k * ric > VALORES) | (q3 + k * ric < VALORES)
    pd.testing.assert_series_equal(r.es_atipico, esperado, check_names=False)
    assert r.cantidad == int(esperado.sum()) >= 2
    assert r.es_atipico.loc[148] and r.es_atipico.loc[149]  # los dos valores extremos, con su índice original


def test_ric_caso_de_libro():
    r = atipicos.atipicos_ric(pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 100]))
    assert (r.limite_inferior, r.limite_superior) == pytest.approx((-3.5, 14.5))  # Q1 = 3,25; Q3 = 7,75
    assert r.es_atipico.tolist() == [False] * 9 + [True]


def test_puntaje_z_contra_scipy():
    r = atipicos.atipicos_z(VALORES, umbral=3.0)
    z = stats.zscore(VALORES, ddof=1)
    pd.testing.assert_series_equal(r.es_atipico, pd.Series(np.abs(z) > 3.0, index=VALORES.index), check_names=False)
    assert r.metodo == "puntaje_z"
    assert r.limite_superior == pytest.approx(VALORES.mean() + 3.0 * VALORES.std(ddof=1))
    assert r.limite_inferior == pytest.approx(VALORES.mean() - 3.0 * VALORES.std(ddof=1))


def test_los_nulos_no_son_atipicos_ni_cuentan():
    con_nulos = pd.Series([1.0, 2.0, None, 3.0, 4.0, 50.0, np.nan])
    r = atipicos.atipicos_ric(con_nulos)
    assert r.n == 5 and r.es_atipico.tolist() == [False, False, False, False, False, True, False]
    assert len(r.es_atipico) == len(con_nulos)


def test_muestra_insuficiente():
    with pytest.raises(MuestraInsuficiente):
        atipicos.atipicos_ric(pd.Series([1.0, 2.0, 300.0]))
    with pytest.raises(MuestraInsuficiente):
        atipicos.atipicos_z(pd.Series([5.0, 5.0, 5.0, 5.0]))


def test_detectar_despacha_segun_la_spec():
    assert atipicos.detectar(VALORES, metodo="RIC", k=1.5).metodo == "RIC"
    z = atipicos.detectar(VALORES, metodo="puntaje_z", k=2.5)
    assert (z.metodo, z.k) == ("puntaje_z", 2.5)
    with pytest.raises(ValueError):
        atipicos.detectar(VALORES, metodo="DBSCAN")
