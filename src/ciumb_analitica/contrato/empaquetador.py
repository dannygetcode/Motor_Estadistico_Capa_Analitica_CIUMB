"""Empaquetador del contrato de datos `ciumb.informe/2.0.0` (sección 4.4.3, Figura 12, DA-04, OE4).

Toma lo que calcularon el motor y ML y arma el paquete para la capa de IA. Es la última barrera de privacidad
(invariante 4): solo agregados, cero PII, sin dimensiones internas.
Pruebas: `tests/contrato/test_empaquetador.py`.
"""

from __future__ import annotations

from datetime import date

from ciumb_analitica.contrato.modelos import Contrato
from ciumb_analitica.motor.resultado import PENDIENTE, SeccionCalculada
from ciumb_analitica.semantica.modelos import CapaSemantica
from ciumb_analitica.spec.resultado import GraficoResuelto, SpecResuelta


class DimensionNoExportable(ValueError):  # noqa: N818 - nombre de dominio en español
    """Un indicador viene agrupado por una dimensión que no puede viajar a la IA (empresa, macroproyecto) o
    que identifica personas."""


def id_especificacion(fecha: date, consecutivo: int) -> str:
    """Identificador `esp-AAAAMMDD-NNNN` (p. ej. esp-20261105-0042). `consecutivo` entre 1 y 9999."""
    raise NotImplementedError(PENDIENTE)


def empaquetar(
    spec: SpecResuelta,
    grafico: GraficoResuelto,
    secciones: list[SeccionCalculada],
    *,
    capa: CapaSemantica,
    id_spec: str,
    huella_datos: str,
    periodo_datos: tuple[date, date] | None = None,
) -> Contrato:
    """Arma y valida el paquete.

    Entradas:
      spec, grafico: spec resuelta y gráfico FINAL (`RevisionDatos.grafico`): el contrato describe lo que el
        usuario ve.
      secciones: salida del motor (`SeccionCalculada`), con las advertencias de `validar` y `revisar_datos`
        ya incluidas como texto.
      id_spec: de `id_especificacion`. huella_datos: 64 hex de `compilador.huella_datos` (aquí se le antepone
        `sha256:`, D-15).
      periodo_datos: (desde, hasta) reales de los datos; obligatorio si `spec.periodo` es None (D-21).
    Reglas:
      - `periodo` = spec.periodo (o periodo_datos) + `corte` = spec.corte.
      - `alcance` = solo rol y facultad; nunca `id_usuario`.
      - Si algún indicador trae en `grupo` una dimensión con `viaja_a_ia = False` o `identifica_persona`,
        lanza `DimensionNoExportable` (no la quita en silencio: es un defecto de quien armó la sección).
      - Los valores numéricos se redondean a 6 decimales (sin formato de presentación). NaN e infinito no se
        envían: el indicador se omite y se agrega una advertencia a su sección.
      - Termina SIEMPRE en `contrato.modelos.cargar_contrato`, que valida el esquema y aplica el filtro de
        PII (`ErrorPII` bloquea el envío).
    Salida: `Contrato` listo para serializar con `model_dump(mode="json", exclude_none=True)`.
    """
    raise NotImplementedError(PENDIENTE)
