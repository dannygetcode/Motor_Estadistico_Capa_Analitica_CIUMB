"""Series de tiempo (Tabla 8, RF-03, OE1). Librería: pandas.

La agregación mensual, trimestral, semestral o anual ya la hace el compilador (columnas `tiempo_anio`,
`tiempo_mes`…). Aquí se ordena la serie, se completan los periodos faltantes y se calculan variaciones y
acumulados. Pruebas: `tests/motor/test_series.py`.
"""

from __future__ import annotations

import pandas as pd

from ciumb_analitica.spec.modelos import Granularidad

FRECUENCIAS: dict[Granularidad, str] = {
    Granularidad.MES: "M",
    Granularidad.TRIMESTRE: "Q",
    Granularidad.SEMESTRE: "2Q",
    Granularidad.ANIO: "Y",
}
"""Frecuencia de `pandas.Period` por granularidad. El semestre es '2Q': el semestre 1 es el periodo que empieza en
el trimestre 1 y el semestre 2 el que empieza en el trimestre 3."""


def _periodo(anio: int, sub: int | None, granularidad: Granularidad) -> pd.Period:
    if granularidad is Granularidad.MES:
        return pd.Period(year=anio, month=sub, freq="M")
    if granularidad is Granularidad.TRIMESTRE:
        return pd.Period(year=anio, quarter=sub, freq="Q")
    if granularidad is Granularidad.SEMESTRE:
        return pd.Period(f"{anio}Q{2 * sub - 1}", freq="2Q")
    return pd.Period(year=anio, freq="Y")


def periodos_por_anio(indice: pd.PeriodIndex) -> int:
    """Cuántos periodos de la frecuencia de `indice` caben en un año (12, 4, 2 o 1)."""
    freq = indice.freqstr.upper()
    if freq.startswith("M"):
        return 12
    if freq.startswith("2Q"):
        return 2
    if freq.startswith("Q"):
        return 4
    return 1


def a_serie(datos: pd.DataFrame, metrica: str, granularidad: Granularidad, *, completar: bool = True) -> pd.Series:
    """Convierte el resultado del compilador en una serie con índice `pandas.PeriodIndex`.

    Entradas: datos con `tiempo_anio` y la columna de la granularidad (`tiempo_mes`, `tiempo_trimestre` o
    `tiempo_semestre`). Salida: serie ordenada. Frecuencias: mes 'M', trimestre 'Q', semestre '2Q' (semestre 1
    = enero-junio), año 'Y'. Si `completar`, los periodos intermedios sin fila quedan en 0 para métricas
    aditivas; para razones y promedios quedan nulos (pasar `completar=False`).
    """
    columna_sub = {
        Granularidad.MES: "tiempo_mes",
        Granularidad.TRIMESTRE: "tiempo_trimestre",
        Granularidad.SEMESTRE: "tiempo_semestre",
    }.get(granularidad)
    frecuencia = FRECUENCIAS[granularidad]
    if datos.empty:
        return pd.Series([], index=pd.PeriodIndex([], freq=frecuencia), name=metrica, dtype=float)
    indice = [
        _periodo(int(fila["tiempo_anio"]), int(fila[columna_sub]) if columna_sub else None, granularidad)
        for _, fila in datos.iterrows()
    ]
    valores = pd.to_numeric(datos[metrica], errors="coerce").to_numpy(dtype=float)
    serie = pd.Series(valores, index=pd.PeriodIndex(indice, freq=frecuencia), name=metrica)
    serie = serie.groupby(level=0).sum(min_count=1).sort_index()
    if completar:
        completo = pd.period_range(serie.index.min(), serie.index.max(), freq=frecuencia)
        serie = serie.reindex(completo, fill_value=0.0)
    return serie


def variacion_porcentual(serie: pd.Series, *, rezago: int = 1) -> pd.Series:
    """Variación porcentual frente al periodo `rezago` posiciones atrás: 100 * (x_t - x_{t-r}) / |x_{t-r}|.

    El primer tramo queda nulo. Si el valor anterior es 0, la variación es nula (no infinito).
    `rezago=12` sobre una serie mensual da la variación interanual mes a mes.
    """
    anterior = serie.shift(rezago)
    variacion = 100.0 * (serie - anterior) / anterior.abs()
    return variacion.where(anterior != 0)


def acumulado(serie: pd.Series, *, reiniciar_cada_anio: bool = True) -> pd.Series:
    """Suma acumulada; por defecto se reinicia en enero (acumulado del año). Solo métricas aditivas."""
    if reiniciar_cada_anio and isinstance(serie.index, pd.PeriodIndex):
        return serie.groupby(serie.index.year).cumsum()
    return serie.cumsum()


def variacion_interanual(serie: pd.Series) -> dict:
    """Compara el último año de la serie con el mismo tramo del año anterior (P3, Figura 12).

    Entradas: serie mensual, trimestral o semestral que cubre dos años (el último puede estar incompleto).
    Salida: {"actual": suma del tramo del último año, "anterior": suma del MISMO tramo del año previo,
    "variacion_pct": 100 * (actual - anterior) / |anterior| o None si anterior es 0,
    "periodo_maximo": pandas.Period del mayor valor del último año, "valor_maximo": ese valor,
    "n_periodos": número de periodos comparados}.
    Ejemplo: enero-octubre de 2026 frente a enero-octubre de 2025, no frente a todo 2025.
    """
    if not isinstance(serie.index, pd.PeriodIndex) or serie.empty:
        raise ValueError("la variación interanual necesita una serie con índice de periodos")
    serie = serie.sort_index()
    paso = periodos_por_anio(serie.index)
    ultimo_anio = int(serie.index.max().year)
    tramo = serie[serie.index.year == ultimo_anio]
    previos = [p - paso for p in tramo.index]
    anterior_tramo = serie.reindex(pd.PeriodIndex(previos, freq=serie.index.freq))
    actual = float(tramo.sum())
    anterior = float(anterior_tramo.fillna(0.0).sum())
    periodo_maximo = tramo.idxmax()
    return {
        "actual": actual,
        "anterior": anterior,
        "variacion_pct": None if anterior == 0 else 100.0 * (actual - anterior) / abs(anterior),
        "periodo_maximo": periodo_maximo,
        "valor_maximo": float(tramo.loc[periodo_maximo]),
        "n_periodos": int(len(tramo)),
    }
