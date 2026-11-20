"""Despacho del análisis: de los datos revisados a las secciones del contrato (pasos 9 y 10 de la Figura 11).

Recibe el resultado del compilador ya pasado por `revisar_datos` y llama a la función del motor o de ML que
pide `spec.analisis.metodo`. Devuelve:
  - `secciones`: `SeccionCalculada` con TODAS las cifras que el texto puede necesitar (la IA no calcula nada,
    ni una resta): valores por grupo, totales, máximos, variaciones, estadísticos con valor p y n.
  - `analisis`: el objeto que el gráfico necesita (pronóstico, segmentación o atípicos), o None.
  - `extra`: parámetros del análisis que el texto puede citar (alfa, nivel de confianza, k, horizonte); van al
    validador de cifras, no al contrato (`docs/interfaz_capa_ia.md`, punto 10).
Reglas de privacidad: los grupos por una dimensión con `viaja_a_ia = False` (empresa, macroproyecto) no se
publican en el contrato; de una segmentación solo viajan k, la silueta, los tamaños y los centroides.
Pruebas: `tests/motor/test_analisis.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ciumb_analitica.ml import atipicos as ml_atipicos
from ciumb_analitica.ml import pronostico as ml_pronostico
from ciumb_analitica.ml import segmentacion as ml_segmentacion
from ciumb_analitica.motor import descriptiva, inferencia, series
from ciumb_analitica.motor.resultado import (
    MuestraInsuficiente,
    ResultadoAtipicos,
    ResultadoPronostico,
    ResultadoPrueba,
    ResultadoSegmentacion,
    SeccionCalculada,
)
from ciumb_analitica.semantica.modelos import Aditividad, CapaSemantica
from ciumb_analitica.spec.convenciones import (
    CATEGORIAS_BINARIA,
    DIMENSION_TIEMPO,
    SUFIJO_DEN,
    SUFIJO_NUM,
    columnas_de_dimension,
)
from ciumb_analitica.spec.modelos import Granularidad
from ciumb_analitica.spec.resultado import Nivel, SpecResuelta

MAX_INDICADORES = 200
"""Tope de indicadores por sección del contrato (`contrato.modelos.Seccion`)."""

MIN_UNIDADES_CENTROIDE = 5
"""Un grupo de la segmentación con menos unidades no publica su centroide (sería la actividad de esas unidades;
misma regla que la supresión de grupos con menos de cinco personas, invariante 4)."""

MAX_GRUPOS_DETALLE = 60
"""Grupos que se detallan en la sección de datos; si hay más, se publican los mayores y se advierte."""

NOMBRE_METODO = {
    "frecuencias": "frecuencias por grupo",
    "descriptiva": "estadística descriptiva (media, mediana, desviación estándar muestral y cuartiles)",
    "serie": "serie de tiempo",
    "variacion": "variación frente al periodo anterior",
    "variacion_interanual": "variación frente al mismo periodo del año anterior",
    "pearson": "correlación de Pearson",
    "spearman": "correlación de Spearman",
    "chi_cuadrado": "prueba chi-cuadrado de independencia, sin corrección de Yates",
    "t_student": "t de Student para dos muestras independientes (Welch)",
    "mann_whitney": "U de Mann-Whitney",
    "atipicos": "detección de valores atípicos",
    "pronostico": "pronóstico",
    "segmentacion": "segmentación k-medias con variables estandarizadas",
}


class AnalisisNoAplicable(ValueError):  # noqa: N818 - nombre de dominio en español
    """Los datos reales no permiten el método pedido (p. ej. la dimensión no tiene dos grupos para la t).
    La orquestación lo devuelve como spec corregible: hay que repreguntar al usuario."""


@dataclass
class Calculo:
    secciones: list[SeccionCalculada]
    analisis: object | None = None
    extra: list[float] = field(default_factory=list)
    tablas: dict[str, pd.DataFrame] = field(default_factory=dict)


# --- Utilidades ----------------------------------------------------------------------------------------------------


def _numero(valor) -> float | int | None:
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return None
    if isinstance(valor, bool | np.bool_):
        return int(valor)
    if isinstance(valor, int | np.integer):
        return int(valor)
    valor = float(valor)
    if not np.isfinite(valor):
        return None
    return int(valor) if valor.is_integer() and abs(valor) < 2**53 else valor


def _texto(valor) -> str:
    if valor is None or (isinstance(valor, float) and np.isnan(valor)) or valor is pd.NA:
        return "Sin dato"
    return str(valor)[:300] or "Sin dato"


def _ind(id_: str, valor, **kw) -> dict:
    kw = {k: v for k, v in kw.items() if v is not None}
    if "grupo" in kw:
        kw["grupo"] = {k: _texto(v) for k, v in kw["grupo"].items()}
    return {"id": id_, "valor": _numero(valor), **kw}


def _es_razon(datos: pd.DataFrame, metrica: str) -> bool:
    return f"{metrica}{SUFIJO_NUM}" in datos.columns and f"{metrica}{SUFIJO_DEN}" in datos.columns


def _valor_conjunto(datos: pd.DataFrame, metrica: str) -> float | None:
    """Total del conjunto: una razón se recalcula desde sus componentes; lo demás se suma."""
    if _es_razon(datos, metrica):
        return descriptiva.razon_total(datos, metrica)
    return float(pd.to_numeric(datos[metrica], errors="coerce").sum())


def _agrupar(datos: pd.DataFrame, columnas: list[str], metrica: str) -> pd.DataFrame:
    """Valor de `metrica` por combinación de `columnas` (razones desde num/den; aditivas sumadas)."""
    if not columnas:
        return pd.DataFrame({metrica: [_valor_conjunto(datos, metrica)]})
    if _es_razon(datos, metrica):
        num, den = f"{metrica}{SUFIJO_NUM}", f"{metrica}{SUFIJO_DEN}"
        partes = datos.groupby(columnas, sort=True, dropna=False)[[num, den]].sum().reset_index()
        partes[metrica] = 100.0 * partes[num] / partes[den].where(partes[den] != 0)
        return partes[[*columnas, metrica]]
    return datos.groupby(columnas, sort=True, dropna=False)[metrica].sum().reset_index()


def _etiqueta_tiempo(fila: pd.Series, granularidad: Granularidad) -> str:
    anio = int(fila["tiempo_anio"])
    if granularidad is Granularidad.MES:
        return f"{anio}-{int(fila['tiempo_mes']):02d}"
    if granularidad is Granularidad.TRIMESTRE:
        return f"{anio}-T{int(fila['tiempo_trimestre'])}"
    if granularidad is Granularidad.SEMESTRE:
        return f"{anio}-S{int(fila['tiempo_semestre'])}"
    return str(anio)


def _etiqueta_periodo(periodo: pd.Period, granularidad: Granularidad) -> str:
    if granularidad is Granularidad.MES:
        return f"{periodo.year}-{periodo.month:02d}"
    if granularidad is Granularidad.TRIMESTRE:
        return f"{periodo.year}-T{periodo.quarter}"
    if granularidad is Granularidad.SEMESTRE:
        return f"{periodo.year}-S{(periodo.quarter + 1) // 2}"
    return str(periodo.year)


def _ubicacion(granularidad: Granularidad | None, etiqueta: str) -> dict:
    """Un periodo en un indicador: `mes` (AAAA-MM, como la Figura 12) o `grupo` {"tiempo": etiqueta}."""
    if granularidad is Granularidad.MES:
        return {"mes": etiqueta}
    return {"grupo": {DIMENSION_TIEMPO: etiqueta}}


class _Contexto:
    def __init__(self, spec: SpecResuelta, capa: CapaSemantica, datos: pd.DataFrame):
        self.spec = spec
        self.capa = capa
        self.datos = datos
        self.granularidad = spec.granularidad()
        self.metricas = [m.id for m in spec.metricas if m.id in datos.columns]
        self.dim_columnas: list[str] = []  # columnas de dimensiones no temporales presentes
        self.columnas_tiempo: list[str] = []
        self.ocultas: list[str] = []  # dimensiones que no viajan a la IA
        for d in spec.dimensiones:
            columnas = [c for c in columnas_de_dimension(d) if c in datos.columns]
            if d.id == DIMENSION_TIEMPO:
                self.columnas_tiempo = columnas
            elif columnas:
                dimension = capa.dimensiones.get(d.id)
                if dimension is not None and (not dimension.viaja_a_ia or dimension.identifica_persona):
                    self.ocultas.append(d.id)
                else:
                    self.dim_columnas.append(columnas[0])

    def aditiva(self, metrica: str) -> bool:
        """True si la métrica se puede sumar entre periodos. Una semiaditiva (instantánea: proyectos, convenios)
        no se suma entre fechas de corte (D-18); una razón se recalcula desde sus componentes."""
        m = self.capa.metricas.get(metrica)
        return m is None or m.aditividad is Aditividad.ADITIVA

    def total(self, datos: pd.DataFrame, metrica: str) -> float | None:
        """Total del conjunto. Con tiempo, una semiaditiva vale lo del último periodo (no la suma de los cortes)."""
        if not _es_razon(datos, metrica) and not self.aditiva(metrica) and self.columnas_tiempo and len(datos):
            ultimo = datos[self.columnas_tiempo].apply(tuple, axis=1).max()
            datos = datos[datos[self.columnas_tiempo].apply(tuple, axis=1) == ultimo]
        return _valor_conjunto(datos, metrica)

    def unidad(self, metrica: str) -> str | None:
        m = self.capa.metricas.get(metrica)
        return m.unidad if m else None

    def nombre(self, codigo: str) -> str:
        if codigo in self.capa.metricas:
            return self.capa.metricas[codigo].nombre
        if codigo in self.capa.dimensiones:
            return self.capa.dimensiones[codigo].nombre
        return codigo.replace("_", " ")

    def advertencia_ocultas(self) -> list[str]:
        if not self.ocultas:
            return []
        nombres = ", ".join(self.nombre(o).lower() for o in self.ocultas)
        return [f"El detalle por {nombres} se muestra solo en el informe; aquí se publican los totales."]

    def con_tiempo(self) -> pd.DataFrame:
        """Datos con la columna `tiempo` (etiqueta legible del periodo)."""
        if not self.columnas_tiempo or self.granularidad is None:
            return self.datos
        datos = self.datos.sort_values(self.columnas_tiempo, kind="mergesort").copy()
        datos[DIMENSION_TIEMPO] = [_etiqueta_tiempo(f, self.granularidad) for _, f in datos.iterrows()]
        return datos


def _seccion(id_: str, indicadores: list[dict], metodo: str, advertencias: list[str] | None = None) -> SeccionCalculada:
    advertencias = list(advertencias or [])
    indicadores = [i for i in indicadores if i.get("valor") is not None]  # p. ej. una razón con denominador 0
    if len(indicadores) > MAX_INDICADORES:
        indicadores = indicadores[:MAX_INDICADORES]
        advertencias.append(f"La sección se limitó a los primeros {MAX_INDICADORES} indicadores.")
    if not indicadores:
        indicadores = [_ind("sin_datos", 0)]
        advertencias.append("No hay datos para el periodo y los filtros pedidos.")
    return SeccionCalculada(id=id_, indicadores=indicadores, metodo=metodo, advertencias=advertencias)


def _avisos(resultado) -> list[str]:
    return [a.mensaje for a in getattr(resultado, "advertencias", ())]


# --- Sección de datos (valores por grupo y totales) -----------------------------------------------------------------


def _seccion_datos(ctx: _Contexto, metodo: str, *, relativas: bool = False) -> SeccionCalculada:
    """Valores de cada métrica por grupo, con el total del conjunto y la participación si se pide."""
    datos = ctx.con_tiempo()
    columnas = list(ctx.dim_columnas)
    if ctx.columnas_tiempo and ctx.granularidad is not None:
        columnas.append(DIMENSION_TIEMPO)
    indicadores: list[dict] = []
    advertencias = ctx.advertencia_ocultas()
    for m in ctx.metricas:
        unidad = ctx.unidad(m)
        total = ctx.total(datos, m)
        indicadores.append(_ind(f"{m}_total", total, unidad=unidad))
        if not columnas:
            continue
        grupos = _agrupar(datos, columnas, m).dropna(subset=[m])
        grupos = grupos.sort_values([m, *columnas], ascending=[False, *[True] * len(columnas)], kind="mergesort")
        if len(grupos) > MAX_GRUPOS_DETALLE:
            advertencias.append(
                f"Se publican los {MAX_GRUPOS_DETALLE} grupos con mayor {ctx.nombre(m).lower()} de {len(grupos)}."
            )
            grupos = grupos.head(MAX_GRUPOS_DETALLE)
        # La participación solo tiene sentido si las celdas suman el total: no para razones ni para cortes.
        aditiva = not _es_razon(datos, m) and (ctx.aditiva(m) or DIMENSION_TIEMPO not in columnas)
        for _, fila in grupos.iterrows():
            grupo = {c: str(fila[c]) for c in columnas if c != DIMENSION_TIEMPO}
            ubicacion = {}
            if DIMENSION_TIEMPO in columnas:
                ubicacion = _ubicacion(ctx.granularidad, fila[DIMENSION_TIEMPO])
                if "grupo" in ubicacion:
                    grupo |= ubicacion.pop("grupo")
            indicadores.append(_ind(m, fila[m], unidad=unidad, grupo=grupo or None, **ubicacion))
            if relativas and aditiva and total:
                indicadores.append(
                    _ind(f"{m}_participacion", fila[m] / total, unidad="proporcion", grupo=grupo or None, **ubicacion)
                )
        if len(grupos) > 1:
            mayor = grupos.iloc[0]
            grupo = {c: str(mayor[c]) for c in columnas if c != DIMENSION_TIEMPO}
            ubicacion = _ubicacion(ctx.granularidad, mayor[DIMENSION_TIEMPO]) if DIMENSION_TIEMPO in columnas else {}
            if "grupo" in ubicacion:
                grupo |= ubicacion.pop("grupo")
            indicadores.append(_ind(f"{m}_maximo", mayor[m], unidad=unidad, grupo=grupo or None, **ubicacion))
            indicadores.append(_ind(f"{m}_n_grupos", len(grupos)))
    return _seccion("datos", indicadores, metodo, advertencias)


# --- Series --------------------------------------------------------------------------------------------------------


def _serie(ctx: _Contexto, metrica: str) -> tuple[pd.Series, pd.Series | None, pd.Series | None]:
    """Serie de la métrica sumando las demás dimensiones. Para una razón devuelve también num y den."""
    if not ctx.columnas_tiempo or ctx.granularidad is None:
        raise AnalisisNoAplicable("el método necesita la dimensión tiempo")
    datos = ctx.datos
    if _es_razon(datos, metrica):
        num = series.a_serie(_sumar_tiempo(ctx, f"{metrica}{SUFIJO_NUM}"), f"{metrica}{SUFIJO_NUM}", ctx.granularidad)
        den = series.a_serie(_sumar_tiempo(ctx, f"{metrica}{SUFIJO_DEN}"), f"{metrica}{SUFIJO_DEN}", ctx.granularidad)
        return (100.0 * num / den.where(den != 0)).rename(metrica), num, den
    # Un periodo sin fila vale 0 solo si la métrica es aditiva; un corte que falta queda vacío.
    serie = series.a_serie(_sumar_tiempo(ctx, metrica), metrica, ctx.granularidad, completar=ctx.aditiva(metrica))
    return serie, None, None


def _sumar_tiempo(ctx: _Contexto, columna: str) -> pd.DataFrame:
    return ctx.datos.groupby(ctx.columnas_tiempo, sort=True)[columna].sum().reset_index()


def _indicadores_serie(ctx: _Contexto, metrica: str, serie: pd.Series) -> list[dict]:
    unidad = ctx.unidad(metrica)
    salida = []
    for periodo, valor in serie.items():
        if pd.isna(valor):
            continue
        salida.append(
            _ind(
                metrica,
                valor,
                unidad=unidad,
                **_ubicacion(ctx.granularidad, _etiqueta_periodo(periodo, ctx.granularidad)),
            )
        )
    validos = serie.dropna()
    if len(validos):
        for nombre, periodo in (("maximo", validos.idxmax()), ("minimo", validos.idxmin())):
            salida.append(
                _ind(f"{metrica}_{nombre}", validos.loc[periodo], unidad=unidad,
                     **_ubicacion(ctx.granularidad, _etiqueta_periodo(periodo, ctx.granularidad)))
            )  # fmt: skip
        salida.append(_ind(f"{metrica}_n_periodos", len(validos)))
    return salida


def _calc_serie(ctx: _Contexto) -> Calculo:
    analisis = ctx.spec.analisis
    secciones = []
    for m in ctx.metricas:
        serie, _, _ = _serie(ctx, m)
        indicadores = _indicadores_serie(ctx, m, serie)
        if not _es_razon(ctx.datos, m) and not ctx.aditiva(m) and len(serie.dropna()):
            ultimo = serie.dropna().index[-1]
            indicadores.insert(
                0,
                _ind(
                    f"{m}_ultimo_periodo",
                    serie.loc[ultimo],
                    unidad=ctx.unidad(m),
                    **_ubicacion(ctx.granularidad, _etiqueta_periodo(ultimo, ctx.granularidad)),
                ),
            )
        elif not _es_razon(ctx.datos, m):
            indicadores.insert(0, _ind(f"{m}_total", serie.sum(), unidad=ctx.unidad(m)))
            if getattr(analisis, "acumulado", False):
                acumulado = series.acumulado(serie)
                ultimo = acumulado.index[-1]
                indicadores.append(
                    _ind(f"{m}_acumulado_anio", acumulado.iloc[-1], unidad=ctx.unidad(m),
                         **_ubicacion(ctx.granularidad, _etiqueta_periodo(ultimo, ctx.granularidad)))
                )  # fmt: skip
        secciones.append(_seccion(m, indicadores, NOMBRE_METODO["serie"], ctx.advertencia_ocultas()))
    return Calculo(secciones)


def _calc_variacion(ctx: _Contexto) -> Calculo:
    metodo = ctx.spec.analisis.metodo
    secciones = []
    for m in ctx.metricas:
        serie, num, den = _serie(ctx, m)
        unidad = ctx.unidad(m)
        indicadores: list[dict] = []
        if metodo == "variacion_interanual":
            if num is not None:  # razón: el tramo se recalcula desde sus componentes
                rn, rd = series.variacion_interanual(num), series.variacion_interanual(den)
                actual = 100.0 * rn["actual"] / rd["actual"] if rd["actual"] else None
                anterior = 100.0 * rn["anterior"] / rd["anterior"] if rd["anterior"] else None
                variacion = 100.0 * (actual - anterior) / abs(anterior) if actual is not None and anterior else None
                n_periodos = rn["n_periodos"]
                tramo = serie[serie.index.year == serie.index.max().year].dropna()
                periodo_max = tramo.idxmax() if len(tramo) else None
                valor_max = tramo.max() if len(tramo) else None
            elif not ctx.aditiva(m):  # instantánea: el último corte frente al mismo corte del año anterior
                validos = serie.dropna()
                ultimo = validos.index[-1]
                previo = ultimo - series.periodos_por_anio(serie.index)
                actual = float(validos.iloc[-1])
                anterior = float(serie[previo]) if previo in serie.index and pd.notna(serie[previo]) else None
                variacion = 100.0 * (actual - anterior) / abs(anterior) if anterior else None
                n_periodos = 1
                tramo = validos[validos.index.year == ultimo.year]
                periodo_max, valor_max = tramo.idxmax(), tramo.max()
            else:
                r = series.variacion_interanual(serie)
                actual, anterior, variacion = r["actual"], r["anterior"], r["variacion_pct"]
                n_periodos, periodo_max, valor_max = r["n_periodos"], r["periodo_maximo"], r["valor_maximo"]
            ultimo_anio = int(serie.index.max().year)
            if num is None and not ctx.aditiva(m):
                descripcion = f"último corte de {ultimo_anio} frente al mismo corte de {ultimo_anio - 1}"
            else:
                descripcion = (
                    f"tramo de {n_periodos} periodos de {ultimo_anio} frente al mismo tramo de {ultimo_anio - 1}"
                )
            indicadores.append(
                _ind(f"{m}_{ultimo_anio}", actual, anterior=_numero(anterior),
                     variacion_pct=_numero(variacion), unidad=unidad, metodo=descripcion)
            )  # fmt: skip
            if periodo_max is not None:
                indicadores.append(
                    _ind(f"{m}_periodo_mayor", valor_max, unidad=unidad,
                         **_ubicacion(ctx.granularidad, _etiqueta_periodo(periodo_max, ctx.granularidad)))
                )  # fmt: skip
        else:
            validos = serie.dropna()
            if len(validos) >= 2:
                ultimo, previo = validos.iloc[-1], validos.iloc[-2]
                variacion = None if previo == 0 else 100.0 * (ultimo - previo) / abs(previo)
                indicadores.append(
                    _ind(f"{m}_ultimo_periodo", ultimo, anterior=_numero(previo), variacion_pct=_numero(variacion),
                         unidad=unidad,
                         **_ubicacion(ctx.granularidad, _etiqueta_periodo(validos.index[-1], ctx.granularidad)))
                )  # fmt: skip
        indicadores += _indicadores_serie(ctx, m, serie)
        secciones.append(_seccion(m, indicadores, NOMBRE_METODO[metodo], ctx.advertencia_ocultas()))
    return Calculo(secciones)


# --- Descriptiva y atípicos ----------------------------------------------------------------------------------------


def _indicadores_resumen(ctx: _Contexto, metrica: str, valores: pd.Series, grupo: dict | None = None) -> list[dict]:
    r = descriptiva.resumen(valores)
    unidad = ctx.unidad(metrica)
    salida = [
        _ind(f"{metrica}_media", r.media, unidad=unidad, n=r.n, grupo=grupo),
        _ind(f"{metrica}_mediana", r.mediana, unidad=unidad, n=r.n, grupo=grupo),
    ]
    if grupo is None:
        salida += [
            _ind(f"{metrica}_minimo", r.minimo, unidad=unidad),
            _ind(f"{metrica}_maximo", r.maximo, unidad=unidad),
            _ind(f"{metrica}_q1", r.q1, unidad=unidad),
            _ind(f"{metrica}_q3", r.q3, unidad=unidad),
        ]
        if r.desviacion is not None:
            salida.append(_ind(f"{metrica}_desviacion", r.desviacion, unidad=unidad))
        if r.moda is not None:
            salida.append(_ind(f"{metrica}_moda", r.moda, unidad=unidad))
    return salida


def _indicadores_atipicos(ctx: _Contexto, metrica: str, resultado: ResultadoAtipicos) -> list[dict]:
    unidad = ctx.unidad(metrica)
    etiqueta = "k" if resultado.metodo == "RIC" else "umbral"
    return [
        _ind(f"{metrica}_atipicos", resultado.cantidad, n=resultado.n,
             metodo=f"{'rango intercuartílico de Tukey' if resultado.metodo == 'RIC' else 'puntaje Z'}, "
                    f"{etiqueta} = {resultado.k:g}"),
        _ind(f"{metrica}_atipicos_proporcion", resultado.cantidad / resultado.n if resultado.n else None,
             unidad="proporcion"),
        _ind(f"{metrica}_limite_inferior", resultado.limite_inferior, unidad=unidad),
        _ind(f"{metrica}_limite_superior", resultado.limite_superior, unidad=unidad),
    ]  # fmt: skip


def _calc_descriptiva(ctx: _Contexto) -> Calculo:
    analisis = ctx.spec.analisis
    if ctx.spec.nivel is not Nivel.REGISTRO:  # datos ya agregados por grupo: se describen como frecuencias
        return Calculo([_seccion_datos(ctx, NOMBRE_METODO["frecuencias"])])
    regla = getattr(analisis, "atipicos", None)
    secciones, extra, objeto = [], [], None
    for m in ctx.metricas:
        valores = pd.to_numeric(ctx.datos[m], errors="coerce")
        indicadores = _indicadores_resumen(ctx, m, valores)
        if _es_razon(ctx.datos, m):
            indicadores.append(
                _ind(f"{m}_conjunto", descriptiva.razon_total(ctx.datos, m), unidad=ctx.unidad(m),
                     metodo="razón de los totales (no es el promedio de las razones)")
            )  # fmt: skip
        for columna in ctx.dim_columnas:
            for etiqueta, grupo in ctx.datos.groupby(columna, sort=True):
                indicadores += _indicadores_resumen(ctx, m, grupo[m], {columna: str(etiqueta)})
        advertencias = ctx.advertencia_ocultas()
        if regla is not None:
            try:
                resultado = ml_atipicos.detectar(valores, metodo=regla.metodo, k=regla.k)
                indicadores += _indicadores_atipicos(ctx, m, resultado)
                extra.append(regla.k)
                objeto = objeto or resultado
            except MuestraInsuficiente as e:
                advertencias.append(f"No se calcularon atípicos: {e}.")
        secciones.append(_seccion(m, indicadores, NOMBRE_METODO["descriptiva"], advertencias))
    return Calculo(secciones, objeto, extra)


def _calc_atipicos(ctx: _Contexto) -> Calculo:
    analisis = ctx.spec.analisis
    secciones, objeto = [], None
    for m in ctx.metricas:
        valores = pd.to_numeric(ctx.datos[m], errors="coerce")
        try:
            resultado = ml_atipicos.detectar(valores, metodo=analisis.tecnica, k=analisis.k)
        except MuestraInsuficiente as e:
            raise AnalisisNoAplicable(str(e)) from e
        objeto = objeto or resultado
        indicadores = _indicadores_atipicos(ctx, m, resultado) + _indicadores_resumen(ctx, m, valores)[:2]
        secciones.append(_seccion(m, indicadores, NOMBRE_METODO["atipicos"], ctx.advertencia_ocultas()))
    return Calculo(secciones, objeto, [analisis.k])


# --- Pruebas -------------------------------------------------------------------------------------------------------


def _indicador_prueba(r: ResultadoPrueba, id_: str) -> dict:
    return _ind(id_, r.estadistico, valor_p=float(r.valor_p), n=r.n)


def _calc_correlacion(ctx: _Contexto) -> Calculo:
    analisis = ctx.spec.analisis
    x, y = analisis.variables
    r = inferencia.correlacion(ctx.datos[x], ctx.datos[y], metodo=analisis.metodo, alfa=analisis.alfa)
    id_ = "r_pearson" if analisis.metodo == "pearson" else "rho_spearman"
    indicadores = [
        _indicador_prueba(r, id_),
        _ind("significativa", int(r.significativo), metodo=f"1 si el valor p es menor que alfa = {analisis.alfa:g}"),
    ]
    for m in (x, y):
        indicadores += _indicadores_resumen(ctx, m, ctx.datos[m])[:2]
    metodo = f"{NOMBRE_METODO[analisis.metodo]}, bilateral, alfa = {analisis.alfa:g}"
    return Calculo([_seccion("relacion", indicadores, metodo, _avisos(r))], None, [analisis.alfa])


def _calc_dos_grupos(ctx: _Contexto) -> Calculo:
    analisis = ctx.spec.analisis
    metrica, dimension = analisis.variables
    columna = dimension  # una dimensión no temporal tiene una sola columna con su código
    try:
        a, b, (ea, eb) = inferencia.dos_grupos(ctx.datos, metrica, columna)
    except ValueError as e:
        raise AnalisisNoAplicable(str(e)) from e
    prueba = inferencia.t_student if analisis.metodo == "t_student" else inferencia.mann_whitney
    r = prueba(a, b, alfa=analisis.alfa)
    unidad = ctx.unidad(metrica)
    indicadores = [_indicador_prueba(r, "t" if analisis.metodo == "t_student" else "u")]
    if r.grados_libertad is not None:
        indicadores.append(_ind("grados_libertad", r.grados_libertad))
    indicadores.append(
        _ind("significativa", int(r.significativo), metodo=f"1 si el valor p es menor que alfa = {analisis.alfa:g}")
    )
    for etiqueta, valores in ((ea, a), (eb, b)):
        indicadores.append(
            _ind(f"{metrica}_media", valores.mean(), unidad=unidad, n=len(valores), grupo={columna: etiqueta})
        )
        indicadores.append(
            _ind(f"{metrica}_mediana", valores.median(), unidad=unidad, n=len(valores), grupo={columna: etiqueta})
        )
    metodo = f"{NOMBRE_METODO[analisis.metodo]}, bilateral, alfa = {analisis.alfa:g}"
    return Calculo([_seccion("comparacion", indicadores, metodo, _avisos(r))], None, [analisis.alfa])


def _calc_chi_cuadrado(ctx: _Contexto, prueba: pd.DataFrame | None) -> Calculo:
    analisis = ctx.spec.analisis
    if prueba is None:
        raise AnalisisNoAplicable("falta la consulta de la prueba chi-cuadrado")
    fila, columna = analisis.variables
    dim_columna = ctx.capa.dimensiones.get(columna)
    if dim_columna is not None and dim_columna.binaria_de_metrica:
        tabla = inferencia.tabla_contingencia_de_razon(
            prueba, fila, dim_columna.binaria_de_metrica, CATEGORIAS_BINARIA[columna]
        )
    else:
        conteo = next(c for c in prueba.columns if c not in (fila, columna) and not c.startswith("_"))
        tabla = inferencia.tabla_contingencia(prueba, fila, columna, conteo)
    try:
        r = inferencia.chi_cuadrado(tabla, alfa=analisis.alfa)
    except MuestraInsuficiente as e:
        raise AnalisisNoAplicable(str(e)) from e
    indicadores = [
        _indicador_prueba(r, "chi_cuadrado"),
        _ind("grados_libertad", r.grados_libertad),
        _ind("significativa", int(r.significativo), metodo=f"1 si el valor p es menor que alfa = {analisis.alfa:g}"),
    ]
    for etiqueta, conteos in tabla.iterrows():
        total = float(conteos.sum())
        for categoria, valor in conteos.items():
            indicadores.append(_ind("frecuencia", valor, grupo={fila: str(etiqueta), columna: str(categoria)}))
            if total:
                indicadores.append(
                    _ind("proporcion_fila", valor / total, unidad="proporcion",
                         grupo={fila: str(etiqueta), columna: str(categoria)})
                )  # fmt: skip
    metodo = f"{NOMBRE_METODO['chi_cuadrado']}, alfa = {analisis.alfa:g}"
    secciones = [_seccion("prueba", indicadores, metodo, _avisos(r))]
    if ctx.metricas:
        secciones.insert(0, _seccion_datos(ctx, NOMBRE_METODO["frecuencias"]))
    return Calculo(secciones, None, [analisis.alfa], {"Tabla de contingencia": tabla.reset_index()})


# --- Pronóstico y segmentación -------------------------------------------------------------------------------------


def _calc_pronostico(ctx: _Contexto, publicar: bool) -> Calculo:
    analisis = ctx.spec.analisis
    m = ctx.metricas[0]
    serie, _, _ = _serie(ctx, m)
    indicadores = _indicadores_serie(ctx, m, serie)
    advertencias = ctx.advertencia_ocultas()
    objeto = None
    extra = [analisis.horizonte, analisis.nivel_confianza, 100 * analisis.nivel_confianza]
    if publicar:
        try:
            r = ml_pronostico.pronosticar(
                serie.dropna(), analisis.horizonte, tecnica=analisis.tecnica, nivel_confianza=analisis.nivel_confianza
            )
        except MuestraInsuficiente as e:
            advertencias.append(f"El pronóstico no se publica: {e}.")
        else:
            objeto = r
            ultimo = serie.dropna().index[-1]
            for h, (v, lo, hi) in enumerate(zip(r.valores, r.inferior, r.superior, strict=True), start=1):
                etiqueta = _etiqueta_periodo(ultimo + h, ctx.granularidad)
                indicadores.append(
                    _ind(f"{m}_pronostico", v, ic_inferior=lo, ic_superior=hi, unidad=ctx.unidad(m),
                         **_ubicacion(ctx.granularidad, etiqueta))
                )  # fmt: skip
            indicadores += [
                _ind("mae_modelo", r.mae_modelo, metodo="error absoluto medio, validación de origen móvil a un paso"),
                _ind("mae_linea_base", r.mae_ingenuo, metodo="error absoluto medio del último valor observado"),
            ]
            advertencias += _avisos(r)
    tecnica = "Holt (suavizado exponencial con tendencia)" if analisis.tecnica == "holt" else "regresión lineal"
    metodo = f"{NOMBRE_METODO['pronostico']} con {tecnica}, intervalo del {analisis.nivel_confianza:.0%}"
    return Calculo([_seccion(m, indicadores, metodo, advertencias)], objeto, extra)


def _calc_segmentacion(ctx: _Contexto) -> Calculo:
    analisis = ctx.spec.analisis
    columnas = list(ctx.metricas)
    try:
        r = ml_segmentacion.segmentar(ctx.datos, columnas, k=analisis.k)
    except MuestraInsuficiente as e:
        raise AnalisisNoAplicable(str(e)) from e
    indicadores = [
        _ind("k", r.k, metodo="elegido por coeficiente de silueta" if analisis.k is None else "fijado en la solicitud"),
        _ind("silueta", r.silueta),
        _ind("unidades", int(sum(r.tamanos))),
    ]
    pequenos = 0
    for grupo, tamano in enumerate(r.tamanos):
        etiqueta = {"segmento": str(grupo + 1)}
        indicadores.append(_ind("tamano", tamano, grupo=etiqueta))
        if tamano < MIN_UNIDADES_CENTROIDE:  # el centroide de un grupo diminuto describe a unidades concretas
            pequenos += 1
            continue
        for m in columnas:
            indicadores.append(_ind(f"{m}_centroide", r.centroides.loc[grupo, m], unidad=ctx.unidad(m), grupo=etiqueta))
    metodo = NOMBRE_METODO["segmentacion"]
    advertencias = ["Solo se publican los tamaños y los centroides de los grupos; nunca qué unidad cae en cuál."]
    if pequenos:
        advertencias.append(
            f"{pequenos} grupo(s) con menos de {MIN_UNIDADES_CENTROIDE} unidades: "
            "se informa su tamaño, no su centroide."
        )
    extra = [] if analisis.k is None else [analisis.k]
    tabla = r.centroides.reset_index().assign(grupo=lambda t: t["grupo"] + 1)
    tabla.insert(1, "tamano", list(r.tamanos))
    return Calculo([_seccion("segmentos", indicadores, metodo, advertencias)], r, extra, {"Segmentos": tabla})


# --- Entrada -------------------------------------------------------------------------------------------------------


def calcular(
    spec: SpecResuelta,
    datos: pd.DataFrame,
    capa: CapaSemantica,
    *,
    prueba: pd.DataFrame | None = None,
    publicar_pronostico: bool = True,
) -> Calculo:
    """Calcula las secciones del contrato para una spec válida.

    Entradas: `datos` = `RevisionDatos.datos` de la consulta principal (o la unión de las principales en P8);
    `prueba` = la consulta `prueba` del plan (chi-cuadrado); `publicar_pronostico` = `RevisionDatos.
    publicar_pronostico`. Salida: `Calculo`. Lanza `AnalisisNoAplicable` si los datos no admiten el método.
    """
    ctx = _Contexto(spec, capa, datos)
    metodo = spec.analisis.metodo
    if metodo == "frecuencias":
        calculo = Calculo([_seccion_datos(ctx, NOMBRE_METODO["frecuencias"], relativas=spec.analisis.relativas)])
    elif metodo == "descriptiva":
        calculo = _calc_descriptiva(ctx)
    elif metodo == "serie":
        calculo = _calc_serie(ctx)
    elif metodo in ("variacion", "variacion_interanual"):
        calculo = _calc_variacion(ctx)
    elif metodo in ("pearson", "spearman"):
        calculo = _calc_correlacion(ctx)
    elif metodo in ("t_student", "mann_whitney"):
        calculo = _calc_dos_grupos(ctx)
    elif metodo == "chi_cuadrado":
        calculo = _calc_chi_cuadrado(ctx, prueba)
    elif metodo == "atipicos":
        calculo = _calc_atipicos(ctx)
    elif metodo == "pronostico":
        calculo = _calc_pronostico(ctx, publicar_pronostico)
    elif metodo == "segmentacion":
        calculo = _calc_segmentacion(ctx)
    else:  # pragma: no cover - el validador de specs no deja pasar otro método
        raise AnalisisNoAplicable(f"método desconocido: {metodo}")
    return calculo


def tabla_para_exportar(datos: pd.DataFrame, nombres: dict[str, str]) -> pd.DataFrame:
    """Datos del informe sin columnas auxiliares (`_…`, `__num`, `__den`) y con nombres legibles. Las columnas de
    tiempo (`tiempo_anio`, `tiempo_mes`…) se combinan en una sola etiqueta de periodo («2026-03», «2026-T1»), para
    que un año no se lea como cantidad («2.026»)."""
    visibles = [c for c in datos.columns if not c.startswith("_") and not c.endswith((SUFIJO_NUM, SUFIJO_DEN))]
    tabla = datos[visibles].copy()
    if "tiempo_anio" in tabla.columns:
        granularidad = next(
            (g for g, c in ((Granularidad.MES, "tiempo_mes"), (Granularidad.TRIMESTRE, "tiempo_trimestre"),
                            (Granularidad.SEMESTRE, "tiempo_semestre")) if c in tabla.columns),
            Granularidad.ANIO,
        )  # fmt: skip
        columnas_tiempo = [c for c in tabla.columns if c.startswith("tiempo_")]
        tabla = tabla.sort_values(columnas_tiempo, kind="mergesort")
        etiquetas = [_etiqueta_tiempo(f, granularidad) for _, f in tabla.iterrows()]
        tabla = tabla.drop(columns=columnas_tiempo)
        tabla.insert(0, DIMENSION_TIEMPO, etiquetas)
        visibles = list(tabla.columns)
    return tabla.reset_index(drop=True).rename(columns={c: nombres.get(c, c) for c in visibles})


__all__ = [
    "AnalisisNoAplicable",
    "Calculo",
    "ResultadoPronostico",
    "ResultadoSegmentacion",
    "calcular",
    "tabla_para_exportar",
]
