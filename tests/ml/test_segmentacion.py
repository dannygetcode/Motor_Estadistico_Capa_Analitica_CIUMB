"""ml.segmentacion (Tabla 8, INF-EMP-03, P8, OE2): k-medias con silueta contra scikit-learn."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import StandardScaler

from ciumb_analitica.ml import segmentacion
from ciumb_analitica.motor.resultado import MuestraInsuficiente
from tests.conftest import PENDIENTE

pytestmark = PENDIENTE

COLUMNAS = ["practicas", "convenios", "consultorias"]


def _empresas() -> pd.DataFrame:
    """Tres grupos bien separados de 30, 20 y 10 empresas."""
    rng = np.random.default_rng(20261111)
    centros = [(2, 1, 0), (15, 3, 1), (8, 6, 9)]
    filas = [rng.poisson(c, size=(n, 3)) for c, n in zip(centros, (30, 20, 10), strict=True)]
    datos = pd.DataFrame(np.vstack(filas), columns=COLUMNAS).astype(float)
    datos.index = range(1000, 1060)  # sk_empresa
    return datos


def _referencia(datos: pd.DataFrame, k: int):
    x = StandardScaler().fit_transform(datos[COLUMNAS])
    etiquetas = KMeans(n_clusters=k, n_init=10, random_state=segmentacion.SEMILLA).fit_predict(x)
    return x, etiquetas


def test_k_fijo_coincide_con_scikit_learn():
    datos = _empresas()
    r = segmentacion.segmentar(datos, COLUMNAS, k=3)
    x, etiquetas = _referencia(datos, 3)
    assert r.k == 3 and r.etiquetas.index.equals(datos.index)
    assert adjusted_rand_score(etiquetas, r.etiquetas) == pytest.approx(1.0)
    assert r.silueta == pytest.approx(silhouette_score(x, etiquetas))


def test_k_se_elige_por_silueta():
    datos = _empresas()
    r = segmentacion.segmentar(datos, COLUMNAS)
    siluetas = {k: silhouette_score(*_referencia(datos, k)) for k in range(2, 11)}
    assert r.siluetas_por_k == pytest.approx(siluetas)
    assert r.k == max(siluetas, key=lambda k: (round(siluetas[k], 12), -k)) == 3
    assert r.silueta == pytest.approx(siluetas[3])


def test_grupos_ordenados_por_tamano_y_centroides_en_unidades_originales():
    datos = _empresas()
    r = segmentacion.segmentar(datos, COLUMNAS, k=3)
    assert r.tamanos == (30, 20, 10)
    assert r.etiquetas.value_counts().sort_index().tolist() == [30, 20, 10]
    assert r.centroides.columns.tolist() == COLUMNAS and len(r.centroides) == 3
    for grupo in range(3):
        esperado = datos[r.etiquetas == grupo][COLUMNAS].mean()
        assert r.centroides.loc[grupo].to_numpy() == pytest.approx(esperado.to_numpy())


def test_es_reproducible():
    datos = _empresas()
    a = segmentacion.segmentar(datos, COLUMNAS)
    b = segmentacion.segmentar(datos.sample(frac=1.0, random_state=3), COLUMNAS)
    assert a.k == b.k and a.tamanos == b.tamanos
    assert adjusted_rand_score(a.etiquetas.sort_index(), b.etiquetas.sort_index()) == pytest.approx(1.0)


def test_muestra_insuficiente():
    with pytest.raises(MuestraInsuficiente):
        segmentacion.segmentar(_empresas().head(9), COLUMNAS)
    iguales = pd.DataFrame({"practicas": [1.0] * 20, "convenios": [2.0] * 20, "consultorias": [0.0] * 20})
    with pytest.raises(MuestraInsuficiente):
        segmentacion.segmentar(iguales, COLUMNAS)


def test_unir_por_dimension_las_consultas_de_p8():
    resultados = {
        "principal:hecho_practica": pd.DataFrame({"empresa": [1, 2, None], "practicas": [5, 3, 9]}),
        "principal:hecho_convenio": pd.DataFrame({"empresa": [2, 3], "convenios": [1, 4]}),
        "principal:hecho_consultoria": pd.DataFrame({"empresa": [1], "consultorias": [2]}),
    }
    unido = segmentacion.unir_por_dimension(resultados, "empresa", COLUMNAS)
    assert unido["empresa"].tolist() == [1, 2, 3]
    assert unido[COLUMNAS].to_numpy().tolist() == [[5, 0, 2], [3, 1, 0], [0, 4, 0]]
