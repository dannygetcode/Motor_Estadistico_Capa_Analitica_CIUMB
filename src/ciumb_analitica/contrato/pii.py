"""Filtro de PII del contrato (sección 4.4.3; invariante 4; RNF-05, RNF-06).

Una lista de patrones (correos, números de documento, NIT) bloquea el envío hacia la capa de IA si aparece
alguno en CUALQUIER texto del paquete (claves y valores). Los números JSON no se revisan: son agregados.

La capa de IA aplica la misma lista al prompt antes de enviarlo a un proveedor (4.4.1): `PATRONES_PII` es la
lista compartida.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

PATRONES_PII: dict[str, re.Pattern[str]] = {
    "correo": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    # NIT colombiano: 9 dígitos (con o sin puntos de miles) y dígito de verificación.
    "nit": re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}\s?-\s?\d(?!\d)"),
    # Documento de identidad: 6 a 10 dígitos seguidos, o con puntos de miles (1.023.456.789).
    "documento": re.compile(r"(?<![\d.,-])(?:\d{6,10}|\d{1,3}(?:\.\d{3}){2,3})(?![\d.,-]|\s?%)"),
}

# Textos del contrato que tienen 6+ dígitos y no son PII: se validan por su propio patrón en el modelo.
_CAMPOS_EXENTOS = {"huella_datos", "id"}


@dataclass(frozen=True)
class HallazgoPII:
    ruta: str
    patron: str


class ErrorPII(Exception):  # noqa: N818 - nombre de dominio en español
    """El paquete contiene texto con forma de dato personal. El envío a la capa de IA queda bloqueado."""

    def __init__(self, hallazgos: list[HallazgoPII]):
        self.hallazgos = hallazgos
        # El mensaje nombra la ruta y el patrón, nunca el valor.
        super().__init__("; ".join(f"{h.ruta}: {h.patron}" for h in hallazgos))


def _revisar_texto(texto: str, ruta: str, salida: list[HallazgoPII]) -> None:
    for nombre, patron in PATRONES_PII.items():
        if patron.search(texto):
            salida.append(HallazgoPII(ruta=ruta, patron=nombre))


def buscar_pii(datos: Any, ruta: str = "$") -> list[HallazgoPII]:
    """Recorre un JSON decodificado y devuelve los textos con forma de correo, documento o NIT.

    Entradas: dict/list/escalares. Salida: lista de hallazgos (vacía = se puede enviar).
    Exenciones: `huella_datos` y los `id` (su forma ya la fija el esquema del contrato).
    """
    hallazgos: list[HallazgoPII] = []
    if isinstance(datos, dict):
        for clave, valor in datos.items():
            sub = f"{ruta}.{clave}"
            _revisar_texto(str(clave), f"{sub} (clave)", hallazgos)
            if clave in _CAMPOS_EXENTOS and isinstance(valor, str):
                continue
            hallazgos.extend(buscar_pii(valor, sub))
    elif isinstance(datos, list):
        for i, valor in enumerate(datos):
            hallazgos.extend(buscar_pii(valor, f"{ruta}[{i}]"))
    elif isinstance(datos, str):
        _revisar_texto(datos, ruta, hallazgos)
    return hallazgos


def depurar_texto(texto: str, marca: str = "[dato retirado]") -> str:
    """Reemplaza por `marca` todo lo que coincida con `PATRONES_PII` (uso: depurar el prompt del usuario)."""
    for patron in PATRONES_PII.values():
        texto = patron.sub(marca, texto)
    return texto
