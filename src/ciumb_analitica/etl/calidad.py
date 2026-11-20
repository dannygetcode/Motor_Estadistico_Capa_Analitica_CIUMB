"""Reglas de calidad del ETL (sección 4.2.2; INF-TRA-08).

Los registros que fallan una regla NO se descartan: se cargan con `marca_calidad` (códigos separados por coma)
y se registran en `ana_.etl_marca_calidad`, para que el área responsable los corrija en el origen.
Pruebas: `tests/etl/test_calidad.py` (contra los defectos exactos de `datos_sinteticos.generar`).
"""

from __future__ import annotations

import pandas as pd

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


def _fecha(serie: pd.Series) -> pd.Series:
    return pd.to_datetime(serie, errors="coerce")


def _columna(filas: pd.DataFrame, nombre: str) -> pd.Series:
    if nombre not in filas.columns:
        raise KeyError(f"la regla necesita la columna '{nombre}'")
    return filas[nombre]


def _digitos(valor) -> str | None:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    digitos = "".join(c for c in str(valor) if c.isdigit())
    return digitos or None


def _regla(regla: str, entidad: str, filas: pd.DataFrame, catalogo: dict[str, list[str]]) -> pd.Series:
    if regla == FIN_ANTES_DE_INICIO:
        inicio, fin = _fecha(_columna(filas, "fecha_inicio")), _fecha(_columna(filas, "fecha_fin"))
        return (fin < inicio).fillna(False)
    if regla == PRESUPUESTO_NEGATIVO:
        return (pd.to_numeric(_columna(filas, "presupuesto_ejecutado"), errors="coerce") < 0).fillna(False)
    if regla == ESTADO_FUERA_DE_CATALOGO:
        validos = set(catalogo.get(entidad, ()))
        return ~_columna(filas, "estado").map(lambda e: isinstance(e, str) and e in validos).astype(bool)
    if regla == SIN_EMPRESA:
        return _columna(filas, "id_empresa").isna()
    if regla == SIN_TUTOR:
        return _columna(filas, "id_tutor_academico").isna() | _columna(filas, "id_tutor_empresarial").isna()
    if regla == SIN_FECHA_FIN:
        return _columna(filas, "fecha_fin").isna()
    if regla == NIT_REPETIDO:
        digitos = _columna(filas, "nit").map(_digitos)
        conteo = digitos.map(digitos.value_counts())
        return (digitos.notna() & (conteo > 1)).fillna(False)
    raise KeyError(f"regla de calidad desconocida: {regla}")


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
    reglas = REGLAS_POR_ENTIDAD.get(entidad, ())
    evaluacion = pd.DataFrame(index=filas.index)
    for regla in reglas:
        evaluacion[regla] = _regla(regla, entidad, filas, catalogo_estados).astype(bool).to_numpy()
    return evaluacion


def marca(evaluacion: pd.DataFrame) -> pd.Series:
    """Convierte la salida de `evaluar` en el valor de `marca_calidad`: códigos de las reglas que fallan,
    en orden alfabético y separados por coma; `None` si la fila pasa todas."""
    columnas = sorted(evaluacion.columns)
    valores = evaluacion[columnas].to_numpy(dtype=bool) if columnas else None
    marcas = [
        (",".join(c for c, falla in zip(columnas, fila, strict=True) if falla) or None) if columnas else None
        for fila in (valores if valores is not None else [()] * len(evaluacion))
    ]
    return pd.Series(marcas, index=evaluacion.index, dtype=object)
