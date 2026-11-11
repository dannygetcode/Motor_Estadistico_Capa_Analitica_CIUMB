"""Gramática cerrada de `rpt_metrica.expresion_sql`.

La expresión de una métrica NO es SQL libre: es una de tres formas, y sus nombres de columna se resuelven
contra las tablas de `ana_` (lista blanca, invariante 2). Así un registro nuevo en `rpt_metrica` (RF-22) no
puede introducir SQL arbitrario.

    *                       conteo de filas del hecho
    columna                 medida que se agrega con suma, promedio o mediana
    [100 * ] num / den      razón: SUM(num) / SUM(den); `den` puede ser `*` (número de filas)

Una razón nunca se suma ni se promedia entre grupos: siempre se recalcula desde sus componentes (4.4.2, paso 3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_COL = r"[a-z][a-z0-9_]{0,59}"
_RE_COLUMNA = re.compile(rf"^{_COL}$")
_RE_RAZON = re.compile(rf"^(?:(?P<factor>100)\s*\*\s*)?(?P<num>{_COL})\s*/\s*(?P<den>{_COL}|\*)$")


class ExpresionInvalida(ValueError):
    pass


@dataclass(frozen=True)
class Expresion:
    """`tipo`: 'conteo' | 'columna' | 'razon'. En una razón, `denominador=None` significa número de filas."""

    tipo: str
    columna: str | None = None
    numerador: str | None = None
    denominador: str | None = None
    factor: int = 1

    @property
    def columnas(self) -> tuple[str, ...]:
        return tuple(c for c in (self.columna, self.numerador, self.denominador) if c)


def analizar(texto: str) -> Expresion:
    """Convierte el texto de `expresion_sql` en una `Expresion`. Lanza `ExpresionInvalida`."""
    texto = texto.strip()
    if texto == "*":
        return Expresion(tipo="conteo")
    if _RE_COLUMNA.match(texto):
        return Expresion(tipo="columna", columna=texto)
    razon = _RE_RAZON.match(texto)
    if razon:
        den = razon["den"]
        return Expresion(
            tipo="razon",
            numerador=razon["num"],
            denominador=None if den == "*" else den,
            factor=100 if razon["factor"] else 1,
        )
    raise ExpresionInvalida(f"expresión fuera de la gramática permitida: {texto!r}")
