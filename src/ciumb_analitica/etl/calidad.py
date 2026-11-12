"""Reglas de calidad del ETL (sección 4.2.2; INF-TRA-08).

Los registros que fallan una regla NO se descartan: se cargan con `marca_calidad` (códigos separados por coma)
y se registran en `ana_.etl_marca_calidad`, para que el área responsable los corrija en el origen.
Pruebas: `tests/etl/test_calidad.py` (contra los defectos exactos de `datos_sinteticos.generar`).
"""

from __future__ import annotations

import pandas as pd

from ciumb_analitica.motor.resultado import PENDIENTE

FIN_ANTES_DE_INICIO = "fin_antes_de_inicio"
PRESUPUESTO_NEGATIVO = "presupuesto_negativo"
ESTADO_FUERA_DE_CATALOGO = "estado_fuera_de_catalogo"
SIN_EMPRESA = "sin_empresa"
SIN_TUTOR = "sin_tutor"
SIN_FECHA_FIN = "sin_fecha_fin"
NIT_REPETIDO = "nit_repetido"

REGLAS_POR_ENTIDAD: dict[str, tuple[str, ...]] = {
    "proyecto_investigacion": (FIN_ANTES_DE_INICIO, PRESUPUESTO_NEGATIVO, ESTADO_FUERA_DE_CATALOGO),
    "practica": (FIN_ANTES_DE_INICIO, ESTADO_FUERA_DE_CATALOGO, SIN_EMPRESA, SIN_TUTOR),
    "convenio": (FIN_ANTES_DE_INICIO, ESTADO_FUERA_DE_CATALOGO, SIN_FECHA_FIN),
    "empresa": (NIT_REPETIDO,),
}


def evaluar(entidad: str, filas: pd.DataFrame, *, catalogo_estados: dict[str, list[str]]) -> pd.DataFrame:
    """Aplica las reglas de `REGLAS_POR_ENTIDAD[entidad]` a las filas extraídas.

    Entradas: `filas` con los nombres canónicos de `fuentes.vistas` (incluida la columna id de la entidad:
    `id_proyecto`, `id_practica`, `id_convenio`, `id_empresa`); `catalogo_estados`: entidad -> estados
    válidos (comparación exacta: «En Ejecución» o «aprobado » con espacio están fuera del catálogo).
    Salida: DataFrame con una columna booleana por regla y el mismo índice que `filas`.
    Definiciones:
      fin_antes_de_inicio      fecha_fin < fecha_inicio (ambas no nulas)
      presupuesto_negativo     presupuesto_ejecutado < 0
      estado_fuera_de_catalogo estado nulo o no listado para la entidad
      sin_empresa              id_empresa nulo
      sin_tutor                id_tutor_academico nulo o id_tutor_empresarial nulo
      sin_fecha_fin            fecha_fin nula
      nit_repetido             el NIT (solo dígitos) aparece en más de una fila; se marcan todas
    Una entidad sin reglas devuelve un DataFrame sin columnas.
    """
    raise NotImplementedError(PENDIENTE)


def marca(evaluacion: pd.DataFrame) -> pd.Series:
    """Convierte la salida de `evaluar` en el valor de `marca_calidad`: códigos de las reglas que fallan,
    en orden alfabético y separados por coma; `None` si la fila pasa todas."""
    raise NotImplementedError(PENDIENTE)
