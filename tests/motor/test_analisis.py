"""motor.analisis: del método de la spec a las secciones del contrato, con las cifras de las librerías de referencia.

Cada caso arma los datos con la forma que devuelve el compilador, calcula las secciones, las empaqueta en un
contrato y comprueba (1) que las cifras son las de SciPy / statsmodels / scikit-learn llamados directamente,
(2) que no viaja ninguna dimensión interna y (3) que el texto de plantilla de ese contrato pasa el validador de
cifras (invariante 10: el modo degradado siempre produce el informe).
"""

from __future__ import annotations

import hashlib
import warnings
from datetime import date

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from ciumb_analitica.contrato.empaquetador import empaquetar
from ciumb_analitica.motor import analisis
from ciumb_analitica.semantica.semilla import capa_semilla
from ciumb_analitica.spec.validador import validar
from ciumb_analitica.validador_cifras.plantilla import plantilla_por_defecto
from ciumb_analitica.validador_cifras.validador import validar_narrativa
from tests.conftest import fixture_prompt

CAPA = capa_semilla()
HOY = date(2026, 11, 5)
RNG = np.random.default_rng(20261111)


def _spec(datos: dict):
    resultado = validar(datos, CAPA, hoy=HOY)
    assert resultado.spec is not None, resultado.problemas
    return resultado.spec


def _base(**campos) -> dict:
    return {"esquema": "ciumb.spec/1.0", "origen": "prompt", "alcance": {"rol": "directivo"}} | campos


def _indicador(calculo, id_: str, **grupo):
    for s in calculo.secciones:
        for i in s.indicadores:
            if i["id"] == id_ and (i.get("grupo") or {}) == grupo:
                return i
    raise KeyError(id_)


def _verificar_plantilla(spec, calculo, periodo=None):
    contrato = empaquetar(
        spec, spec.grafico, calculo.secciones, capa=CAPA, id_spec="esp-20261105-0001",
        huella_datos=hashlib.sha256(b"x").hexdigest(), periodo_datos=periodo,
    )  # fmt: skip
    assert validar_narrativa(plantilla_por_defecto(contrato), contrato, extra=calculo.extra).aprobado
    return contrato


def test_frecuencias_relativas_y_total():
    spec = _spec(fixture_prompt("p02")["spec"])
    datos = pd.DataFrame({"programa": ["A", "B", "C"], "practicas": [50, 30, 20]})
    calculo = analisis.calcular(spec, datos, CAPA)
    assert _indicador(calculo, "practicas_total")["valor"] == 100
    assert _indicador(calculo, "practicas", programa="B")["valor"] == 30
    assert _indicador(calculo, "practicas_participacion", programa="B")["valor"] == pytest.approx(0.3)
    assert _indicador(calculo, "practicas_maximo", programa="A")["valor"] == 50
    _verificar_plantilla(spec, calculo, (date(2026, 7, 1), date(2026, 10, 31)))


def test_una_razon_por_grupo_se_recalcula_desde_sus_componentes():
    spec = _spec(fixture_prompt("p04")["spec"])
    datos = pd.DataFrame(
        {
            "facultad": ["A", "A", "B"], "tiempo_anio": [2026] * 3, "tiempo_trimestre": [1, 2, 1],
            "pct_hitos_atrasados": [50.0, 10.0, 20.0],
            "pct_hitos_atrasados__num": [1.0, 10.0, 4.0], "pct_hitos_atrasados__den": [2.0, 100.0, 20.0],
        }
    )  # fmt: skip
    prueba = pd.DataFrame(
        {"facultad": ["A", "B", "C"], "pct_hitos_atrasados__num": [30.0, 8.0, 25.0],
         "pct_hitos_atrasados__den": [120.0, 80.0, 80.0], "pct_hitos_atrasados": [25.0, 10.0, 31.25]}
    )  # fmt: skip
    calculo = analisis.calcular(spec, datos, CAPA, prueba=prueba)
    assert _indicador(calculo, "pct_hitos_atrasados_total")["valor"] == pytest.approx(100 * 15 / 122)
    referencia = stats.chi2_contingency([[30, 90], [8, 72], [25, 55]], correction=False)
    chi = _indicador(calculo, "chi_cuadrado")
    assert chi["valor"] == pytest.approx(referencia.statistic) and chi["valor_p"] == pytest.approx(referencia.pvalue)
    assert chi["n"] == 280 and _indicador(calculo, "grados_libertad")["valor"] == 2
    assert _indicador(calculo, "frecuencia", facultad="A", estado_hito="atrasado")["valor"] == 30
    assert 0.05 in calculo.extra
    _verificar_plantilla(spec, calculo)


