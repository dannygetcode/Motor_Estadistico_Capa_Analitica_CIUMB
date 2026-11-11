"""Modelos de la especificación de informe `ciumb.spec/1.0` (Tabla 20, sección 4.4.2).

INTERFAZ CERRADA (frontera con la capa de IA). BORRADOR hasta que la revise la capa de IA
(ver docs/decisiones.md, D-06 a D-08, y docs/interfaz_capa_ia.md). No cambiar sin aprobación de Daniel.

Reglas generales:
- Un campo desconocido invalida la especificación (paso 1 del validador): todos los modelos usan `extra="forbid"`.
- Los tipos son estrictos: `"5"` no es un entero y `1` no es un booleano.
- Los identificadores (`id`, `campo`, `variables`) son códigos de la capa semántica publicada en GET /semantica:
  minúsculas, dígitos y guion bajo. Aquí solo se valida su forma; su existencia la revisa el validador (paso 2).
- El JSON Schema exportado vive en `schemas/ciumb.spec-1.0.schema.json` (se regenera con
  `uv run python -m ciumb_analitica.exportar_esquemas`).
"""

from __future__ import annotations

import json
from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr, model_validator

ESQUEMA_SPEC = "ciumb.spec/1.0"

PATRON_CODIGO = r"^[a-z][a-z0-9_]{0,59}$"
PATRON_PLANTILLA = r"^INF-[A-Z]{3}-[0-9]{2}$"

Codigo = Annotated[str, Field(pattern=PATRON_CODIGO, description="Código de la capa semántica (GET /semantica).")]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Origen(StrEnum):
    PROMPT = "prompt"
    PLANTILLA_BASE = "plantilla_base"
    GUARDADA = "guardada"


class Agregacion(StrEnum):
    CONTEO = "conteo"
    SUMA = "suma"
    PROMEDIO = "promedio"
    MEDIANA = "mediana"
    RAZON = "razon"


class Granularidad(StrEnum):
    MES = "mes"
    TRIMESTRE = "trimestre"
    SEMESTRE = "semestre"
    ANIO = "anio"


class TipoGrafico(StrEnum):
    BARRAS = "barras"
    LINEAS = "lineas"
    TORTA = "torta"
    DISPERSION = "dispersion"
    MAPA_CALOR = "mapa_calor"
    HISTOGRAMA = "histograma"


class OrigenGrafico(StrEnum):
    PROMPT = "prompt"
    RECOMENDADO = "recomendado"


class Rol(StrEnum):
    DIRECTIVO = "directivo"
    COORDINADOR = "coordinador"
    TUTOR = "tutor"
    CONSULTOR = "consultor"
    ADMINISTRADOR = "administrador"


