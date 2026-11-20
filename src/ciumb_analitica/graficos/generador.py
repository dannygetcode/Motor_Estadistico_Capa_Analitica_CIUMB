"""Generador de gráficos: seis tipos de RF-15 (Tabla 21, DA-08, OE3). Librería: Matplotlib (imagen estática
para PDF y DOCX) y Plotly (figura interactiva para HTML).

El tipo NO se decide aquí: llega resuelto en `RevisionDatos.grafico` (lo fijan el validador de specs y
`revisar_datos`). Este módulo dibuja lo que se le pide y es determinista: mismos datos -> misma figura.
Pruebas: `tests/graficos/test_generador.py`.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field

import matplotlib

matplotlib.use("Agg")  # sin pantalla; determinista

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402

from ciumb_analitica.exportacion import identidad  # noqa: E402
from ciumb_analitica.motor.resultado import (  # noqa: E402
    ResultadoAtipicos,
    ResultadoPronostico,
    ResultadoSegmentacion,
)
from ciumb_analitica.motor.series import _periodo  # noqa: E402
from ciumb_analitica.spec.convenciones import (  # noqa: E402
    DIMENSION_TIEMPO,
    SUFIJO_DEN,
    SUFIJO_NUM,
    columnas_de_dimension,
)
from ciumb_analitica.spec.modelos import Granularidad, TipoGrafico  # noqa: E402
from ciumb_analitica.spec.resultado import MAX_SECTORES_TORTA, GraficoResuelto, SpecResuelta  # noqa: E402

ETIQUETA_OTROS = "Otros"
DIMENSIONES_SIN_ROTULO = frozenset({"empresa", "macroproyecto"})
"""Dimensiones con `viaja_a_ia = False`: se dibujan con rótulos genéricos («Empresa 1»), nunca con su nombre."""

TAMANO = (8.0, 4.5)
DPI = 120
_ESTILO = {
    "font.family": identidad.FUENTE,
    "font.size": 9,
    "axes.edgecolor": identidad.GRIS_SUAVE,
    "axes.labelcolor": identidad.GRIS_TEXTO,
    "axes.titleweight": "bold",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "xtick.color": identidad.GRIS_TEXTO,
    "ytick.color": identidad.GRIS_TEXTO,
    "svg.hashsalt": "ciumb",
    "path.simplify": False,
}


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


# --- Utilidades --------------------------------------------------------------------------------------------------


def _columnas_visibles(datos: pd.DataFrame) -> list[str]:
    return [c for c in datos.columns if not c.startswith("_") and not c.endswith((SUFIJO_NUM, SUFIJO_DEN))]


def _etiqueta_periodo(fila: pd.Series, granularidad: Granularidad) -> str:
    anio = int(fila["tiempo_anio"])
    if granularidad is Granularidad.MES:
        return f"{anio}-{int(fila['tiempo_mes']):02d}"
    if granularidad is Granularidad.TRIMESTRE:
        return f"{anio}-T{int(fila['tiempo_trimestre'])}"
    if granularidad is Granularidad.SEMESTRE:
        return f"{anio}-S{int(fila['tiempo_semestre'])}"
    return str(anio)


def _etiqueta_de_periodo(periodo: pd.Period, granularidad: Granularidad) -> str:
    if granularidad is Granularidad.MES:
        return f"{periodo.year}-{periodo.month:02d}"
    if granularidad is Granularidad.TRIMESTRE:
        return f"{periodo.year}-T{periodo.quarter}"
    if granularidad is Granularidad.SEMESTRE:
        return f"{periodo.year}-S{(periodo.quarter + 1) // 2}"
    return str(periodo.year)


class _Ejes:
    """Columnas del resultado traducidas a lo que se dibuja: categorías legibles y orden estable."""

    def __init__(self, datos: pd.DataFrame, spec: SpecResuelta, etiquetas: dict[str, str]):
        self.datos = datos.reset_index(drop=True).copy()
        self.etiquetas = etiquetas
        self.granularidad = spec.granularidad() or Granularidad.MES
        self.metricas = [m.id for m in spec.metricas if m.id in self.datos.columns]
        self.dimensiones: list[str] = []  # nombres de columnas de categoría ya preparadas
        self.nombres_dim: dict[str, str] = {}
        for dimension in spec.dimensiones:
            columnas = [c for c in columnas_de_dimension(dimension) if c in self.datos.columns]
            if not columnas:
                continue
            if dimension.id == DIMENSION_TIEMPO:
                orden = self.datos.sort_values(columnas, kind="mergesort").index
                self.datos = self.datos.loc[orden].reset_index(drop=True)
                self.datos["__tiempo"] = [_etiqueta_periodo(f, self.granularidad) for _, f in self.datos.iterrows()]
                self.dimensiones.append("__tiempo")
                self.nombres_dim["__tiempo"] = etiquetas.get(DIMENSION_TIEMPO, "Periodo")
            else:
                columna = columnas[0]
                if dimension.id in DIMENSIONES_SIN_ROTULO:
                    codigos = {v: i for i, v in enumerate(sorted(self.datos[columna].dropna().unique(), key=str), 1)}
                    nombre = etiquetas.get(dimension.id, "Unidad")
                    self.datos[columna] = self.datos[columna].map(lambda v, c=codigos, n=nombre: f"{n} {c.get(v, '')}")
                self.datos[columna] = self.datos[columna].astype(str)
                self.dimensiones.append(columna)
                self.nombres_dim[columna] = etiquetas.get(dimension.id, columna.replace("_", " ").capitalize())

    def nombre(self, codigo: str) -> str:
        return self.nombres_dim.get(codigo) or self.etiquetas.get(codigo) or codigo.replace("_", " ").capitalize()

    def tiempo(self) -> str | None:
        return "__tiempo" if "__tiempo" in self.dimensiones else None

    def categorias(self) -> list[str]:
        return [d for d in self.dimensiones if d != "__tiempo"]


def _agregar(d: pd.DataFrame, por: list[str], metrica: str) -> pd.Series:
    """Valor de `metrica` por combinación de `por`. Una razón se recalcula desde sus componentes (100 * num / den);
    nunca se suman ni promedian porcentajes (4.4.2, paso 3). El resto se suma (métricas aditivas ya agregadas)."""
    num, den = f"{metrica}{SUFIJO_NUM}", f"{metrica}{SUFIJO_DEN}"
    if num in d.columns and den in d.columns:
        partes = d.groupby(por, sort=False)[[num, den]].sum()
        return (100.0 * partes[num] / partes[den].where(partes[den] != 0)).rename(metrica)
    return d.groupby(por, sort=False)[metrica].sum()


def _png(figura) -> bytes:
    salida = io.BytesIO()
    figura.savefig(salida, format="png", dpi=DPI, metadata={"Software": None}, bbox_inches="tight")
    plt.close(figura)
    return salida.getvalue()


def _plotly(figura: go.Figure, titulo: str, eje_x: str, eje_y: str, fuente: str) -> dict:
    figura.update_layout(
        title={"text": titulo},
        xaxis_title=eje_x or None,
        yaxis_title=eje_y or None,
        font={"family": identidad.FUENTE_DOCUMENTO, "color": identidad.GRIS_TEXTO},
        colorway=list(identidad.PALETA_DATOS),
        annotations=[
            {
                "text": fuente,
                "showarrow": False,
                "xref": "paper",
                "yref": "paper",
                "x": 0,
                "y": -0.2,
                "xanchor": "left",
                "font": {"size": 10, "color": identidad.GRIS_SUAVE},
            }
        ],
        template="none",
    )
    figura_dict = json.loads(figura.to_json())
    figura_dict["layout"].pop("template", None)
    return figura_dict


def _lista(valores) -> list:
    return [None if pd.isna(v) else (float(v) if isinstance(v, (int, float, np.number)) else v) for v in valores]


def agrupar_otros(datos: pd.DataFrame, categoria: str, metrica: str, max_sectores: int = 6) -> pd.DataFrame:
    """Deja las `max_sectores - 1` categorías mayores y suma el resto en «Otros» (Tabla 21, Figura 13).

    Salida: a lo sumo `max_sectores` filas, ordenadas de mayor a menor con «Otros» al final. El total se
    conserva. Si hay `max_sectores` categorías o menos, solo ordena. En empate, orden alfabético.
    """
    ordenado = datos.sort_values([metrica, categoria], ascending=[False, True], kind="mergesort")
    ordenado = ordenado.reset_index(drop=True)
    if len(ordenado) <= max_sectores:
        return ordenado
    mayores = ordenado.head(max_sectores - 1)
    resto = ordenado.iloc[max_sectores - 1 :]
    otros = pd.DataFrame({categoria: [ETIQUETA_OTROS], metrica: [resto[metrica].sum()]})
    return pd.concat([mayores[[categoria, metrica]], otros], ignore_index=True)


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
    ejes = _Ejes(datos, spec, etiquetas)
    tipo = TipoGrafico(grafico.tipo)
    if not ejes.metricas:
        raise ValueError("los datos no traen ninguna métrica de la spec para dibujar")
    dibujar = {
        TipoGrafico.BARRAS: _barras,
        TipoGrafico.LINEAS: _lineas,
        TipoGrafico.TORTA: _torta,
        TipoGrafico.DISPERSION: _dispersion,
        TipoGrafico.MAPA_CALOR: _mapa_calor,
        TipoGrafico.HISTOGRAMA: _histograma,
    }[tipo]
    with plt.rc_context(_ESTILO):
        figura, ejes_mpl = plt.subplots(figsize=TAMANO)
        plotly_fig, eje_x, eje_y, notas = dibujar(ejes, ejes_mpl, grafico, analisis)
        ejes_mpl.set_title(titulo, color=identidad.GRIS_TEXTO, loc="left")
        if eje_x:
            ejes_mpl.set_xlabel(eje_x)
        if eje_y:
            ejes_mpl.set_ylabel(eje_y)
        figura.text(
            0.0,
            -0.02,
            fuente,
            fontsize=8,
            color=identidad.GRIS_SUAVE,
            ha="left",
            va="top",
            transform=figura.transFigure,
        )
        png = _png(figura)
    return Grafico(
        tipo=tipo.value,
        png=png,
        plotly=_plotly(plotly_fig, titulo, eje_x, eje_y, fuente),
        titulo=titulo,
        eje_x=eje_x,
        eje_y=eje_y,
        fuente=fuente,
        notas=tuple(notas),
    )


# --- Un dibujante por tipo: devuelve (figura plotly, eje x, eje y, notas) ----------------------------------------


def _barras(ejes: _Ejes, ax, grafico: GraficoResuelto, analisis):
    d = ejes.datos
    metrica = ejes.metricas[0]
    dims = ejes.dimensiones
    figura = go.Figure()
    if not dims:  # sin dimensión: una barra por métrica
        nombres = [ejes.nombre(m) for m in ejes.metricas]
        valores = [float(d[m].sum()) for m in ejes.metricas]
        ax.bar(nombres, valores, color=identidad.AZUL_DATOS)
        figura.add_bar(x=nombres, y=valores, marker_color=identidad.AZUL_DATOS)
        return figura, "Indicador", "Valor", []
    x = dims[0]
    categorias_x = list(dict.fromkeys(d[x])) if x == "__tiempo" else sorted(d[x].unique())
    if len(dims) == 1:
        serie = _agregar(d, [x], metrica).reindex(categorias_x)
        ax.bar(categorias_x, serie.to_numpy(dtype=float), color=identidad.AZUL_DATOS)
        figura.add_bar(x=categorias_x, y=_lista(serie), marker_color=identidad.AZUL_DATOS, name=ejes.nombre(metrica))
    else:
        leyenda = dims[1]
        tabla = _agregar(d, [x, leyenda], metrica).unstack(leyenda).fillna(0)
        tabla = tabla.reindex(categorias_x)
        tabla = tabla[sorted(tabla.columns)]
        ancho = 0.8 / max(len(tabla.columns), 1)
        posiciones = np.arange(len(tabla.index))
        for i, columna in enumerate(tabla.columns):
            color = identidad.PALETA_DATOS[i % len(identidad.PALETA_DATOS)]
            ax.bar(
                posiciones + i * ancho - 0.4 + ancho / 2,
                tabla[columna].to_numpy(dtype=float),
                ancho,
                label=str(columna),
                color=color,
            )
            figura.add_bar(x=list(tabla.index), y=_lista(tabla[columna]), name=str(columna), marker_color=color)
        ax.set_xticks(posiciones, list(tabla.index))
        ax.legend(title=ejes.nombre(leyenda), frameon=False)
        figura.update_layout(barmode="group", legend_title_text=ejes.nombre(leyenda))
    if len(categorias_x) > 6:
        ax.tick_params(axis="x", labelrotation=45)
    return figura, ejes.nombre(x), ejes.nombre(metrica), []


def _lineas(ejes: _Ejes, ax, grafico: GraficoResuelto, analisis):
    d = ejes.datos
    metrica = ejes.metricas[0]
    x = ejes.tiempo() or (ejes.dimensiones[0] if ejes.dimensiones else None)
    if x is None:
        raise ValueError("el gráfico de líneas necesita una dimensión de tiempo o de categoría")
    figura = go.Figure()
    categorias_x = list(dict.fromkeys(d[x]))
    otras = [c for c in ejes.dimensiones if c != x]
    notas: list[str] = []
    if otras:
        leyenda = otras[0]
        for i, (valor, grupo) in enumerate(d.groupby(leyenda, sort=True)):
            serie = _agregar(grupo, [x], metrica).reindex(categorias_x)
            color = identidad.PALETA_DATOS[i % len(identidad.PALETA_DATOS)]
            ax.plot(categorias_x, serie.to_numpy(dtype=float), marker="o", label=str(valor), color=color)
            figura.add_scatter(x=categorias_x, y=_lista(serie), mode="lines+markers", name=str(valor))
        ax.legend(title=ejes.nombre(leyenda), frameon=False)
    else:
        serie = _agregar(d, [x], metrica).reindex(categorias_x)
        ax.plot(
            categorias_x,
            serie.to_numpy(dtype=float),
            marker="o",
            color=identidad.AZUL_DATOS,
            label=ejes.nombre(metrica),
        )
        figura.add_scatter(
            x=categorias_x,
            y=_lista(serie),
            mode="lines+markers",
            name=ejes.nombre(metrica),
            line={"color": identidad.AZUL_DATOS},
        )
        if isinstance(analisis, ResultadoPronostico) and x == "__tiempo":
            futuros = _periodos_futuros(d, ejes.granularidad, len(analisis.valores))
            puente_x = [categorias_x[-1], *futuros]
            puente_y = [float(serie.iloc[-1]), *analisis.valores]
            ax.plot(puente_x, puente_y, linestyle="--", color=identidad.AZUL_DATOS, label="Pronóstico")
            ax.fill_between(
                futuros,
                analisis.inferior,
                analisis.superior,
                color=identidad.PALETA_DATOS[1],
                alpha=0.25,
                label=f"Intervalo {analisis.nivel_confianza:.0%}",
            )
            figura.add_scatter(x=puente_x, y=puente_y, mode="lines", name="Pronóstico", line={"dash": "dash"})
            figura.add_scatter(
                x=futuros + futuros[::-1],
                y=list(analisis.superior) + list(analisis.inferior)[::-1],
                fill="toself",
                mode="none",
                name=f"Intervalo {analisis.nivel_confianza:.0%}",
                opacity=0.3,
            )
            ax.legend(frameon=False)
            notas.append(
                f"El tramo punteado es un pronóstico ({analisis.tecnica}) con intervalo del "
                f"{analisis.nivel_confianza:.0%}."
            )
    if len(categorias_x) > 8:
        paso = max(1, len(categorias_x) // 8)
        ax.set_xticks(range(0, len(ax.get_xticks()), paso))
        ax.tick_params(axis="x", labelrotation=45)
    return figura, ejes.nombre(x), ejes.nombre(metrica), notas


def _periodos_futuros(d: pd.DataFrame, granularidad: Granularidad, horizonte: int) -> list[str]:
    columna = {
        Granularidad.MES: "tiempo_mes",
        Granularidad.TRIMESTRE: "tiempo_trimestre",
        Granularidad.SEMESTRE: "tiempo_semestre",
    }.get(granularidad)
    ultima = d.iloc[-1]
    ultimo = _periodo(int(ultima["tiempo_anio"]), int(ultima[columna]) if columna else None, granularidad)
    paso = 1
    return [_etiqueta_de_periodo(ultimo + paso * h, granularidad) for h in range(1, horizonte + 1)]


def _torta(ejes: _Ejes, ax, grafico: GraficoResuelto, analisis):
    metrica = ejes.metricas[0]
    categoria = ejes.dimensiones[0] if ejes.dimensiones else None
    if categoria is None:
        raise ValueError("la torta necesita una dimensión de categoría")
    base = _agregar(ejes.datos, [categoria], metrica).reset_index().sort_values(categoria, kind="mergesort")
    maximo = grafico.max_sectores or MAX_SECTORES_TORTA
    agrupado = agrupar_otros(base, categoria, metrica, max_sectores=maximo)
    notas = []
    if len(base) > maximo:
        agrupadas = len(base) - (maximo - 1)
        notas.append(f"Se agruparon {agrupadas} categorías menores en «{ETIQUETA_OTROS}».")
    colores = [identidad.PALETA_DATOS[i % len(identidad.PALETA_DATOS)] for i in range(len(agrupado))]
    if agrupado[categoria].iloc[-1] == ETIQUETA_OTROS:
        colores[-1] = identidad.GRIS_SUAVE
    ax.pie(
        agrupado[metrica].to_numpy(dtype=float),
        labels=agrupado[categoria].tolist(),
        colors=colores,
        autopct="%1.1f %%",
        startangle=90,
        counterclock=False,
        wedgeprops={"linewidth": 1, "edgecolor": "white"},
    )
    ax.axis("equal")
    figura = go.Figure(
        go.Pie(
            labels=agrupado[categoria].tolist(),
            values=_lista(agrupado[metrica]),
            marker={"colors": colores},
            sort=False,
            direction="clockwise",
        )
    )
    return figura, "", "", notas


def _dispersion(ejes: _Ejes, ax, grafico: GraficoResuelto, analisis):
    d = ejes.datos
    if len(ejes.metricas) < 2:
        raise ValueError("la dispersión necesita dos métricas")
    mx, my = ejes.metricas[0], ejes.metricas[1]
    figura = go.Figure()
    notas: list[str] = []
    if isinstance(analisis, ResultadoSegmentacion) and len(analisis.etiquetas) == len(d):
        grupos = analisis.etiquetas.to_numpy()
        for g in sorted(set(grupos.tolist())):
            mascara = grupos == g
            color = identidad.PALETA_DATOS[int(g) % len(identidad.PALETA_DATOS)]
            nombre = f"Grupo {int(g) + 1}"
            ax.scatter(d.loc[mascara, mx], d.loc[mascara, my], s=28, color=color, label=nombre, alpha=0.85)
            figura.add_scatter(
                x=_lista(d.loc[mascara, mx]),
                y=_lista(d.loc[mascara, my]),
                mode="markers",
                name=nombre,
                marker={"color": color},
            )
        ax.legend(frameon=False)
        notas.append(f"Color por grupo de k-medias (k = {analisis.k}).")
    else:
        ax.scatter(d[mx], d[my], s=28, color=identidad.AZUL_DATOS, alpha=0.8)
        figura.add_scatter(
            x=_lista(d[mx]),
            y=_lista(d[my]),
            mode="markers",
            marker={"color": identidad.AZUL_DATOS},
            name=ejes.nombre(my),
        )
    return figura, ejes.nombre(mx), ejes.nombre(my), notas


def _mapa_calor(ejes: _Ejes, ax, grafico: GraficoResuelto, analisis):
    d = ejes.datos
    metrica = ejes.metricas[0]
    if len(ejes.dimensiones) < 2:
        raise ValueError("el mapa de calor necesita dos dimensiones")
    filas, columnas = ejes.dimensiones[0], ejes.dimensiones[1]
    orden_columnas = list(dict.fromkeys(d[columnas])) if columnas == "__tiempo" else sorted(d[columnas].unique())
    orden_filas = list(dict.fromkeys(d[filas])) if filas == "__tiempo" else sorted(d[filas].unique())
    tabla = _agregar(d, [filas, columnas], metrica).unstack(columnas)
    tabla = tabla.reindex(index=orden_filas, columns=orden_columnas)
    valores = tabla.to_numpy(dtype=float)
    imagen = ax.imshow(valores, cmap=identidad.ESCALA_CALOR, aspect="auto")
    ax.set_xticks(range(len(orden_columnas)), orden_columnas)
    ax.set_yticks(range(len(orden_filas)), orden_filas)
    umbral = np.nanmean(valores) if np.isfinite(valores).any() else 0
    for i in range(valores.shape[0]):
        for j in range(valores.shape[1]):
            if np.isfinite(valores[i, j]):
                ax.text(
                    j,
                    i,
                    f"{valores[i, j]:.1f}",
                    ha="center",
                    va="center",
                    fontsize=8,
                    color="white" if valores[i, j] > umbral else identidad.GRIS_TEXTO,
                )
    ax.figure.colorbar(imagen, ax=ax, label=ejes.nombre(metrica))
    ax.spines[:].set_visible(False)
    figura = go.Figure(
        go.Heatmap(
            z=[_lista(fila) for fila in valores],
            x=orden_columnas,
            y=orden_filas,
            colorscale=identidad.ESCALA_CALOR,
            texttemplate="%{z:.1f}",
            colorbar={"title": {"text": ejes.nombre(metrica)}},
        )
    )
    return figura, ejes.nombre(columnas), ejes.nombre(filas), [f"Color: {ejes.nombre(metrica)}."]


def _histograma(ejes: _Ejes, ax, grafico: GraficoResuelto, analisis):
    metrica = ejes.metricas[0]
    x = pd.to_numeric(ejes.datos[metrica], errors="coerce").dropna().to_numpy(dtype=float)
    if x.size == 0:
        raise ValueError("el histograma no tiene valores")
    bordes = np.histogram_bin_edges(x, bins="fd")
    if len(bordes) < 3:  # RIC 0 o muy pocos datos: Freedman-Diaconis no separa clases
        bordes = np.histogram_bin_edges(x, bins="sturges")
    conteos, bordes = np.histogram(x, bins=bordes)
    ax.hist(x, bins=bordes, color=identidad.AZUL_DATOS, edgecolor="white")
    notas = [f"Clases por la regla de Freedman-Diaconis ({len(conteos)} clases, n = {x.size})."]
    figura = go.Figure(
        go.Bar(
            x=_lista((bordes[:-1] + bordes[1:]) / 2),
            y=[int(c) for c in conteos],
            width=_lista(np.diff(bordes)),
            marker_color=identidad.AZUL_DATOS,
            name=ejes.nombre(metrica),
        )
    )
    if isinstance(analisis, ResultadoAtipicos):
        for limite in (analisis.limite_inferior, analisis.limite_superior):
            ax.axvline(limite, color=identidad.GRIS_TEXTO, linestyle="--", linewidth=1)
            figura.add_vline(x=float(limite), line_dash="dash", line_color=identidad.GRIS_TEXTO)
        notas.append(
            f"Líneas punteadas: límites de atípicos ({analisis.metodo}, k = {analisis.k:g}); "
            f"{analisis.cantidad} valor(es) fuera."
        )
    return figura, ejes.nombre(metrica), "Frecuencia", notas