def test_descriptiva_con_atipicos_p6():
    spec = _spec(fixture_prompt("p06")["spec"])
    valores = [35.0, 48.0, 52.0, 55.0, 61.0, 64.0, 70.0, 88.0, 197.0]
    datos = pd.DataFrame({"pct_ejecucion": valores, "pct_ejecucion__num": valores, "pct_ejecucion__den": 100.0})
    calculo = analisis.calcular(spec, datos, CAPA)
    assert _indicador(calculo, "pct_ejecucion_media")["valor"] == pytest.approx(np.mean(valores))
    assert _indicador(calculo, "pct_ejecucion_desviacion")["valor"] == pytest.approx(np.std(valores, ddof=1))
    assert _indicador(calculo, "pct_ejecucion_atipicos")["valor"] == 1
    q1, q3 = np.percentile(valores, [25, 75])
    assert _indicador(calculo, "pct_ejecucion_limite_superior")["valor"] == pytest.approx(q3 + 1.5 * (q3 - q1))
    assert calculo.analisis.cantidad == 1 and 1.5 in calculo.extra
    _verificar_plantilla(spec, calculo)


def test_correlacion_p5_contra_scipy():
    spec = _spec(fixture_prompt("p05")["spec"])
    n = RNG.integers(1, 7, size=40).astype(float)
    datos = pd.DataFrame({"n_consultores": n, "satisfaccion": np.clip(3 + 0.2 * n + RNG.normal(0, 0.5, 40), 1, 5)})
    calculo = analisis.calcular(spec, datos, CAPA)
    referencia = stats.spearmanr(datos["n_consultores"], datos["satisfaccion"])
    rho = _indicador(calculo, "rho_spearman")
    assert rho["valor"] == pytest.approx(referencia.statistic) and rho["valor_p"] == pytest.approx(referencia.pvalue)
    assert rho["n"] == 40
    _verificar_plantilla(spec, calculo, (date(2025, 11, 1), date(2026, 10, 31)))


def test_variacion_interanual_p3():
    spec = _spec(fixture_prompt("p03")["spec"])
    filas = [(a, m, 10.0 * m + (5.0 if a == 2026 else 0.0)) for a in (2025, 2026) for m in range(1, 13)]
    datos = pd.DataFrame(filas, columns=["tiempo_anio", "tiempo_mes", "facturacion"]).query(
        "not (tiempo_anio == 2026 and tiempo_mes > 10)"
    )
    calculo = analisis.calcular(spec, datos, CAPA)
    tramo = _indicador(calculo, "facturacion_2026")
    assert (tramo["valor"], tramo["anterior"]) == (600, 550)
    assert tramo["variacion_pct"] == pytest.approx(100 * 50 / 550)
    mayor = _indicador(calculo, "facturacion_periodo_mayor")
    assert (mayor["mes"], mayor["valor"]) == ("2026-10", 105)
    _verificar_plantilla(spec, calculo)


