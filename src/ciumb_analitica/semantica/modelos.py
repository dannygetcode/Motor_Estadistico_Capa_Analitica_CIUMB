"""Capa semántica: el diccionario que dice qué se puede pedir (sección 4.4.2, DA-07).

`CapaSemantica` es el objeto en memoria que usan el validador de specs y el compilador. Se construye desde la
semilla (`semantica.semilla.capa_semilla`) o desde las tablas `rpt_metrica`, `rpt_dimension` y
`rpt_compatibilidad` (`semantica.almacen.leer_capa`). Al construirse comprueba que cada tabla y columna exista
en el esquema `ana_`: es la lista blanca de identificadores del compilador.
"""

from __future__ import annotations

from enum import StrEnum
from functools import cached_property

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Column, Table

from ciumb_analitica.dw import esquema as dw
from ciumb_analitica.semantica.expresion import Expresion, analizar
from ciumb_analitica.spec.modelos import METODOS_ANALISIS, PATRON_CODIGO, Agregacion, Granularidad, TipoGrafico

VERSION_SEMANTICA = "1.0"


class Aditividad(StrEnum):
    ADITIVA = "aditiva"  # se puede sumar por cualquier dimensión
    SEMIADITIVA = "semiaditiva"  # instantánea: no se suma entre fechas de corte
    NO_ADITIVA = "no_aditiva"  # razón o porcentaje: se recalcula desde sus componentes


class TipoDimension(StrEnum):
    CATEGORICA = "categorica"
    TEMPORAL = "temporal"
    ORDINAL = "ordinal"


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AgregadoAlterno(_Base):
    """Agregado precalculado que puede responder la métrica cuando cubre las dimensiones pedidas."""

    tabla: str
    expresion_sql: str

    @cached_property
    def expresion(self) -> Expresion:
        return analizar(self.expresion_sql)


class Metrica(_Base):
    codigo: str = Field(pattern=PATRON_CODIGO)
    nombre: str
    descripcion: str
    sinonimos: tuple[str, ...] = ()
    hecho_o_agregado: str
    expresion_sql: str
    agregaciones: tuple[Agregacion, ...]
    agregacion_defecto: Agregacion
    aditividad: Aditividad
    unidad: str
    columna_personas: str | None = None
    agregados: tuple[AgregadoAlterno, ...] = ()
    activa: bool = True

    @cached_property
    def expresion(self) -> Expresion:
        return analizar(self.expresion_sql)

    @property
    def tabla(self) -> Table:
        return dw.tabla(self.hecho_o_agregado)

    @property
    def es_conteo(self) -> bool:
        return self.expresion.tipo == "conteo"

    @property
    def es_razon(self) -> bool:
        return self.expresion.tipo == "razon"

    @model_validator(mode="after")
    def _coherencia(self) -> Metrica:
        _exigir_columnas(self.hecho_o_agregado, self.expresion.columnas, self.codigo)
        if self.columna_personas:
            _exigir_columnas(self.hecho_o_agregado, (self.columna_personas,), self.codigo)
        for alterno in self.agregados:
            _exigir_columnas(alterno.tabla, alterno.expresion.columnas, self.codigo)
            if alterno.expresion.tipo == "conteo":
                raise ValueError(f"{self.codigo}: un agregado alterno no puede ser un conteo de filas")
        if self.agregacion_defecto not in self.agregaciones:
            raise ValueError(f"{self.codigo}: la agregación por defecto no está entre las válidas")
        if self.es_razon and (self.agregaciones != (Agregacion.RAZON,) or self.aditividad is not Aditividad.NO_ADITIVA):
            raise ValueError(f"{self.codigo}: una razón solo admite la agregación 'razon' y es no aditiva")
        if self.es_conteo and self.agregaciones != (Agregacion.CONTEO,):
            raise ValueError(f"{self.codigo}: un conteo de filas solo admite la agregación 'conteo'")
        if self.expresion.tipo == "columna" and {Agregacion.RAZON, Agregacion.CONTEO} & set(self.agregaciones):
            raise ValueError(f"{self.codigo}: una medida admite suma, promedio o mediana")
        return self


class Dimension(_Base):
    codigo: str = Field(pattern=PATRON_CODIGO)
    nombre: str
    descripcion: str
    sinonimos: tuple[str, ...] = ()
    tabla_columna: str | None = None
    tipo: TipoDimension
    identifica_persona: bool = False
    viaja_a_ia: bool = True
    binaria_de_metrica: str | None = Field(
        default=None,
        description="Dimensión de dos categorías derivada de los componentes de una razón (num, den - num). "
        "Solo sirve como variable de una prueba con esa métrica (D-19).",
    )

    @property
    def nombre_tabla(self) -> str | None:
        return self.tabla_columna.split(".")[0] if self.tabla_columna else None

    @property
    def tabla(self) -> Table:
        return dw.tabla(self.nombre_tabla)

    @property
    def columna(self) -> Column:
        return self.tabla.c[self.tabla_columna.split(".")[1]]

    @property
    def es_temporal(self) -> bool:
        return self.tipo is TipoDimension.TEMPORAL

    @model_validator(mode="after")
    def _coherencia(self) -> Dimension:
        if (self.tabla_columna is None) == (self.binaria_de_metrica is None):
            raise ValueError(f"{self.codigo}: exactamente uno de tabla_columna o binaria_de_metrica")
        if self.tabla_columna:
            partes = self.tabla_columna.split(".")
            if len(partes) != 2:
                raise ValueError(f"{self.codigo}: tabla_columna debe ser 'tabla.columna'")
            _exigir_columnas(partes[0], (partes[1],), self.codigo)
        if self.identifica_persona and self.viaja_a_ia:
            raise ValueError(f"{self.codigo}: una dimensión que identifica personas no viaja a la IA")
        return self


