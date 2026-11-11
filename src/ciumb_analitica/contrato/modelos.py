"""Modelos del contrato de datos `ciumb.informe/2.0.0` (sección 4.4.3, Figura 12).

INTERFAZ CERRADA (frontera con la capa de IA). BORRADOR hasta que la revise la capa de IA
(docs/decisiones.md, D-07 y D-15; docs/interfaz_capa_ia.md). Cambiar el contrato exige subir su versión
(invariante 8, DA-04) una vez aprobado.

El paquete solo lleva agregados: ni registros individuales ni datos personales (invariante 4).
- Un campo desconocido invalida el paquete (`extra="forbid"`).
- `ciumb_analitica.contrato.pii.buscar_pii` bloquea el envío si algún texto parece correo, documento o NIT.
- `alcance` NO lleva `id_usuario`: hacia la IA solo viajan el rol y, si aplica, la facultad.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ciumb_analitica.spec.modelos import PATRON_CODIGO, PATRON_PLANTILLA, Origen, OrigenGrafico, Rol, TipoGrafico

VERSION_CONTRATO = "2.0.0"
ID_CONTRATO = f"ciumb.informe/{VERSION_CONTRATO}"

PATRON_HUELLA = r"^sha256:[0-9a-f]{64}$"
PATRON_ID_ESPECIFICACION = r"^esp-[0-9]{8}-[0-9]{4}$"
PATRON_MES = r"^[0-9]{4}-(0[1-9]|1[0-2])$"

UNIDAD_PROPORCION = "proporcion"
"""Unidad de un valor entre 0 y 1 que el texto puede escribir como porcentaje (paso 3 del validador de cifras)."""

Numero = int | float
Texto = Annotated[str, Field(min_length=1, max_length=300)]
Codigo = Annotated[str, Field(pattern=PATRON_CODIGO)]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class GraficoContrato(_Base):
    """Gráfico que el usuario VE (el final). Si se sustituyó el pedido, la sección lleva una advertencia."""

    tipo: TipoGrafico
    origen: OrigenGrafico


class EspecificacionRef(_Base):
    id: Annotated[str, Field(pattern=PATRON_ID_ESPECIFICACION)]
    origen: Origen
    base: Annotated[str, Field(pattern=PATRON_PLANTILLA)] | None = None
    grafico: GraficoContrato | None = None


class PeriodoContrato(_Base):
    desde: date
    hasta: date
    corte: date

    @model_validator(mode="after")
    def _orden(self) -> PeriodoContrato:
        if self.desde > self.hasta:
            raise ValueError("periodo.desde no puede ser posterior a periodo.hasta")
        return self


class AlcanceContrato(_Base):
    rol: Rol
    facultad: Annotated[str, Field(min_length=1, max_length=150)] | None = None


class Indicador(_Base):
    """Una cifra del informe. Todos los campos numéricos son cifras admitidas por el validador de cifras."""

    id: Codigo
    valor: Numero = Field(description="Valor calculado, sin redondear para presentación.")
    anterior: Numero | None = Field(default=None, description="Valor del periodo de comparación.")
    variacion_pct: Numero | None = Field(default=None, description="Variación porcentual frente a `anterior`.")
    unidad: Annotated[str, Field(min_length=1, max_length=40)] | None = Field(
        default=None, description="P. ej. 'millones COP', '%', 'dias'. 'proporcion' = valor entre 0 y 1."
    )
    n: Annotated[int, Field(ge=0)] | None = Field(default=None, description="Tamaño de la muestra.")
    meta: Numero | None = None
    metodo: Texto | None = Field(default=None, description="Si existe, reemplaza al `metodo` de la sección (D-07).")
    mes: Annotated[str, Field(pattern=PATRON_MES)] | None = Field(
        default=None, description="Mes al que corresponde el valor (AAAA-MM), como en la Figura 12."
    )
    grupo: dict[Codigo, Texto] | None = Field(
        default=None, description="Categoría del valor: código de dimensión -> etiqueta (p. ej. facultad)."
    )
    valor_p: Annotated[float, Field(ge=0, le=1)] | None = Field(default=None, description="Valor p de la prueba.")
    ic_inferior: Numero | None = Field(default=None, description="Límite inferior del intervalo de confianza.")
    ic_superior: Numero | None = Field(default=None, description="Límite superior del intervalo de confianza.")


class Seccion(_Base):
    id: Codigo
    indicadores: Annotated[list[Indicador], Field(min_length=1, max_length=200)]
    metodo: Texto = Field(description="Método de la sección; un indicador puede reemplazarlo con el suyo (D-07).")
    advertencias: Annotated[list[Texto], Field(max_length=20)] = []

    @model_validator(mode="after")
    def _ids_unicos(self) -> Seccion:
        claves = [(i.id, i.mes, tuple(sorted((i.grupo or {}).items()))) for i in self.indicadores]
        if len(claves) != len(set(claves)):
            raise ValueError(f"la sección '{self.id}' repite un indicador (mismo id, mes y grupo)")
        return self


class Contrato(_Base):
    """Paquete `ciumb.informe/2.0.0` que el área analítica entrega a la capa de IA."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, title="ciumb.informe/2.0.0")

    contrato: Literal["ciumb.informe/2.0.0"]
    especificacion: EspecificacionRef
    periodo: PeriodoContrato
    alcance: AlcanceContrato
    secciones: Annotated[list[Seccion], Field(min_length=1, max_length=30)]
    huella_datos: Annotated[str, Field(pattern=PATRON_HUELLA)] = Field(
        description="sha256 de los datos agregados del informe (D-15). Sin nombres, documentos, correos ni NIT."
    )

    @model_validator(mode="after")
    def _secciones_unicas(self) -> Contrato:
        ids = [s.id for s in self.secciones]
        if len(ids) != len(set(ids)):
            raise ValueError("'secciones' tiene identificadores repetidos")
        return self


def cargar_contrato(datos: dict) -> Contrato:
    """Valida un dict contra el contrato 2.0.0 (esquema + PII). Lanza `ValidationError` o `ErrorPII`.

    Es la única puerta de salida hacia la capa de IA: el empaquetador debe terminar llamándola.
    """
    from ciumb_analitica.contrato.pii import ErrorPII, buscar_pii

    contrato = Contrato.model_validate_json(json.dumps(datos))
    hallazgos = buscar_pii(datos)
    if hallazgos:
        raise ErrorPII(hallazgos)
    return contrato
