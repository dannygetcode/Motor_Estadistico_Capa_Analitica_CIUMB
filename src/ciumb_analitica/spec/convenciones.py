"""Convenciones compartidas entre el validador, el compilador, el motor y los gráficos.

INTERFAZ CERRADA: los nombres de las columnas del resultado de una consulta compilada se definen aquí y solo
aquí.

Columnas del resultado:
- Una dimensión -> una columna con su código (`facultad`, `estado`…).
- La dimensión `tiempo` -> `tiempo_anio` y, según la granularidad, `tiempo_mes`, `tiempo_trimestre` o
  `tiempo_semestre`.
- Una métrica -> una columna con su código. Si es una razón, además `<codigo>__num` y `<codigo>__den`
  (sus componentes, para recalcularla en cualquier total).
- `_n_personas` (nivel agregado) o `_persona` (nivel registro): solo cuando la métrica cuenta personas; el
  validador las usa para suprimir grupos con menos de cinco personas y luego las elimina. Nunca se exportan.
"""

from __future__ import annotations

from ciumb_analitica.spec.modelos import DimensionSpec, Granularidad, Rol

DIMENSION_TIEMPO = "tiempo"

COLUMNAS_GRANULARIDAD: dict[Granularidad, tuple[str, ...]] = {
    Granularidad.MES: ("anio", "mes"),
    Granularidad.TRIMESTRE: ("anio", "trimestre"),
    Granularidad.SEMESTRE: ("anio", "semestre"),
    Granularidad.ANIO: ("anio",),
}

COL_N_PERSONAS = "_n_personas"
COL_PERSONA = "_persona"

SUFIJO_NUM = "__num"
SUFIJO_DEN = "__den"

# Categorías de una dimensión binaria derivada de una razón (D-19): (numerador, denominador - numerador).
CATEGORIAS_BINARIA = {"estado_hito": ("atrasado", "a_tiempo")}

# RF-21: hechos que puede consultar un rol restringido a «lo que tiene a su cargo» (D-20).
HECHOS_POR_ROL: dict[Rol, tuple[str, ...]] = {
    Rol.TUTOR: ("hecho_practica",),
    Rol.CONSULTOR: ("hecho_consultoria",),
}
DIMENSION_ALCANCE_COORDINADOR = "facultad"


def columnas_de_dimension(dimension: DimensionSpec) -> tuple[str, ...]:
    """Nombres de las columnas del resultado que corresponden a una dimensión de la spec resuelta."""
    if dimension.id == DIMENSION_TIEMPO:
        granularidad = dimension.granularidad or Granularidad.MES
        return tuple(f"tiempo_{c}" for c in COLUMNAS_GRANULARIDAD[granularidad])
    return (dimension.id,)


def columnas_de_dimensiones(dimensiones) -> list[str]:
    return [c for d in dimensiones for c in columnas_de_dimension(d)]
