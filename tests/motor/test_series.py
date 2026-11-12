"""motor.series (Tabla 8, RF-03, OE1): agregación temporal, variación porcentual y acumulados."""

from __future__ import annotations

import pandas as pd
import pytest

from ciumb_analitica.motor import series
from ciumb_analitica.spec.modelos import Granularidad
from tests.conftest import PENDIENTE

pytestmark = PENDIENTE


def _mensual() -> pd.DataFrame:
    """Enero de 2025 a octubre de 2026, como la consulta de P3 (Figuras 10 y 12)."""
    filas = [(a, m, 10.0 * m + (5.0 if a == 2026 else 0.0)) for a in (2025, 2026) for m in range(1, 13)]
    datos = pd.DataFrame(filas, columns=["tiempo_anio", "tiempo_mes", "facturacion"])
    return datos[~((datos["tiempo_anio"] == 2026) & (datos["tiempo_mes"] > 10))]


def test_a_serie_mensual_ordenada_con_indice_de_periodos():
    desordenado = _mensual().sample(frac=1.0, random_state=1)
    s = series.a_serie(desordenado, "facturacion", Granularidad.MES)
    assert isinstance(s.index, pd.PeriodIndex) and s.index.freqstr == "M"
    assert (str(s.index[0]), str(s.index[-1]), len(s)) == ("2025-01", "2026-10", 22)
    assert s.iloc[0] == 10.0 and s.iloc[-1] == 105.0


def test_a_serie_completa_periodos_faltantes():
    con_hueco = _mensual().query("not (tiempo_anio == 2025 and tiempo_mes == 3)")
    assert series.a_serie(con_hueco, "facturacion", Granularidad.MES).loc["2025-03"] == 0.0
    sin_completar = series.a_serie(con_hueco, "facturacion", Granularidad.MES, completar=False)
    assert len(sin_completar) == 21


@pytest.mark.parametrize(
    ("granularidad", "columna", "valores", "primero"),
    [
        (Granularidad.TRIMESTRE, "tiempo_trimestre", [1, 2, 3, 4], "2025Q1"),
        (Granularidad.SEMESTRE, "tiempo_semestre", [1, 2], "2025"),
        (Granularidad.ANIO, None, [None], "2025"),
    ],
)
def test_a_serie_otras_granularidades(granularidad, columna, valores, primero):
    filas = [
        {"tiempo_anio": a, "practicas": 10 * a} | ({columna: v} if columna else {})
        for a in (2025, 2026)
        for v in valores
    ]
    s = series.a_serie(pd.DataFrame(filas), "practicas", granularidad)
    assert len(s) == 2 * len(valores)
    assert str(s.index[0]).startswith(primero)
    assert s.index.is_monotonic_increasing


def test_variacion_porcentual():
    s = pd.Series([100.0, 110.0, 99.0, 0.0, 50.0])
    v = series.variacion_porcentual(s)
    assert pd.isna(v.iloc[0])
    assert v.iloc[1:4].tolist() == pytest.approx([10.0, -10.0, -100.0])
    assert pd.isna(v.iloc[4])  # el anterior es 0: sin variación definida, no infinito
    pd.testing.assert_series_equal(v.iloc[:4], s.pct_change().mul(100).iloc[:4])


def test_variacion_con_rezago_de_doce_es_interanual():
    s = series.a_serie(_mensual(), "facturacion", Granularidad.MES)
    v = series.variacion_porcentual(s, rezago=12)
    assert v.iloc[:12].isna().all()
    assert v.loc["2026-01"] == pytest.approx(50.0)  # 15 frente a 10
    assert v.loc["2026-10"] == pytest.approx(5.0)  # 105 frente a 100


def test_acumulado_se_reinicia_cada_anio():
    s = series.a_serie(_mensual(), "facturacion", Granularidad.MES)
    a = series.acumulado(s)
    assert a.loc["2025-12"] == pytest.approx(780.0) and a.loc["2026-01"] == pytest.approx(15.0)
    assert series.acumulado(s, reiniciar_cada_anio=False).iloc[-1] == pytest.approx(s.sum())


def test_variacion_interanual_compara_el_mismo_tramo():
    s = series.a_serie(_mensual(), "facturacion", Granularidad.MES)
    r = series.variacion_interanual(s)
    assert r["n_periodos"] == 10
    assert r["actual"] == pytest.approx(600.0)  # enero-octubre de 2026
    assert r["anterior"] == pytest.approx(550.0)  # enero-octubre de 2025, no los 780 del año completo
    assert r["variacion_pct"] == pytest.approx(100 * 50 / 550)
    assert (str(r["periodo_maximo"]), r["valor_maximo"]) == ("2026-10", 105.0)


def test_variacion_interanual_sin_base():
    s = pd.Series([0.0, 0.0, 5.0, 7.0], index=pd.period_range("2025-01", periods=4, freq="2Q"))
    assert series.variacion_interanual(s)["variacion_pct"] is None
