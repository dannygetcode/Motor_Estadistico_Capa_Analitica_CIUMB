"""motor.inferencia (Tabla 8, RF-04, OE1): contraste con scipy.stats y regla de muestra pequeña (RNF-13)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from ciumb_analitica.motor import inferencia
from ciumb_analitica.motor.resultado import MuestraInsuficiente
from ciumb_analitica.spec import resultado as r
from tests.conftest import PENDIENTE

pytestmark = PENDIENTE

RNG = np.random.default_rng(20261111)
N_CONSULTORES = pd.Series(RNG.integers(1, 7, size=86).astype(float))
SATISFACCION = pd.Series(np.clip(3.0 + 0.2 * N_CONSULTORES + RNG.normal(0, 0.6, size=86), 1, 5).round(1))


@pytest.mark.parametrize(("metodo", "referencia"), [("pearson", stats.pearsonr), ("spearman", stats.spearmanr)])
def test_correlacion_contra_scipy(metodo, referencia):
    obtenido = inferencia.correlacion(N_CONSULTORES, SATISFACCION, metodo=metodo, alfa=0.05)
    esperado = referencia(N_CONSULTORES, SATISFACCION)
    assert obtenido.metodo == metodo and obtenido.n == 86
    assert obtenido.estadistico == pytest.approx(esperado.statistic)
    assert obtenido.valor_p == pytest.approx(esperado.pvalue)
    assert obtenido.significativo is (esperado.pvalue < 0.05)
    assert obtenido.advertencias == ()


def test_correlacion_descarta_pares_con_nulos_y_avisa_muestra_pequena():
    x = pd.Series([1.0, 2.0, 3.0, 4.0, None, 6.0, 7.0])
    y = pd.Series([2.0, 1.0, 4.0, 3.0, 5.0, None, 8.0])
    obtenido = inferencia.correlacion(x, y, metodo="spearman")
    esperado = stats.spearmanr([1, 2, 3, 4, 7], [2, 1, 4, 3, 8])
    assert obtenido.n == 5 and obtenido.estadistico == pytest.approx(esperado.statistic)
    assert [a.codigo for a in obtenido.advertencias] == [r.MUESTRA_PEQUENA]


def test_correlacion_sin_muestra_suficiente():
    with pytest.raises(MuestraInsuficiente):
        inferencia.correlacion(pd.Series([1.0, 2.0]), pd.Series([3.0, 4.0]))
    with pytest.raises(MuestraInsuficiente):
        inferencia.correlacion(pd.Series([1.0, 1.0, 1.0, 1.0]), pd.Series([1.0, 2.0, 3.0, 4.0]))


def test_tabla_contingencia_completa_celdas_ausentes():
    datos = pd.DataFrame({"facultad": ["B", "A", "A"], "estado": ["x", "y", "x"], "proyectos": [3, 5, 7]})
    tabla = inferencia.tabla_contingencia(datos, "facultad", "estado", "proyectos")
    assert tabla.index.tolist() == ["A", "B"] and tabla.columns.tolist() == ["x", "y"]
    assert tabla.to_numpy().tolist() == [[7, 5], [3, 0]]


def test_tabla_contingencia_de_razon_p4():
    datos = pd.DataFrame(
        {
            "facultad": ["Ingeniería", "Ciencias Sociales"],
            "pct_hitos_atrasados": [25.0, 10.0],
            "pct_hitos_atrasados__num": [30.0, 8.0],
            "pct_hitos_atrasados__den": [120.0, 80.0],
        }
    )
    tabla = inferencia.tabla_contingencia_de_razon(datos, "facultad", "pct_hitos_atrasados", ("atrasado", "a_tiempo"))
    assert tabla.columns.tolist() == ["atrasado", "a_tiempo"]
    assert tabla.loc["Ingeniería"].tolist() == [30, 90] and tabla.loc["Ciencias Sociales"].tolist() == [8, 72]


def test_chi_cuadrado_contra_scipy():
    tabla = pd.DataFrame([[30, 90], [8, 72], [25, 55]], index=["A", "B", "C"], columns=["atrasado", "a_tiempo"])
    obtenido = inferencia.chi_cuadrado(tabla, alfa=0.05)
    esperado = stats.chi2_contingency(tabla.to_numpy(), correction=False)
    assert obtenido.estadistico == pytest.approx(esperado.statistic)
    assert obtenido.valor_p == pytest.approx(esperado.pvalue)
    assert (obtenido.grados_libertad, obtenido.n) == (2, 280)
    assert obtenido.significativo is (esperado.pvalue < 0.05)
    assert obtenido.advertencias == ()  # todas las esperadas son >= 5


def test_chi_cuadrado_sin_correccion_de_yates_en_dos_por_dos():
    tabla = pd.DataFrame([[12, 18], [20, 10]])
    obtenido = inferencia.chi_cuadrado(tabla)
    assert obtenido.estadistico == pytest.approx(stats.chi2_contingency(tabla.to_numpy(), correction=False).statistic)
    assert obtenido.estadistico != pytest.approx(stats.chi2_contingency(tabla.to_numpy(), correction=True).statistic)


def test_chi_cuadrado_con_esperado_menor_que_cinco_sale_con_advertencia():
    tabla = pd.DataFrame([[2, 9], [3, 40], [1, 30]])
    esperado = stats.chi2_contingency(tabla.to_numpy(), correction=False)
    assert (esperado.expected_freq < 5).sum() == 3
    obtenido = inferencia.chi_cuadrado(tabla)
    assert obtenido.valor_p == pytest.approx(esperado.pvalue)  # el valor p se reporta igual
    assert [a.codigo for a in obtenido.advertencias] == [r.CHI2_ESPERADO_BAJO]
    assert "3" in obtenido.advertencias[0].mensaje


def test_chi_cuadrado_quita_filas_vacias_y_exige_dos_por_dos():
    con_vacia = pd.DataFrame([[30, 90], [0, 0], [8, 72]])
    assert inferencia.chi_cuadrado(con_vacia).grados_libertad == 1
    with pytest.raises(MuestraInsuficiente):
        inferencia.chi_cuadrado(pd.DataFrame([[30, 90], [0, 0]]))


A = pd.Series(RNG.normal(4.1, 0.5, size=34))
B = pd.Series(RNG.normal(3.8, 0.9, size=27))


def test_t_student_de_welch_contra_scipy():
    obtenido = inferencia.t_student(A, B, alfa=0.05)
    esperado = stats.ttest_ind(A, B, equal_var=False)
    assert obtenido.estadistico == pytest.approx(esperado.statistic)
    assert obtenido.valor_p == pytest.approx(esperado.pvalue)
    assert obtenido.grados_libertad == pytest.approx(esperado.df)
    assert obtenido.n == 61 and obtenido.advertencias == ()
    assert obtenido.valor_p != pytest.approx(stats.ttest_ind(A, B, equal_var=True).pvalue)


def test_mann_whitney_contra_scipy():
    obtenido = inferencia.mann_whitney(A, B)
    esperado = stats.mannwhitneyu(A, B, alternative="two-sided")
    assert obtenido.estadistico == pytest.approx(esperado.statistic)
    assert obtenido.valor_p == pytest.approx(esperado.pvalue)
    assert obtenido.n == 61


def test_pruebas_de_dos_grupos_con_muestras_pequenas():
    pocos = inferencia.t_student(A.head(6), B.head(25))
    assert [a.codigo for a in pocos.advertencias] == [r.MUESTRA_PEQUENA]
    with pytest.raises(MuestraInsuficiente):
        inferencia.t_student(A.head(1), B)
    with pytest.raises(MuestraInsuficiente):
        inferencia.mann_whitney(pd.Series([], dtype=float), B)


def test_dos_grupos():
    datos = pd.DataFrame({"sector": ["Salud", "Tecnología", "Salud", None], "satisfaccion": [4.0, 3.0, 5.0, 1.0]})
    a, b, etiquetas = inferencia.dos_grupos(datos, "satisfaccion", "sector")
    assert etiquetas == ("Salud", "Tecnología") and a.tolist() == [4.0, 5.0] and b.tolist() == [3.0]
    tres = pd.DataFrame({"sector": ["A", "B", "C"], "satisfaccion": [1.0, 2.0, 3.0]})
    with pytest.raises(ValueError, match="dos"):
        inferencia.dos_grupos(tres, "satisfaccion", "sector")
