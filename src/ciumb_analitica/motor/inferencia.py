"""Inferencia (Tabla 8, RF-04, OE1): correlaciones y pruebas de hipótesis con valor p y tamaño de muestra.
Librería: SciPy (statsmodels donde haga falta).

Regla de muestra pequeña (RNF-13, invariante 7): el chi-cuadrado con alguna frecuencia esperada < 5 sale CON
advertencia `CHI2_ESPERADO_BAJO`; nunca se oculta el aviso ni se omite el valor p.
Pruebas: `tests/motor/test_inferencia.py` (contraste con `scipy.stats`).
"""

from __future__ import annotations

import pandas as pd

from ciumb_analitica.motor.resultado import PENDIENTE, ResultadoPrueba


def correlacion(x: pd.Series, y: pd.Series, *, metodo: str = "pearson", alfa: float = 0.05) -> ResultadoPrueba:
    """Correlación de Pearson o de Spearman con valor p bilateral.

    Entradas: dos series alineadas por índice; los pares con algún nulo se descartan. `metodo`: 'pearson' o
    'spearman'. Salida: `ResultadoPrueba` con `estadistico` = r o rho y `n` = pares usados.
    Referencia: `scipy.stats.pearsonr` / `scipy.stats.spearmanr`.
    Lanza `MuestraInsuficiente` con menos de 3 pares o si una variable es constante.
    Advertencia `MUESTRA_PEQUENA` con menos de 20 pares.
    """
    raise NotImplementedError(PENDIENTE)


def tabla_contingencia(datos: pd.DataFrame, fila: str, columna: str, conteo: str) -> pd.DataFrame:
    """Arma la tabla de contingencia desde la consulta `prueba` de dos dimensiones.

    Entradas: datos con las columnas `fila`, `columna` y `conteo` (una fila por celda; las celdas ausentes
    valen 0). Salida: DataFrame con índice = categorías de `fila` y columnas = categorías de `columna`,
    ambos ordenados.
    """
    raise NotImplementedError(PENDIENTE)


def tabla_contingencia_de_razon(
    datos: pd.DataFrame, fila: str, metrica: str, categorias: tuple[str, str]
) -> pd.DataFrame:
    """Tabla de contingencia de una dimensión binaria derivada de una razón (D-19; P4).

    Entradas: consulta `prueba` con `fila`, `<metrica>__num` y `<metrica>__den`; `categorias` =
    `spec.convenciones.CATEGORIAS_BINARIA[...]`, p. ej. ('atrasado', 'a_tiempo').
    Salida: índice = categorías de `fila`; dos columnas: categorias[0] = num, categorias[1] = den - num.
    """
    raise NotImplementedError(PENDIENTE)


def chi_cuadrado(tabla: pd.DataFrame, *, alfa: float = 0.05) -> ResultadoPrueba:
    """Prueba chi-cuadrado de independencia sobre una tabla de contingencia.

    Referencia: `scipy.stats.chi2_contingency(tabla, correction=False)`. `n` = total de la tabla;
    `grados_libertad` = (filas - 1)(columnas - 1).
    Si alguna frecuencia esperada es < 5 (`spec.resultado.MIN_ESPERADO_CHI2`), agrega la advertencia
    `CHI2_ESPERADO_BAJO` indicando cuántas celdas; el resultado se devuelve igual.
    Se eliminan antes las filas y columnas con total 0. Lanza `MuestraInsuficiente` si quedan menos de 2 x 2.
    """
    raise NotImplementedError(PENDIENTE)


def t_student(a: pd.Series, b: pd.Series, *, alfa: float = 0.05) -> ResultadoPrueba:
    """t de Student para dos muestras independientes, bilateral, sin asumir varianzas iguales (Welch).

    Referencia: `scipy.stats.ttest_ind(a, b, equal_var=False)`. `n` = n1 + n2. `grados_libertad` de
    Welch-Satterthwaite. Lanza `MuestraInsuficiente` si algún grupo tiene menos de 2 observaciones.
    Advertencia `MUESTRA_PEQUENA` si algún grupo tiene menos de 20.
    """
    raise NotImplementedError(PENDIENTE)


def mann_whitney(a: pd.Series, b: pd.Series, *, alfa: float = 0.05) -> ResultadoPrueba:
    """U de Mann-Whitney bilateral (alternativa no paramétrica a la t).

    Referencia: `scipy.stats.mannwhitneyu(a, b, alternative="two-sided")`. `estadistico` = U del primer grupo.
    Lanza `MuestraInsuficiente` si algún grupo está vacío.
    """
    raise NotImplementedError(PENDIENTE)


def dos_grupos(datos: pd.DataFrame, metrica: str, grupo: str) -> tuple[pd.Series, pd.Series, tuple[str, str]]:
    """Separa los registros en los dos grupos de `grupo` para `t_student` / `mann_whitney`.

    Salida: (valores del grupo 1, valores del grupo 2, (etiqueta 1, etiqueta 2)) con las etiquetas en orden
    alfabético. Lanza `ValueError` si la dimensión no tiene exactamente dos categorías con datos: el motor lo
    convierte en un aviso para repreguntar (paso 5 del validador de specs).
    """
    raise NotImplementedError(PENDIENTE)
