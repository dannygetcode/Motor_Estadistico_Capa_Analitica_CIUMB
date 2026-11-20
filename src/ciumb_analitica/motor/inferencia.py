"""Inferencia (Tabla 8, RF-04, OE1): correlaciones y pruebas de hipótesis con valor p y tamaño de muestra.
Librería: SciPy (statsmodels donde haga falta).

Regla de muestra pequeña (RNF-13, invariante 7): el chi-cuadrado con alguna frecuencia esperada < 5 sale CON
advertencia `CHI2_ESPERADO_BAJO`; nunca se oculta el aviso ni se omite el valor p.
Pruebas: `tests/motor/test_inferencia.py` (contraste con `scipy.stats`).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from ciumb_analitica.motor.resultado import MuestraInsuficiente, ResultadoPrueba
from ciumb_analitica.spec import resultado as r

MIN_PARES_CORRELACION = 3
MIN_MUESTRA_SIN_AVISO = 20
"""Por debajo de 20 observaciones (pares o por grupo) el resultado lleva `MUESTRA_PEQUENA` (RNF-13)."""


def _aviso_muestra(n: int, que: str) -> r.Aviso:
    return r.Aviso(
        codigo=r.MUESTRA_PEQUENA,
        mensaje=f"Muestra pequeña: {n} {que} (menos de {MIN_MUESTRA_SIN_AVISO}); interpretar con cautela.",
    )


def _numerica(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie, errors="coerce").dropna().astype(float)


def correlacion(x: pd.Series, y: pd.Series, *, metodo: str = "pearson", alfa: float = 0.05) -> ResultadoPrueba:
    """Correlación de Pearson o de Spearman con valor p bilateral.

    Entradas: dos series alineadas por índice; los pares con algún nulo se descartan. `metodo`: 'pearson' o
    'spearman'. Salida: `ResultadoPrueba` con `estadistico` = r o rho y `n` = pares usados.
    Referencia: `scipy.stats.pearsonr` / `scipy.stats.spearmanr`.
    Lanza `MuestraInsuficiente` con menos de 3 pares o si una variable es constante.
    Advertencia `MUESTRA_PEQUENA` con menos de 20 pares.
    """
    if metodo not in ("pearson", "spearman"):
        raise ValueError(f"método de correlación desconocido: {metodo}")
    pares = pd.concat([pd.to_numeric(x, errors="coerce"), pd.to_numeric(y, errors="coerce")], axis=1).dropna()
    n = len(pares)
    if n < MIN_PARES_CORRELACION:
        raise MuestraInsuficiente(f"la correlación necesita al menos {MIN_PARES_CORRELACION} pares; hay {n}")
    a, b = pares.iloc[:, 0].to_numpy(float), pares.iloc[:, 1].to_numpy(float)
    if np.ptp(a) == 0 or np.ptp(b) == 0:
        raise MuestraInsuficiente("una de las variables es constante: la correlación no está definida")
    referencia = stats.pearsonr(a, b) if metodo == "pearson" else stats.spearmanr(a, b)
    valor_p = float(referencia.pvalue)
    avisos = (_aviso_muestra(n, "pares"),) if n < MIN_MUESTRA_SIN_AVISO else ()
    return ResultadoPrueba(
        metodo=metodo,
        estadistico=float(referencia.statistic),
        valor_p=valor_p,
        n=n,
        alfa=alfa,
        significativo=bool(valor_p < alfa),
        advertencias=avisos,
    )


def tabla_contingencia(datos: pd.DataFrame, fila: str, columna: str, conteo: str) -> pd.DataFrame:
    """Arma la tabla de contingencia desde la consulta `prueba` de dos dimensiones.

    Entradas: datos con las columnas `fila`, `columna` y `conteo` (una fila por celda; las celdas ausentes
    valen 0). Salida: DataFrame con índice = categorías de `fila` y columnas = categorías de `columna`,
    ambos ordenados.
    """
    tabla = datos.pivot_table(index=fila, columns=columna, values=conteo, aggfunc="sum", fill_value=0)
    tabla = tabla.sort_index(axis=0).sort_index(axis=1)
    tabla.index.name, tabla.columns.name = fila, columna
    return tabla


def tabla_contingencia_de_razon(
    datos: pd.DataFrame, fila: str, metrica: str, categorias: tuple[str, str]
) -> pd.DataFrame:
    """Tabla de contingencia de una dimensión binaria derivada de una razón (D-19; P4).

    Entradas: consulta `prueba` con `fila`, `<metrica>__num` y `<metrica>__den`; `categorias` =
    `spec.convenciones.CATEGORIAS_BINARIA[...]`, p. ej. ('atrasado', 'a_tiempo').
    Salida: índice = categorías de `fila`; dos columnas: categorias[0] = num, categorias[1] = den - num.
    """
    num = pd.to_numeric(datos[f"{metrica}__num"], errors="coerce").fillna(0.0)
    den = pd.to_numeric(datos[f"{metrica}__den"], errors="coerce").fillna(0.0)
    tabla = pd.DataFrame(
        {categorias[0]: num.to_numpy(), categorias[1]: (den - num).to_numpy()},
        index=pd.Index(datos[fila].to_numpy(), name=fila),
    )
    return tabla.groupby(level=0, sort=True).sum()


def chi_cuadrado(tabla: pd.DataFrame, *, alfa: float = 0.05) -> ResultadoPrueba:
    """Prueba chi-cuadrado de independencia sobre una tabla de contingencia.

    Referencia: `scipy.stats.chi2_contingency(tabla, correction=False)`. `n` = total de la tabla;
    `grados_libertad` = (filas - 1)(columnas - 1).
    Si alguna frecuencia esperada es < 5 (`spec.resultado.MIN_ESPERADO_CHI2`), agrega la advertencia
    `CHI2_ESPERADO_BAJO` indicando cuántas celdas; el resultado se devuelve igual.
    Se eliminan antes las filas y columnas con total 0. Lanza `MuestraInsuficiente` si quedan menos de 2 x 2.
    """
    t = tabla.apply(pd.to_numeric, errors="coerce").fillna(0)
    t = t.loc[t.sum(axis=1) > 0, t.sum(axis=0) > 0]
    if t.shape[0] < 2 or t.shape[1] < 2:
        raise MuestraInsuficiente(
            f"el chi-cuadrado necesita una tabla de al menos 2 x 2; quedó {t.shape[0]} x {t.shape[1]}"
        )
    referencia = stats.chi2_contingency(t.to_numpy(dtype=float), correction=False)
    bajas = int((referencia.expected_freq < r.MIN_ESPERADO_CHI2).sum())
    avisos = ()
    if bajas:
        avisos = (
            r.Aviso(
                codigo=r.CHI2_ESPERADO_BAJO,
                mensaje=(
                    f"{bajas} de {referencia.expected_freq.size} celdas tienen frecuencia esperada menor que "
                    f"{r.MIN_ESPERADO_CHI2}; el valor p del chi-cuadrado es aproximado."
                ),
            ),
        )
    valor_p = float(referencia.pvalue)
    return ResultadoPrueba(
        metodo="chi_cuadrado",
        estadistico=float(referencia.statistic),
        valor_p=valor_p,
        n=int(round(float(t.to_numpy().sum()))),
        alfa=alfa,
        significativo=bool(valor_p < alfa),
        grados_libertad=float(referencia.dof),
        advertencias=avisos,
    )


def t_student(a: pd.Series, b: pd.Series, *, alfa: float = 0.05) -> ResultadoPrueba:
    """t de Student para dos muestras independientes, bilateral, sin asumir varianzas iguales (Welch).

    Referencia: `scipy.stats.ttest_ind(a, b, equal_var=False)`. `n` = n1 + n2. `grados_libertad` de
    Welch-Satterthwaite. Lanza `MuestraInsuficiente` si algún grupo tiene menos de 2 observaciones.
    Advertencia `MUESTRA_PEQUENA` si algún grupo tiene menos de 20.
    """
    x, y = _numerica(a), _numerica(b)
    if len(x) < 2 or len(y) < 2:
        raise MuestraInsuficiente(f"la t necesita al menos 2 observaciones por grupo; hay {len(x)} y {len(y)}")
    referencia = stats.ttest_ind(x, y, equal_var=False)
    valor_p = float(referencia.pvalue)
    menor = min(len(x), len(y))
    return ResultadoPrueba(
        metodo="t_student",
        estadistico=float(referencia.statistic),
        valor_p=valor_p,
        n=len(x) + len(y),
        alfa=alfa,
        significativo=bool(valor_p < alfa),
        grados_libertad=float(referencia.df),
        advertencias=(_aviso_muestra(menor, "observaciones en el grupo menor"),)
        if menor < MIN_MUESTRA_SIN_AVISO
        else (),
    )


def mann_whitney(a: pd.Series, b: pd.Series, *, alfa: float = 0.05) -> ResultadoPrueba:
    """U de Mann-Whitney bilateral (alternativa no paramétrica a la t).

    Referencia: `scipy.stats.mannwhitneyu(a, b, alternative="two-sided")`. `estadistico` = U del primer grupo.
    Lanza `MuestraInsuficiente` si algún grupo está vacío.
    """
    x, y = _numerica(a), _numerica(b)
    if len(x) == 0 or len(y) == 0:
        raise MuestraInsuficiente("la U de Mann-Whitney necesita observaciones en los dos grupos")
    referencia = stats.mannwhitneyu(x, y, alternative="two-sided")
    valor_p = float(referencia.pvalue)
    menor = min(len(x), len(y))
    return ResultadoPrueba(
        metodo="mann_whitney",
        estadistico=float(referencia.statistic),
        valor_p=valor_p,
        n=len(x) + len(y),
        alfa=alfa,
        significativo=bool(valor_p < alfa),
        advertencias=(_aviso_muestra(menor, "observaciones en el grupo menor"),)
        if menor < MIN_MUESTRA_SIN_AVISO
        else (),
    )


def dos_grupos(datos: pd.DataFrame, metrica: str, grupo: str) -> tuple[pd.Series, pd.Series, tuple[str, str]]:
    """Separa los registros en los dos grupos de `grupo` para `t_student` / `mann_whitney`.

    Salida: (valores del grupo 1, valores del grupo 2, (etiqueta 1, etiqueta 2)) con las etiquetas en orden
    alfabético. Lanza `ValueError` si la dimensión no tiene exactamente dos categorías con datos: el motor lo
    convierte en un aviso para repreguntar (paso 5 del validador de specs).
    """
    validos = datos.dropna(subset=[grupo])
    validos = validos[pd.to_numeric(validos[metrica], errors="coerce").notna()]
    etiquetas = sorted(validos[grupo].astype(str).unique())
    if len(etiquetas) != 2:
        raise ValueError(
            f"la dimensión '{grupo}' debe tener exactamente dos categorías con datos; tiene {len(etiquetas)}"
        )
    claves = validos[grupo].astype(str)
    a = pd.to_numeric(validos.loc[claves == etiquetas[0], metrica]).astype(float).reset_index(drop=True)
    b = pd.to_numeric(validos.loc[claves == etiquetas[1], metrica]).astype(float).reset_index(drop=True)
    return a, b, (etiquetas[0], etiquetas[1])