def _exigir_columnas(tabla: str, columnas: tuple[str, ...], codigo: str) -> None:
    try:
        t = dw.tabla(tabla)
    except KeyError:
        raise ValueError(f"{codigo}: la tabla '{tabla}' no existe en el esquema ana_") from None
    faltan = [c for c in columnas if c not in t.c]
    if faltan:
        raise ValueError(f"{codigo}: columnas inexistentes en {tabla}: {faltan}")


DIMENSION_TIEMPO = "tiempo"
"""Código de la dimensión temporal con granularidad (`dim_tiempo.fecha`)."""


class CapaSemantica(_Base):
    version: str = VERSION_SEMANTICA
    metricas: dict[str, Metrica]
    dimensiones: dict[str, Dimension]
    compatibilidad: frozenset[tuple[str, str]]

    @model_validator(mode="after")
    def _coherencia(self) -> CapaSemantica:
        for codigo, m in self.metricas.items():
            if codigo != m.codigo:
                raise ValueError(f"métrica mal indexada: {codigo}")
        for codigo, d in self.dimensiones.items():
            if codigo != d.codigo:
                raise ValueError(f"dimensión mal indexada: {codigo}")
            if d.binaria_de_metrica and not self.metricas[d.binaria_de_metrica].es_razon:
                raise ValueError(f"{codigo}: binaria_de_metrica debe apuntar a una razón")
        if set(self.metricas) & set(self.dimensiones):
            raise ValueError("un código no puede ser a la vez métrica y dimensión")
        for m, d in self.compatibilidad:
            if m not in self.metricas or d not in self.dimensiones:
                raise ValueError(f"compatibilidad con código inexistente: {m} x {d}")
            if not alcanzable(self.metricas[m], self.dimensiones[d]):
                raise ValueError(f"compatibilidad imposible: {self.metricas[m].hecho_o_agregado} no llega a {d}")
        return self

    def metrica(self, codigo: str) -> Metrica | None:
        m = self.metricas.get(codigo)
        return m if m and m.activa else None

    def dimension(self, codigo: str) -> Dimension | None:
        return self.dimensiones.get(codigo)

    def es_compatible(self, metrica: str, dimension: str) -> bool:
        return (metrica, dimension) in self.compatibilidad

    def dimensiones_compatibles(self, metrica: str, *, sin_personas: bool = True) -> list[str]:
        return sorted(
            d
            for m, d in self.compatibilidad
            if m == metrica and not (sin_personas and self.dimensiones[d].identifica_persona)
        )

    def publicar(self) -> dict:
        """Versión publicada para la capa de IA (GET /semantica): nombres y descripciones, sin datos ni
        nombres de tablas o columnas (DA-07)."""
        return {
            "version": self.version,
            "metricas": [
                {
                    "codigo": m.codigo,
                    "nombre": m.nombre,
                    "descripcion": m.descripcion,
                    "sinonimos": list(m.sinonimos),
                    "agregaciones": [a.value for a in m.agregaciones],
                    "agregacion_defecto": m.agregacion_defecto.value,
                    "unidad": m.unidad,
                    "dimensiones_compatibles": self.dimensiones_compatibles(m.codigo),
                }
                for m in sorted(self.metricas.values(), key=lambda x: x.codigo)
                if m.activa
            ],
            "dimensiones": [
                {
                    "codigo": d.codigo,
                    "nombre": d.nombre,
                    "descripcion": d.descripcion,
                    "sinonimos": list(d.sinonimos),
                    "tipo": d.tipo.value,
                    "identifica_persona": d.identifica_persona,
                    **({"granularidades": [g.value for g in Granularidad]} if d.codigo == DIMENSION_TIEMPO else {}),
                    **({"solo_para_metrica": d.binaria_de_metrica} if d.binaria_de_metrica else {}),
                }
                for d in sorted(self.dimensiones.values(), key=lambda x: x.codigo)
            ],
            "metodos": list(METODOS_ANALISIS),
            "graficos": [g.value for g in TipoGrafico],
        }


def alcanzable(metrica: Metrica, dimension: Dimension, *, tabla: Table | None = None) -> bool:
    """¿El hecho (o el agregado `tabla`) de la métrica tiene la dimensión? Es la matriz de bus (Tabla 15):
    la dimensión es una columna del propio hecho o hay una clave foránea del hecho hacia su tabla."""
    hecho = tabla if tabla is not None else metrica.tabla
    if dimension.binaria_de_metrica:
        return dimension.binaria_de_metrica == metrica.codigo
    if dimension.tabla is hecho:
        return True
    return dw.columna_fk_hacia(hecho, dimension.tabla) is not None
