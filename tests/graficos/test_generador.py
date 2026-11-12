"""graficos.generador (Tabla 21, RF-15, OE3): los seis tipos, con título, ejes y fuente."""

from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from ciumb_analitica.graficos import generador
from ciumb_analitica.semantica.semilla import capa_semilla
from ciumb_analitica.spec.validador import revisar_datos, validar
from tests.conftest import PENDIENTE, fixture_prompt

pytestmark = PENDIENTE

CAPA = capa_semilla()
FIRMA_PNG = b"\x89PNG\r\n\x1a\n"
ETIQUETAS = {c: m.nombre for c, m in CAPA.metricas.items()} | {c: d.nombre for c, d in CAPA.dimensiones.items()}
RNG = np.random.default_rng(20261111)


def _datos(nombre: str) -> pd.DataFrame:
    """Datos con la forma que devuelve el compilador para cada prompt de la Tabla 22."""
    if nombre == "p01":
        return pd.DataFrame(
            [
                (e, f, 3 + i + j)
                for i, e in enumerate(["aprobado", "en_ejecucion", "finalizado"])
                for j, f in enumerate(["Ciencias Sociales", "Ingeniería"])
            ],
            columns=["estado", "facultad", "proyectos"],
        )
    if nombre == "p02":
        return pd.DataFrame(
            {
                "programa": [f"Programa {c}" for c in "ABCDEFGHI"],
                "practicas": [40, 35, 30, 25, 20, 9, 8, 7, 6],
                "_n_personas": [40, 35, 30, 25, 20, 9, 8, 7, 6],
            }
        )
    if nombre in ("p03", "p09"):
        metrica = "facturacion" if nombre == "p03" else "presupuesto_ejecutado"
        meses = [(a, m) for a in (2025, 2026) for m in range(1, 13) if (a, m) <= (2026, 10)]
        if nombre == "p09":
            meses = [x for x in meses if x[0] == 2026]
        return pd.DataFrame(
            [(a, m, 30.0 + m + (a - 2025) * 4) for a, m in meses], columns=["tiempo_anio", "tiempo_mes", metrica]
        )
    if nombre == "p04":
        return pd.DataFrame(
            [
                (f, 2026, t, 10.0 + 3 * i + t, 1.0 + i, 10.0)
                for i, f in enumerate(["Ciencias Sociales", "Económicas", "Ingeniería"])
                for t in (1, 2, 3)
            ],
            columns=[
                "facultad",
                "tiempo_anio",
                "tiempo_trimestre",
                "pct_hitos_atrasados",
                "pct_hitos_atrasados__num",
                "pct_hitos_atrasados__den",
            ],
        )
    if nombre == "p05":
        n = RNG.integers(1, 7, size=40).astype(float)
        return pd.DataFrame({"n_consultores": n, "satisfaccion": (3 + 0.2 * n).round(1), "_registro": range(40)})
    if nombre == "p06":
        return pd.DataFrame(
            {
                "pct_ejecucion": [35.0, 48.0, 52.0, 55.0, 61.0, 64.0, 70.0, 88.0, 97.0],
                "pct_ejecucion__num": 1.0,
                "pct_ejecucion__den": 1.0,
                "_registro": range(9),
            }
        )
    if nombre == "p07":
        return pd.DataFrame(
            [(2019 + i // 2, i % 2 + 1, 80 + 6 * i, 80 + 6 * i) for i in range(15)],
            columns=["tiempo_anio", "tiempo_semestre", "practicas", "_n_personas"],
        )
    raise KeyError(nombre)


def _generar(nombre: str):
    spec = validar(fixture_prompt(nombre)["spec"], CAPA, hoy=date(2026, 11, 5)).spec
    revision = revisar_datos(spec, _datos(nombre))
    grafico = generador.generar_grafico(
        revision.datos, spec, revision.grafico, titulo=f"Prueba {nombre}", etiquetas=ETIQUETAS
    )
    return revision, grafico


@pytest.mark.parametrize(
    ("nombre", "tipo"),
    [("p01", "barras"), ("p02", "torta"), ("p03", "lineas"), ("p04", "mapa_calor"), ("p05", "dispersion"),
     ("p06", "histograma"), ("p07", "lineas"), ("p09", "lineas")],
)  # fmt: skip
def test_los_seis_tipos_con_titulo_ejes_y_fuente(nombre, tipo):
    revision, grafico = _generar(nombre)
    assert grafico.tipo == tipo == revision.grafico.tipo.value
    assert grafico.png.startswith(FIRMA_PNG) and len(grafico.png) > 2000
    assert grafico.titulo == f"Prueba {nombre}" and grafico.fuente.startswith("Fuente:")
    if tipo != "torta":
        assert grafico.eje_x and grafico.eje_y
    json.dumps(grafico.plotly)  # serializable
    assert grafico.plotly["data"] and grafico.plotly["layout"]["title"]["text"] == f"Prueba {nombre}"


def test_los_ejes_usan_los_nombres_de_la_capa_semantica_no_los_codigos():
    _, grafico = _generar("p03")
    assert "Facturación" in grafico.eje_y and "facturacion" not in grafico.eje_y
    assert "_" not in grafico.eje_x


def test_es_determinista():
    assert _generar("p01")[1].png == _generar("p01")[1].png


def test_p2_la_torta_agrupa_en_otros_y_lo_anota():
    _, grafico = _generar("p02")
    sectores = grafico.plotly["data"][0]
    assert len(sectores["labels"]) == 6 and sectores["labels"][-1] == generador.ETIQUETA_OTROS
    assert sum(sectores["values"]) == 180
    assert any("Otros" in nota for nota in grafico.notas)


def test_agrupar_otros():
    datos = _datos("p02").drop(columns="_n_personas")
    agrupado = generador.agrupar_otros(datos, "programa", "practicas", max_sectores=6)
    assert agrupado["programa"].tolist() == [f"Programa {c}" for c in "ABCDE"] + ["Otros"]
    assert agrupado["practicas"].tolist() == [40, 35, 30, 25, 20, 30]
    assert agrupado["practicas"].sum() == datos["practicas"].sum()
    sin_cambio = generador.agrupar_otros(datos.head(6), "programa", "practicas")
    assert len(sin_cambio) == 6 and "Otros" not in sin_cambio["programa"].tolist()
    assert generador.agrupar_otros(datos, "programa", "practicas", max_sectores=3)["practicas"].tolist() == [
        40,
        35,
        105,
    ]


def test_ninguna_columna_auxiliar_llega_al_grafico():
    for nombre in ("p02", "p05", "p06", "p07"):
        _, grafico = _generar(nombre)
        texto = json.dumps(grafico.plotly)
        assert "_n_personas" not in texto and "_registro" not in texto and "__num" not in texto
