"""Seudonimización de identificadores de personas (Tabla 13, invariante 5).

Seudónimo = SHA-256 del id de origen con una sal guardada como secreto del servicio (`SAL_SEUDONIMIZACION`).
Lo usan el ETL (al cargar `dim_persona_rol`, `hecho_practica.seudonimo_estudiante`, `rpt_solicitud.id_usuario`)
y el compilador (para restringir el alcance de un tutor o consultor sin exponer su id).
"""

from __future__ import annotations

import hashlib
import os

VARIABLE_SAL = "SAL_SEUDONIMIZACION"
LONGITUD_MINIMA_SAL = 16


class SalNoConfigurada(RuntimeError):  # noqa: N818 - nombre de dominio en español
    pass


def sal_del_entorno() -> str:
    """Lee la sal de la variable de entorno. Lanza `SalNoConfigurada` si falta o es demasiado corta."""
    return _exigir(os.environ.get(VARIABLE_SAL))


def _exigir(sal: str | None) -> str:
    if not sal or len(sal) < LONGITUD_MINIMA_SAL:
        raise SalNoConfigurada(
            f"Defina {VARIABLE_SAL} (al menos {LONGITUD_MINIMA_SAL} caracteres) como secreto del servicio."
        )
    return sal


def seudonimizar(id_origen: int | str, sal: str) -> str:
    """Devuelve el seudónimo (64 caracteres hexadecimales) del id de una persona. Determinista para una sal dada."""
    return hashlib.sha256(f"{_exigir(sal)}:{id_origen}".encode()).hexdigest()


def hash_nit(nit: str, sal: str) -> str:
    """Hash del NIT normalizado (solo dígitos), para detectar duplicados sin guardar el NIT (INF-TRA-08)."""
    digitos = "".join(c for c in str(nit) if c.isdigit())
    return hashlib.sha256(f"{_exigir(sal)}:nit:{digitos}".encode()).hexdigest()
