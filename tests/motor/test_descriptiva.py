"""motor.descriptiva (Tabla 8, RF-02, OE1): contraste con NumPy y SciPy."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from ciumb_analitica.motor import descriptiva
from ciumb_analitica.motor.resultado import MuestraInsuficiente
from tests.conftest import PENDIENTE

pytestmark = PENDIENTE

RNG = np.random.default_rng(20261111)
VALORES = pd.Series(np.round(RNG.gamma(shape=2.0, scale=30.0, size=57), 2))


def test_resumen_contra_numpy_y_scipy():
    r = descriptiva.resumen(VALORES, percentiles=(5, 10, 90, 95))
    x = VALORES.to_numpy()
    assert r.n == 57
    assert r.media == pytest.approx(np.mean(x))
    assert r.mediana == pytest.approx(np.median(x))
    assert r.desviacion == pytest.approx(np.std(x, ddof=1))
    assert r.desviacion == pytest.approx(stats.tstd(x))
    assert (r.minimo, r.maximo) == (x.min(), x.max())
    assert r.q1 == pytest.approx(np.percentile(x, 25)) and r.q3 == pytest.approx(np.percentile(x, 75))
    assert r.q3 - r.q1 == pytest.approx(stats.iqr(x))
    for p in (5, 10, 90, 95):
        assert r.percentiles[p] == pytest.approx(np.percentile(x, p))


def test_resumen_caso_de_libro():
    r = descriptiva.resumen(pd.Series([2, 4, 4, 4, 5, 5, 7, 9]))
    assert (r.n, r.media, r.mediana, r.moda) == (8, 5.0, 4.5, 4.0)
    assert r.desviacion == pytest.approx(2.13809, abs=1e-5)  # muestral; la poblacional sería 2,0
    assert (r.q1, r.q3) == (4.0, 5.5)


def test_resumen_ignora_nulos_y_casos_limite():
    r = descriptiva.resumen(pd.Series([10.0, None, 20.0, np.nan]))
    assert (r.n, r.media) == (2, 15.0)
    uno = descriptiva.resumen(pd.Series([7.0]))
    assert (uno.n, uno.media, uno.desviacion, uno.moda) == (1, 7.0, None, None)
    assert descriptiva.resumen(pd.Series([1.0, 2.0, 3.0])).moda is None  # todos distintos
    assert descriptiva.resumen(pd.Series([3.0, 1.0, 3.0, 1.0])).moda == 1.0  # la menor de las modas
    with pytest.raises(MuestraInsuficiente):
        descriptiva.resumen(pd.Series([None, np.nan]))


def test_resumen_por_grupo():
    datos = pd.DataFrame({"linea": ["B"] * 4 + ["A"] * 5, "pct_ejecucion": [10, 20, 30, 40, 5, 5, 6, 8, 100]})
    r = descriptiva.resumen_por_grupo(datos, ["linea"], "pct_ejecucion")
    assert r["linea"].tolist() == ["A", "B"]
    a = r.set_index("linea").loc["A"]
    assert (a["n"], a["mediana"], a["maximo"]) == (5, 6, 100)
    assert a["media"] == pytest.approx(24.8) and a["desviacion"] == pytest.approx(np.std([5, 5, 6, 8, 100], ddof=1))
    assert r.set_index("linea").loc["B", "q1"] == pytest.approx(17.5)


def test_frecuencias_relativas_suman_uno():
    datos = pd.DataFrame({"programa": ["A", "B", "C"], "practicas": [50, 30, 20]})
    r = descriptiva.frecuencias(datos, ["programa"], "practicas", relativas=True)
    assert r["frecuencia_relativa"].tolist() == pytest.approx([0.5, 0.3, 0.2])
    assert r["frecuencia_relativa"].sum() == pytest.approx(1.0)
    assert "frecuencia_relativa" not in descriptiva.frecuencias(datos, ["programa"], "practicas").columns
    ceros = descriptiva.frecuencias(datos.assign(practicas=0), ["programa"], "practicas", relativas=True)
    assert ceros["frecuencia_relativa"].isna().all()


def test_razon_total_se_recalcula_desde_los_componentes():
    datos = pd.DataFrame(
        {
            "facultad": ["A", "B"],
            "pct_hitos_atrasados": [50.0, 10.0],
            "pct_hitos_atrasados__num": [1.0, 10.0],
            "pct_hitos_atrasados__den": [2.0, 100.0],
        }
    )
    total = descriptiva.razon_total(datos, "pct_hitos_atrasados")
    assert total == pytest.approx(100 * 11 / 102)
    assert total != pytest.approx(30.0)  # no es el promedio de 50 y 10
    assert descriptiva.razon_total(datos.assign(pct_hitos_atrasados__den=0.0), "pct_hitos_atrasados") is None
