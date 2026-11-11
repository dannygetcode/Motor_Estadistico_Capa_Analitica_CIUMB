"""Resultado del validador de especificaciones y especificación resuelta.

INTERFAZ CERRADA. `SpecResuelta` es lo que reciben el compilador, el motor, los gráficos y el empaquetador:
la spec de la capa de IA con todos los valores por defecto ya decididos (agregación, granularidad, periodo,
método, gráfico y nivel de lectura). Es determinista: misma spec + misma fecha de referencia -> misma
`SpecResuelta` -> misma huella.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ciumb_analitica.spec.modelos import (
    Agregacion,
    Alcance,
    Analisis,
    DimensionSpec,
    Filtro,
    Granularidad,
    Origen,
    OrigenGrafico,
    Salida,
    TipoGrafico,
)


class Estado(StrEnum):
    VALIDA = "valida"
    CORREGIBLE = "corregible"
    FUERA_DE_ALCANCE = "fuera_de_alcance"


class Nivel(StrEnum):
    AGREGADO = "agregado"  # una fila por combinación de dimensiones
    REGISTRO = "registro"  # una fila por registro del hecho (proyecto, práctica, consultoría…)


# --- Códigos de problema (bloquean) --------------------------------------------------------------------------
ESQUEMA_INVALIDO = "ESQUEMA_INVALIDO"
FALTA_METRICA = "FALTA_METRICA"
METRICA_INEXISTENTE = "METRICA_INEXISTENTE"  # fuera de alcance: no hay nada parecido
METRICA_PARECIDA = "METRICA_PARECIDA"  # corregible: hay códigos parecidos en `opciones`
DIMENSION_INEXISTENTE = "DIMENSION_INEXISTENTE"
DIMENSION_PARECIDA = "DIMENSION_PARECIDA"
PLANTILLA_INEXISTENTE = "PLANTILLA_INEXISTENTE"
DIMENSION_IDENTIFICA_PERSONAS = "DIMENSION_IDENTIFICA_PERSONAS"
INCOMPATIBLE = "INCOMPATIBLE"
AGREGACION_INVALIDA = "AGREGACION_INVALIDA"
DIMENSION_SOLO_PRUEBA = "DIMENSION_SOLO_PRUEBA"
GRANULARIDAD_NO_APLICA = "GRANULARIDAD_NO_APLICA"
OPERADOR_INVALIDO = "OPERADOR_INVALIDO"
VALOR_INVALIDO = "VALOR_INVALIDO"
ALCANCE_NO_APLICABLE = "ALCANCE_NO_APLICABLE"
ALCANCE_EXCEDIDO = "ALCANCE_EXCEDIDO"
PERIODO_FUTURO = "PERIODO_FUTURO"
VARIABLES_INVALIDAS = "VARIABLES_INVALIDAS"
FALTA_DIMENSION_TEMPORAL = "FALTA_DIMENSION_TEMPORAL"
FALTA_UNIDAD_DE_ANALISIS = "FALTA_UNIDAD_DE_ANALISIS"
METODO_NO_APLICABLE = "METODO_NO_APLICABLE"
METRICAS_DE_HECHOS_DISTINTOS = "METRICAS_DE_HECHOS_DISTINTOS"

# --- Códigos de aviso (no bloquean; van al anexo del informe y a `advertencias` del contrato) -----------------
PERIODO_POR_DEFECTO = "PERIODO_POR_DEFECTO"
PERIODO_RECORTADO = "PERIODO_RECORTADO"
GRAFICO_SUSTITUIDO = "GRAFICO_SUSTITUIDO"
TORTA_OTROS = "TORTA_OTROS"
MUESTRA_PEQUENA = "MUESTRA_PEQUENA"
PRONOSTICO_NO_PUBLICABLE = "PRONOSTICO_NO_PUBLICABLE"
GRUPOS_SUPRIMIDOS = "GRUPOS_SUPRIMIDOS"
CHI2_ESPERADO_BAJO = "CHI2_ESPERADO_BAJO"  # lo emite motor/inferencia al calcular las frecuencias esperadas

# --- Umbrales (RNF-05, RNF-06, RNF-13, Tabla 21) -------------------------------------------------------------
MIN_PERSONAS_GRUPO = 5
MIN_ESPERADO_CHI2 = 5
MIN_PUNTOS_PRONOSTICO = 12
MIN_OBS_HISTOGRAMA = 20
MAX_SECTORES_TORTA = 6
MAX_CATEGORIAS_BARRAS = 30
MIN_LADO_MAPA_CALOR = 3


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Problema(_Base):
    """Motivo por el que una spec no sigue al cálculo.

    `para`: 'usuario' = hay que repreguntarle; 'ia' = la capa de IA debe corregir la spec (error de forma).
    `opciones`: códigos de la capa semántica que sí sirven (lo que «sí existe»).
    """

    codigo: str
    paso: int
    campo: str
    mensaje: str
    para: Literal["usuario", "ia"] = "usuario"
    opciones: tuple[str, ...] = ()


class Aviso(_Base):
    codigo: str
    mensaje: str


class MetricaResuelta(_Base):
    id: str
    agregacion: Agregacion | None  # None en nivel registro (no se agrega en SQL)


class PeriodoResuelto(_Base):
    desde: date
    hasta: date


class GraficoResuelto(_Base):
    """Gráfico que se dibuja. `pedido` solo se llena cuando el tipo pedido se sustituyó (Tabla 21)."""

    tipo: TipoGrafico
    origen: OrigenGrafico
    pedido: TipoGrafico | None = None
    max_sectores: int | None = None


class SpecResuelta(_Base):
    esquema: Literal["ciumb.spec/1.0"]
    origen: Origen
    base: str | None
    metricas: tuple[MetricaResuelta, ...]
    dimensiones: tuple[DimensionSpec, ...]  # la dimensión `tiempo` siempre trae granularidad
    filtros: tuple[Filtro, ...]
    periodo: PeriodoResuelto | None  # None solo si el periodo lo da un filtro temporal (D-08)
    corte: date
    analisis: Analisis
    grafico: GraficoResuelto
    alcance: Alcance
    salida: Salida | None
    nivel: Nivel

    def granularidad(self) -> Granularidad | None:
        return next((d.granularidad for d in self.dimensiones if d.granularidad), None)

    def huella(self) -> str:
        """SHA-256 (64 hex) del JSON canónico de la spec resuelta. Va a `rpt_especificacion.huella_spec`."""
        canonico = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


class ResultadoValidacion(_Base):
    """Uno de tres (4.4.2): válida (con `spec`), corregible o fuera de alcance (con `problemas`)."""

    estado: Estado
    spec: SpecResuelta | None = None
    problemas: tuple[Problema, ...] = ()
    avisos: tuple[Aviso, ...] = ()

    @property
    def motivo(self) -> str | None:
        """Código del primer problema (para `rpt_especificacion.motivo`)."""
        return self.problemas[0].codigo if self.problemas else None
