"""Generación por código de `dim_tiempo` para 2015 a 2030 (Tabla 16)."""

from __future__ import annotations

from datetime import date, timedelta

ANIO_INICIAL = 2015
ANIO_FINAL = 2030

NOMBRES_MES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)  # fmt: skip


def sk_fecha(d: date) -> int:
    """Clave sustituta de una fecha: entero AAAAMMDD."""
    return d.year * 10000 + d.month * 100 + d.day


def fila_tiempo(d: date) -> dict:
    semestre = 1 if d.month <= 6 else 2
    return {
        "sk_fecha": sk_fecha(d),
        "fecha": d,
        "dia": d.day,
        "mes": d.month,
        "nombre_mes": NOMBRES_MES[d.month - 1],
        "trimestre": (d.month - 1) // 3 + 1,
        "semestre": semestre,
        "anio": d.year,
        "periodo_academico": f"{d.year}-{semestre}",
    }


def filas_dim_tiempo(desde: date | None = None, hasta: date | None = None) -> list[dict]:
    """Una fila por día entre `desde` y `hasta` (por defecto, 2015-01-01 a 2030-12-31)."""
    d = desde or date(ANIO_INICIAL, 1, 1)
    fin = hasta or date(ANIO_FINAL, 12, 31)
    filas = []
    while d <= fin:
        filas.append(fila_tiempo(d))
        d += timedelta(days=1)
    return filas


def fin_de_mes(d: date) -> date:
    siguiente = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return siguiente - timedelta(days=1)


def ultimo_mes_cerrado(hoy: date) -> date:
    """Último día del último mes calendario completo anterior a `hoy`."""
    return date(hoy.year, hoy.month, 1) - timedelta(days=1)
