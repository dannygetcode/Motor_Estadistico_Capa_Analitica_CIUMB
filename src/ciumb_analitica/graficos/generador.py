"""Generador de gráficos: seis tipos de RF-15 (Tabla 21, DA-08, OE3). Librería: Matplotlib (imagen estática
para PDF y DOCX) y Plotly (figura interactiva para HTML).

El tipo NO se decide aquí: llega resuelto en `RevisionDatos.grafico` (lo fijan el validador de specs y
`revisar_datos`). Este módulo dibuja lo que se le pide y es determinista: mismos datos -> misma figura.
Pruebas: `tests/graficos/test_generador.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ciumb_analitica.motor.resultado import PENDIENTE
from ciumb_analitica.spec.resultado import GraficoResuelto, SpecResuelta

ETIQUETA_OTROS = "Otros"


@dataclass(frozen=True)
class Grafico:
    """Gráfico generado.

    tipo: el dibujado. png: imagen (empieza por la firma PNG). plotly: figura como dict JSON-serializable.
    titulo, eje_x, eje_y, fuente: textos mostrados (RF-15 exige título, ejes y fuente de datos).
    notas: lo que el informe debe decir del gráfico (p. ej. «se agruparon 4 categorías en Otros»).
    """

    tipo: str
    png: bytes
    plotly: dict
    titulo: str
    eje_x: str
    eje_y: str
    fuente: str
    notas: tuple[str, ...] = field(default_factory=tuple)


def agrupar_otros(datos: pd.DataFrame, categoria: str, metrica: str, max_sectores: int = 6) -> pd.DataFrame:
    """Deja las `max_sectores - 1` categorías mayores y suma el resto en «Otros» (Tabla 21, Figura 13).

    Salida: a lo sumo `max_sectores` filas, ordenadas de mayor a menor con «Otros» al final. El total se
    conserva. Si hay `max_sectores` categorías o menos, solo ordena. En empate, orden alfabético.
    """
    raise NotImplementedError(PENDIENTE)


def generar_grafico(
    datos: pd.DataFrame,
    spec: SpecResuelta,
    grafico: GraficoResuelto,
    *,
    titulo: str,
    etiquetas: dict[str, str],
    fuente: str = "Fuente: datawarehouse del CIUMB.",
    analisis: object | None = None,
) -> Grafico:
    """Dibuja `grafico.tipo` con los datos ya revisados.

    Entradas: `datos` = `RevisionDatos.datos` (columnas de `spec.convenciones`); `grafico` =
    `RevisionDatos.grafico`; `etiquetas` = código de métrica o dimensión -> nombre legible (de la capa
    semántica); `analisis` = resultado del motor o de ML cuando el gráfico lo necesita.
    Por tipo:
      barras       1 dimensión: barras simples; 2 dimensiones: barras agrupadas (la segunda es la leyenda).
      lineas       eje x = tiempo; una serie por categoría si hay otra dimensión; con `ResultadoPronostico`
                   dibuja el pronóstico punteado y su intervalo sombreado.
      torta        usa `agrupar_otros` con `grafico.max_sectores`.
      dispersion   las dos primeras métricas; con `ResultadoSegmentacion`, color por grupo.
      mapa_calor   filas = primera dimensión, columnas = segunda, color = métrica, valor en cada celda.
      histograma   la primera métrica; clases por la regla de Freedman-Diaconis (`numpy.histogram_bin_edges`
                   con bins="fd"); con `ResultadoAtipicos`, marca los límites.
    Salida: `Grafico`. Identidad UMB: colores y tipografía en `exportacion/identidad.py`.
    Nunca rotula con dimensiones que identifican personas ni muestra la razón social de una empresa.
    """
    raise NotImplementedError(PENDIENTE)
