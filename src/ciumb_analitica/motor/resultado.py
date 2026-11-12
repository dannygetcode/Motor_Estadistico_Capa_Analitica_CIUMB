"""Tipos de salida del motor estadístico y del módulo de ML. Son la entrada del empaquetador del contrato.

Regla: todo lo que el motor devuelve son números calculados con pandas, NumPy, SciPy, statsmodels o
scikit-learn (invariante 1). Las advertencias usan los códigos de `spec.resultado` (RNF-13).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ciumb_analitica.spec.resultado import Aviso

PENDIENTE = "pendiente de implementar"
"""Motivo de las pruebas `xfail` del relevo. Al implementar una función, quitar su marca `xfail`."""


class MuestraInsuficiente(ValueError):  # noqa: N818 - nombre de dominio en español
    """La muestra no alcanza para aplicar el método (p. ej. correlación con menos de 3 pares, pronóstico con
    menos de 12 puntos). No se devuelve un número que el tamaño de la muestra no sostiene (RNF-13)."""


@dataclass(frozen=True)
class ResumenDescriptivo:
    """Medidas de la Tabla 8 (RF-02) para una variable numérica. `desviacion` es la muestral (ddof = 1) y es
    `None` con n < 2. `moda` es la menor de las modas, o `None` si todos los valores son distintos."""

    n: int
    media: float
    mediana: float
    moda: float | None
    desviacion: float | None
    minimo: float
    maximo: float
    q1: float
    q3: float
    percentiles: dict[int, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ResultadoPrueba:
    """Resultado de una correlación o prueba de hipótesis (RF-04): siempre con valor p y tamaño de muestra.

    metodo: 'pearson' | 'spearman' | 'chi_cuadrado' | 't_student' | 'mann_whitney'.
    estadistico: r, rho, chi2, t o U. n: observaciones usadas (pares, total de la tabla o n1 + n2).
    significativo: valor_p < alfa. grados_libertad: solo chi-cuadrado y t.
    advertencias: p. ej. CHI2_ESPERADO_BAJO o MUESTRA_PEQUENA; el valor p se reporta junto a ellas.
    """

    metodo: str
    estadistico: float
    valor_p: float
    n: int
    alfa: float
    significativo: bool
    grados_libertad: float | None = None
    advertencias: tuple[Aviso, ...] = ()


@dataclass(frozen=True)
class ResultadoAtipicos:
    """Atípicos de una variable (RF-05). `es_atipico` tiene el mismo índice que la serie de entrada."""

    metodo: str  # 'RIC' | 'puntaje_z'
    k: float
    limite_inferior: float
    limite_superior: float
    es_atipico: pd.Series
    n: int

    @property
    def cantidad(self) -> int:
        return int(self.es_atipico.sum())


@dataclass(frozen=True)
class ResultadoPronostico:
    """Pronóstico con intervalo (RF-06). Las tres series tienen `horizonte` valores, en orden.

    mae_modelo / mae_ingenuo: error absoluto medio con validación de origen móvil frente a la línea base
    ingenua (último valor observado). Si el modelo no mejora a la línea base, lleva advertencia.
    """

    tecnica: str  # 'holt' | 'regresion_lineal'
    nivel_confianza: float
    valores: tuple[float, ...]
    inferior: tuple[float, ...]
    superior: tuple[float, ...]
    n: int
    mae_modelo: float
    mae_ingenuo: float
    advertencias: tuple[Aviso, ...] = ()


@dataclass(frozen=True)
class ResultadoSegmentacion:
    """Agrupamiento k-medias (INF-EMP-03). `etiquetas` tiene el índice de los datos de entrada; los grupos se
    numeran de 0 a k-1 ordenados de mayor a menor tamaño, para que el resultado sea reproducible."""

    k: int
    silueta: float
    etiquetas: pd.Series
    centroides: pd.DataFrame  # en las unidades originales, una fila por grupo
    tamanos: tuple[int, ...]
    siluetas_por_k: dict[int, float] = field(default_factory=dict)


@dataclass(frozen=True)
class SeccionCalculada:
    """Una sección del informe lista para el contrato.

    indicadores: dicts con los campos de `contrato.modelos.Indicador` (id, valor, anterior, variacion_pct,
    unidad, n, meta, metodo, mes, grupo, valor_p, ic_inferior, ic_superior). Solo agregados.
    metodo: descripción en español del método de la sección. advertencias: mensajes de los avisos.
    """

    id: str
    indicadores: list[dict]
    metodo: str
    advertencias: list[str] = field(default_factory=list)
