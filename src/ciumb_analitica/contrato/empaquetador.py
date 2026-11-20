"""Empaquetador del contrato de datos `ciumb.informe/2.0.0` (sección 4.4.3, Figura 12, DA-04, OE4).

Toma lo que calcularon el motor y ML y arma el paquete para la capa de IA. Es la última barrera de privacidad
(invariante 4): solo agregados, cero PII, sin dimensiones internas.
Pruebas: `tests/contrato/test_empaquetador.py`.
"""

from __future__ import annotations

import math
import re
from datetime import date

import numpy as np

from ciumb_analitica.contrato.modelos import ID_CONTRATO, Contrato, cargar_contrato
from ciumb_analitica.motor.resultado import SeccionCalculada
from ciumb_analitica.semantica.modelos import CapaSemantica
from ciumb_analitica.spec.resultado import GraficoResuelto, SpecResuelta

DECIMALES = 6
CAMPOS_NUMERICOS = ("valor", "anterior", "variacion_pct", "meta", "valor_p", "ic_inferior", "ic_superior")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class DimensionNoExportable(ValueError):  # noqa: N818 - nombre de dominio en español
    """Un indicador viene agrupado por una dimensión que no puede viajar a la IA (empresa, macroproyecto) o
    que identifica personas."""


def id_especificacion(fecha: date, consecutivo: int) -> str:
    """Identificador `esp-AAAAMMDD-NNNN` (p. ej. esp-20261105-0042). `consecutivo` entre 1 y 9999."""
    if not 1 <= consecutivo <= 9999:
        raise ValueError(f"el consecutivo de la especificación debe estar entre 1 y 9999; llegó {consecutivo}")
    return f"esp-{fecha:%Y%m%d}-{consecutivo:04d}"


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
    if not _HEX64.match(huella_datos or ""):
        raise ValueError("huella_datos debe ser el SHA-256 completo (64 caracteres hexadecimales en minúscula)")
    if spec.periodo is not None:
        desde, hasta = spec.periodo.desde, spec.periodo.hasta
    elif periodo_datos is not None:
        desde, hasta = periodo_datos
    else:
        raise ValueError("la spec no trae periodo (lo da un filtro temporal): pase periodo_datos con el rango real")

    especificacion: dict = {
        "id": id_spec,
        "origen": spec.origen.value,
        "grafico": {"tipo": grafico.tipo.value, "origen": grafico.origen.value},
    }
    if spec.base:
        especificacion["base"] = spec.base
    alcance: dict = {"rol": spec.alcance.rol.value}
    if spec.alcance.facultad:
        alcance["facultad"] = spec.alcance.facultad

    paquete = {
        "contrato": ID_CONTRATO,
        "especificacion": especificacion,
        "periodo": {"desde": desde.isoformat(), "hasta": hasta.isoformat(), "corte": spec.corte.isoformat()},
        "alcance": alcance,
        "secciones": [_seccion(s, capa) for s in secciones],
        "huella_datos": f"sha256:{huella_datos}",
    }
    return cargar_contrato(paquete)


def _a_python(valor):
    """Tipos de NumPy a tipos nativos (el contrato es estricto y se serializa a JSON)."""
    if isinstance(valor, np.bool_):
        return bool(valor)
    if isinstance(valor, np.integer):
        return int(valor)
    if isinstance(valor, np.floating):
        return float(valor)
    return valor


def _seccion(seccion: SeccionCalculada, capa: CapaSemantica) -> dict:
    indicadores: list[dict] = []
    omitidos: list[str] = []
    for original in seccion.indicadores:
        indicador = {k: _a_python(v) for k, v in original.items() if v is not None}
        _revisar_grupo(indicador.get("grupo"), capa, seccion.id)
        if any(isinstance(indicador.get(c), float) and not math.isfinite(indicador[c]) for c in CAMPOS_NUMERICOS):
            omitidos.append(str(indicador.get("id")))
            continue
        for campo in CAMPOS_NUMERICOS:
            if isinstance(indicador.get(campo), float):
                indicador[campo] = round(indicador[campo], DECIMALES)
        if "grupo" in indicador:
            indicador["grupo"] = {str(k): str(v) for k, v in indicador["grupo"].items()}
        indicadores.append(indicador)
    advertencias = list(seccion.advertencias)
    if omitidos:
        advertencias.append(
            f"Se omitieron {len(omitidos)} indicador(es) sin valor definido (NaN o infinito): {', '.join(omitidos)}."
        )
    return {"id": seccion.id, "indicadores": indicadores, "metodo": seccion.metodo, "advertencias": advertencias}


def _revisar_grupo(grupo: dict | None, capa: CapaSemantica, seccion: str) -> None:
    for codigo in grupo or {}:
        dimension = capa.dimensiones.get(codigo)
        if dimension is not None and (not dimension.viaja_a_ia or dimension.identifica_persona):
            raise DimensionNoExportable(
                f"la sección '{seccion}' agrupa por '{codigo}', una dimensión que no puede viajar a la capa de IA"
            )
