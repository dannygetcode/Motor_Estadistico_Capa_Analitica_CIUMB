"""Pasos 1 y 2 del validador de cifras (sección 4.4.3): extraer los números del texto y descartar los que no
son cifras del análisis.

Formato español: coma decimal (`412,6`), punto de miles (`1.250.000`), porcentaje (`13 %`, `13%`,
`13 por ciento`) y signo (`-3,2`, `−3,2`). Un punto seguido de un grupo que no es de tres dígitos se lee como
punto decimal (`58.3`), por si el modelo escribe en formato inglés.

No son cifras del análisis (paso 2):
- fechas: `2026-10-31`, `31/10/2026`, `31 de octubre`, `octubre de 2026`, meses `2026-06`;
- periodos académicos: `2026-2`;
- años: enteros de cuatro dígitos entre 1900 y 2100, sin signo, sin separador de miles y sin `%`;
- códigos: `INF-INV-02`, `T3`, `P4`, `esp-20261105-0042`;
- ordinales: `1.º`, `2.ª`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

_MESES = "enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre"

_RE_NUMERO = re.compile(
    r"""
    (?<![\w.,])                              # no pegado a una palabra, a otro número ni a un código (T3, v2)
    (?P<signo>(?<![\w)\]])[-−])?             # signo solo si no es un guion entre palabras o números (2025-2026)
    (?P<num>
        \d{1,3}(?:\.\d{3})+(?:,\d+)?         # 1.250  1.250.000,75
      | \d+,\d+                              # 412,6
      | \d+\.\d+                             # 58.3 (punto decimal)
      | \d+
    )
    (?![\d]|[.,]\d)                          # el número termina aquí
    (?P<pct>\s?(?:%|por\s+ciento\b))?
    """,
    re.VERBOSE,
)

# Tramos del texto cuyos números no son cifras del análisis.
_NO_CIFRAS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("fecha", re.compile(r"\b\d{4}-\d{2}-\d{2}\b")),
    ("fecha", re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")),
    ("fecha", re.compile(rf"\b\d{{1,2}}\s+de\s+(?:{_MESES})\b(?:\s+(?:de|del)\s+\d{{4}}\b)?", re.I)),
    ("fecha", re.compile(rf"\b(?:{_MESES})\s+(?:de|del)\s+\d{{4}}\b", re.I)),
    ("fecha", re.compile(r"\b(?:19|20)\d{2}-(?:0[1-9]|1[0-2])\b(?!-)")),
    ("periodo", re.compile(r"\b(?:19|20)\d{2}-[12]\b(?![\d-])")),
    ("codigo", re.compile(r"\b[A-Za-z]{2,}(?:-[A-Za-z0-9]+)+\b")),
    ("ordinal", re.compile(r"\b\d+\s?\.?[ºª°]")),
)

ANIO_MINIMO, ANIO_MAXIMO = 1900, 2100


@dataclass(frozen=True)
class CifraTexto:
    """Un número encontrado en el texto.

    texto: tal como aparece (`"1.250,5 %"`). valor: su valor numérico. decimales: decimales mostrados.
    es_porcentaje: lleva `%` o «por ciento». con_signo: lleva signo negativo explícito.
    inicio/fin: posición en el texto. descartada: motivo del paso 2 (`None` si es una cifra del análisis).
    """

    texto: str
    valor: Decimal
    decimales: int
    es_porcentaje: bool
    con_signo: bool
    inicio: int
    fin: int
    descartada: str | None = None

    @property
    def tolerancia(self) -> Decimal:
        """Media unidad del último decimal mostrado (paso 4)."""
        return Decimal(5).scaleb(-(self.decimales + 1))


def _interpretar(num: str) -> tuple[Decimal, int, bool]:
    """Devuelve (valor, decimales mostrados, tiene separador de miles)."""
    if "," in num:
        entero, decimal = num.split(",")
        return Decimal(entero.replace(".", "") + "." + decimal), len(decimal), "." in entero
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", num):
        return Decimal(num.replace(".", "")), 0, True
    if "." in num:
        return Decimal(num), len(num.split(".")[1]), False
    return Decimal(num), 0, False


def extraer_cifras(texto: str) -> list[CifraTexto]:
    """Pasos 1 y 2. Devuelve todos los números del texto en orden; los que no son cifras del análisis llevan
    el motivo en `descartada`."""
    tramos = [(motivo, m.start(), m.end()) for motivo, patron in _NO_CIFRAS for m in patron.finditer(texto)]
    cifras = []
    for m in _RE_NUMERO.finditer(texto):
        valor, decimales, con_miles = _interpretar(m["num"])
        con_signo = m["signo"] is not None
        es_pct = m["pct"] is not None
        inicio, fin = m.start(), m.end()
        inicio_num, fin_num = m.start("num"), m.end("num")
        motivo = next((mot for mot, a, b in tramos if inicio_num < b and fin_num > a), None)
        if (
            motivo is None
            and decimales == 0
            and not con_miles
            and not es_pct
            and not con_signo
            and len(m["num"]) == 4
            and ANIO_MINIMO <= valor <= ANIO_MAXIMO
        ):
            motivo = "anio"
        cifras.append(
            CifraTexto(
                texto=texto[inicio:fin].strip(),
                valor=-valor if con_signo else valor,
                decimales=decimales,
                es_porcentaje=es_pct,
                con_signo=con_signo,
                inicio=inicio,
                fin=fin,
                descartada=motivo,
            )
        )
    return cifras


def formatear_numero(valor: float | int, decimales: int | None = None) -> str:
    """Número en formato español: punto de miles y coma decimal. Sin `decimales`, usa 0, 1 o 2 según el valor."""
    if decimales is None:
        d = Decimal(str(valor))
        decimales = 0 if d == d.to_integral_value() else (1 if d * 10 == (d * 10).to_integral_value() else 2)
    texto = f"{valor:,.{decimales}f}"
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