def test_pronostico_p7_contra_statsmodels():
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    spec = _spec(fixture_prompt("p07")["spec"])
    valores = [80 + 6 * i + (i % 3) for i in range(15)]
    datos = pd.DataFrame(
        {"tiempo_anio": [2019 + i // 2 for i in range(15)], "tiempo_semestre": [i % 2 + 1 for i in range(15)],
         "practicas": valores}
    )  # fmt: skip
    calculo = analisis.calcular(spec, datos, CAPA, publicar_pronostico=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        punto = ExponentialSmoothing(np.array(valores, float), trend="add", initialization_method="estimated").fit()
    primero = _indicador(calculo, "practicas_pronostico", tiempo="2026-S2")
    assert primero["valor"] == pytest.approx(float(punto.forecast(1)[0]), rel=1e-6)
    assert primero["ic_inferior"] < primero["valor"] < primero["ic_superior"]
    assert 95 in calculo.extra and 2 in calculo.extra
    _verificar_plantilla(spec, calculo)
    sin_publicar = analisis.calcular(spec, datos, CAPA, publicar_pronostico=False)
    assert not any(i["id"] == "practicas_pronostico" for s in sin_publicar.secciones for i in s.indicadores)


def test_segmentacion_p8_solo_tamanos_y_centroides():
    spec = _spec(fixture_prompt("p08")["spec"])
    centros = [(2, 1, 0), (15, 3, 1), (8, 6, 9)]
    bloques = [RNG.poisson(c, size=(n, 3)) for c, n in zip(centros, (30, 20, 3), strict=True)]
    datos = pd.DataFrame(np.vstack(bloques), columns=["practicas", "convenios", "consultorias"]).astype(float)
    datos.insert(0, "empresa", range(1000, 1053))
    calculo = analisis.calcular(spec, datos, CAPA)
    ids = {i["id"] for s in calculo.secciones for i in s.indicadores}
    assert {"k", "silueta", "tamano"} <= ids
    grupos = [i.get("grupo") for s in calculo.secciones for i in s.indicadores if i.get("grupo")]
    assert all(set(g) == {"segmento"} for g in grupos)
    tamanos = {i["grupo"]["segmento"]: i["valor"] for i in calculo.secciones[0].indicadores if i["id"] == "tamano"}
    centroides = {i["grupo"]["segmento"] for i in calculo.secciones[0].indicadores if i["id"].endswith("_centroide")}
    assert centroides == {g for g, n in tamanos.items() if n >= analisis.MIN_UNIDADES_CENTROIDE}
    _verificar_plantilla(spec, calculo, (date(2025, 11, 1), date(2026, 10, 31)))


def test_una_dimension_interna_no_se_publica_por_grupo():
    spec = _spec(_base(metricas=[{"id": "practicas", "agregacion": "conteo"}], dimensiones=[{"id": "empresa"}],
                       analisis={"metodo": "frecuencias"}))  # fmt: skip
    datos = pd.DataFrame({"empresa": [1, 2, 3], "practicas": [5, 6, 7]})
    calculo = analisis.calcular(spec, datos, CAPA)
    assert [i["id"] for i in calculo.secciones[0].indicadores] == ["practicas_total"]
    assert any("empresa" in a for a in calculo.secciones[0].advertencias)


def test_dos_grupos_contra_scipy_y_metodo_no_aplicable():
    spec = _spec(_base(metricas=[{"id": "satisfaccion"}],
                       analisis={"metodo": "t_student", "variables": ["satisfaccion", "sector"]}))  # fmt: skip
    a, b = RNG.normal(4.1, 0.5, 30), RNG.normal(3.8, 0.9, 25)
    datos = pd.DataFrame({"sector": ["Salud"] * 30 + ["Tecnología"] * 25, "satisfaccion": np.concatenate([a, b])})
    calculo = analisis.calcular(spec, datos, CAPA)
    referencia = stats.ttest_ind(a, b, equal_var=False)
    t = _indicador(calculo, "t")
    assert t["valor"] == pytest.approx(referencia.statistic) and t["valor_p"] == pytest.approx(referencia.pvalue)
    assert _indicador(calculo, "grados_libertad")["valor"] == pytest.approx(referencia.df)
    _verificar_plantilla(spec, calculo, (date(2025, 11, 1), date(2026, 10, 31)))
    tres = datos.assign(sector=["A", "B", "C"] * 18 + ["A"])
    with pytest.raises(analisis.AnalisisNoAplicable, match="dos"):
        analisis.calcular(spec, tres, CAPA)


def test_tabla_para_exportar_sin_columnas_auxiliares():
    datos = pd.DataFrame({"facultad": ["A"], "pct": [1.0], "pct__num": [1.0], "pct__den": [1.0], "_n_personas": [9]})
    tabla = analisis.tabla_para_exportar(datos, {"facultad": "Facultad"})
    assert tabla.columns.tolist() == ["Facultad", "pct"]


def test_tabla_para_exportar_combina_las_columnas_de_tiempo():
    datos = pd.DataFrame({"tiempo_anio": [2026, 2025], "tiempo_trimestre": [1, 4], "facultad": ["A", "B"], "n": [3, 4]})
    tabla = analisis.tabla_para_exportar(datos, {"tiempo": "Tiempo"})
    assert tabla.columns.tolist() == ["Tiempo", "facultad", "n"]
    assert tabla["Tiempo"].tolist() == ["2025-T4", "2026-T1"]


def test_una_semiaditiva_no_se_suma_entre_cortes():
    """`proyectos` es una instantánea (D-18): el total y la variación usan cortes, nunca la suma de los meses."""
    spec = _spec(_base(metricas=[{"id": "proyectos", "agregacion": "conteo"}],
                       dimensiones=[{"id": "tiempo", "granularidad": "mes"}],
                       periodo={"desde": "2025-01-01", "hasta": "2026-10-31"},
                       analisis={"metodo": "variacion_interanual"}))  # fmt: skip
    filas = [(a, m, 100 + m + (10 if a == 2026 else 0)) for a in (2025, 2026) for m in range(1, 13)]
    datos = pd.DataFrame(filas, columns=["tiempo_anio", "tiempo_mes", "proyectos"]).query(
        "not (tiempo_anio == 2026 and tiempo_mes > 10)"
    )
    calculo = analisis.calcular(spec, datos, CAPA)
    corte = _indicador(calculo, "proyectos_2026")
    assert (corte["valor"], corte["anterior"]) == (120, 110)  # octubre de 2026 frente a octubre de 2025
    assert "corte" in corte["metodo"]
    frecuencias = analisis.calcular(spec.model_copy(update={"analisis": spec.analisis.__class__(
        metodo="variacion")}), datos.query("tiempo_mes != 5"), CAPA)  # fmt: skip
    serie = [i for i in frecuencias.secciones[0].indicadores if i["id"] == "proyectos" and i.get("mes") == "2025-05"]
    assert serie == []  # un corte que falta queda vacío, no en 0
    _verificar_plantilla(spec, calculo)