class Formato(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    XLSX = "xlsx"
    HTML = "html"
    CSV = "csv"


class Operador(StrEnum):
    IGUAL = "="
    DISTINTO = "!="
    MAYOR = ">"
    MAYOR_IGUAL = ">="
    MENOR = "<"
    MENOR_IGUAL = "<="
    EN = "en"
    ENTRE = "entre"


class MetricaSpec(_Base):
    id: Codigo
    agregacion: Agregacion | None = Field(
        default=None, description="Si se omite, se usa la agregación por defecto de la métrica en la capa semántica."
    )


class DimensionSpec(_Base):
    id: Codigo
    granularidad: Granularidad | None = Field(
        default=None, description="Solo para dimensiones temporales (p. ej. `tiempo`). Por defecto, `mes`."
    )


Escalar = StrictStr | StrictInt | StrictFloat | StrictBool


class Filtro(_Base):
    """Condición `campo op valor` sobre una dimensión permitida. El valor siempre viaja como parámetro SQL."""

    campo: Codigo
    op: Operador
    valor: Escalar | Annotated[list[Escalar], Field(min_length=1, max_length=100)]

    @model_validator(mode="after")
    def _forma_del_valor(self) -> Filtro:
        es_lista = isinstance(self.valor, list)
        if self.op is Operador.EN and not es_lista:
            raise ValueError("el operador 'en' exige una lista de valores")
        if self.op is Operador.ENTRE and not (es_lista and len(self.valor) == 2):
            raise ValueError("el operador 'entre' exige una lista de dos valores [desde, hasta]")
        if self.op not in (Operador.EN, Operador.ENTRE) and es_lista:
            raise ValueError(f"el operador '{self.op.value}' exige un único valor")
        return self


class Periodo(_Base):
    """Opcional (D-08). Un filtro sobre una dimensión temporal también cuenta como periodo."""

    desde: date
    hasta: date
    corte: date | None = Field(default=None, description="Fecha de corte de los datos. Por defecto, `hasta`.")

    @model_validator(mode="after")
    def _orden(self) -> Periodo:
        if self.desde > self.hasta:
            raise ValueError("periodo.desde no puede ser posterior a periodo.hasta")
        return self


# --- analisis: unión discriminada por `metodo` ---------------------------------------------------------------


class ReglaAtipicos(_Base):
    """Regla de atípicos anidada en `descriptiva` (Figura 15)."""

    metodo: Literal["RIC", "puntaje_z"] = "RIC"
    k: float = Field(default=1.5, gt=0, le=10, strict=False, description="RIC: múltiplo del rango; Z: umbral.")


class AnalisisFrecuencias(_Base):
    metodo: Literal["frecuencias"]
    relativas: bool = False


class AnalisisDescriptiva(_Base):
    metodo: Literal["descriptiva"]
    atipicos: ReglaAtipicos | None = None


class AnalisisSerie(_Base):
    metodo: Literal["serie"]
    acumulado: bool = False


class AnalisisVariacion(_Base):
    """`variacion`: frente al periodo inmediatamente anterior. `variacion_interanual`: frente al mismo
    periodo del año anterior (Figura 10)."""

    metodo: Literal["variacion", "variacion_interanual"]


class AnalisisPrueba(_Base):
    """Correlación o prueba de hipótesis (RF-04).

    `variables` son dos códigos de la capa semántica y NO tienen que estar en `dimensiones` (D-06):
    - pearson, spearman: dos métricas numéricas.
    - chi_cuadrado: dos dimensiones categóricas.
    - t_student, mann_whitney: [métrica numérica, dimensión con exactamente dos grupos].
    """

    metodo: Literal["pearson", "spearman", "chi_cuadrado", "t_student", "mann_whitney"]
    variables: Annotated[list[Codigo], Field(min_length=2, max_length=2)]
    alfa: float = Field(default=0.05, gt=0, lt=1, strict=False)

    @model_validator(mode="after")
    def _distintas(self) -> AnalisisPrueba:
        if self.variables[0] == self.variables[1]:
            raise ValueError("analisis.variables debe tener dos variables distintas")
        return self


class AnalisisAtipicos(_Base):
    metodo: Literal["atipicos"]
    tecnica: Literal["RIC", "puntaje_z"] = "RIC"
    k: float = Field(default=1.5, gt=0, le=10, strict=False)


class AnalisisPronostico(_Base):
    """Exige una dimensión temporal y al menos 12 puntos (RNF-13)."""

    metodo: Literal["pronostico"]
    tecnica: Literal["holt", "regresion_lineal"] = "holt"
    horizonte: int = Field(default=2, ge=1, le=12, description="Periodos a pronosticar, en la granularidad pedida.")
    nivel_confianza: float = Field(default=0.95, gt=0.5, lt=1, strict=False)


class AnalisisSegmentacion(_Base):
    metodo: Literal["segmentacion"]
    tecnica: Literal["kmedias"] = "kmedias"
    k: int | None = Field(default=None, ge=2, le=10, description="Si se omite, se elige por silueta.")


Analisis = Annotated[
    AnalisisFrecuencias
    | AnalisisDescriptiva
    | AnalisisSerie
    | AnalisisVariacion
    | AnalisisPrueba
    | AnalisisAtipicos
    | AnalisisPronostico
    | AnalisisSegmentacion,
    Field(discriminator="metodo"),
]

METODOS_ANALISIS: tuple[str, ...] = (
    "frecuencias",
    "descriptiva",
    "serie",
    "variacion",
    "variacion_interanual",
    "pearson",
    "spearman",
    "chi_cuadrado",
    "t_student",
    "mann_whitney",
    "atipicos",
    "pronostico",
    "segmentacion",
)


class GraficoSpec(_Base):
    """Si el prompt no menciona un tipo, la capa de IA omite `grafico` y lo elige el recomendador (Tabla 21)."""

    tipo: TipoGrafico
    origen: OrigenGrafico = OrigenGrafico.PROMPT
    max_sectores: int | None = Field(default=None, ge=2, le=6, description="Solo torta. Máximo 6 (Tabla 21).")
    reemplaza: Annotated[str, Field(pattern=r"^[a-z_]{1,30}$")] | None = Field(
        default=None, description="Tipo de la plantilla base que este gráfico reemplaza (informativo)."
    )


class Alcance(_Base):
    """Lo agrega el backend del CIUMB, nunca la IA (RF-21). BORRADOR: forma por confirmar con integración.

    - directivo, administrador: todo el centro.
    - coordinador: exige `facultad`.
    - tutor, consultor: exigen `id_usuario` (id de origen; el servicio lo seudonimiza y nunca lo envía a la IA).
    """

    rol: Rol
    facultad: Annotated[str, Field(min_length=1, max_length=150)] | None = None
    id_usuario: Annotated[int, Field(ge=1)] | None = None

    @model_validator(mode="after")
    def _coherencia(self) -> Alcance:
        if self.rol is Rol.COORDINADOR and self.facultad is None:
            raise ValueError("el rol coordinador exige alcance.facultad")
        if self.rol in (Rol.TUTOR, Rol.CONSULTOR) and self.id_usuario is None:
            raise ValueError(f"el rol {self.rol.value} exige alcance.id_usuario")
        return self


class Salida(_Base):
    formatos: Annotated[list[Formato], Field(max_length=5)] = []
    secciones: Annotated[list[Codigo], Field(max_length=20)] = []


class Especificacion(_Base):
    """Especificación de informe `ciumb.spec/1.0`. Única entrada del área analítica."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, title="ciumb.spec/1.0")

    esquema: Literal["ciumb.spec/1.0"]
    origen: Origen
    base: Annotated[str, Field(pattern=PATRON_PLANTILLA)] | None = Field(
        default=None, description="Código INF de la plantilla base, si se usó."
    )
    metricas: Annotated[list[MetricaSpec], Field(min_length=1, max_length=5)]
    dimensiones: Annotated[list[DimensionSpec], Field(max_length=3)] = Field(
        default=[], description="Agrupación del gráfico. Vacía: se calcula el total."
    )
    filtros: Annotated[list[Filtro], Field(max_length=20)] = []
    periodo: Periodo | None = None
    analisis: Analisis | None = Field(default=None, description="Si se omite: descriptiva.")
    grafico: GraficoSpec | None = Field(default=None, description="Si se omite: lo elige el recomendador.")
    alcance: Alcance
    salida: Salida | None = None

    @model_validator(mode="after")
    def _coherencia(self) -> Especificacion:
        if self.origen is Origen.PLANTILLA_BASE and self.base is None:
            raise ValueError("origen 'plantilla_base' exige el código INF en 'base'")
        for nombre, ids in (
            ("metricas", [m.id for m in self.metricas]),
            ("dimensiones", [d.id for d in self.dimensiones]),
        ):
            if len(ids) != len(set(ids)):
                raise ValueError(f"'{nombre}' tiene identificadores repetidos")
        return self


def cargar_especificacion(datos: dict) -> Especificacion:
    """Valida un dict (JSON ya decodificado) contra `ciumb.spec/1.0`. Lanza `pydantic.ValidationError`.

    Se valida en modo JSON estricto: los enumerados y las fechas llegan como texto, pero no hay coerción
    entre tipos (`"5"` no es entero). Usar siempre esta función, no `Especificacion.model_validate`.
    """
    return Especificacion.model_validate_json(json.dumps(datos))
