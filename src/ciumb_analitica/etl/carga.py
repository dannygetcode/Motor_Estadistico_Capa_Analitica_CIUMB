"""ETL nocturno: extracción incremental, seudonimización y carga del esquema `ana_` (sección 4.3.2, OE4).

Orden: dimensiones -> hechos -> agregados (los hechos necesitan las claves sustitutas). Programación con
APScheduler en horario de baja actividad (RNF-04). Cada ejecución se registra en `ana_.etl_ejecucion`.
Pruebas: `tests/etl/test_carga.py`.

Decisiones que la carga debe respetar (docs/decisiones.md):
  D-09  dim_tiempo se genera con `dw.tiempo.filas_dim_tiempo` (2015–2030).
  D-10  dim_macroproyecto es SCD tipo 2: si cambia `estado` o el coordinador, se cierra la fila vigente
        (`vigente_hasta`) y se inserta otra. La fila vigente tiene `vigente_hasta` nulo.
  D-11  hecho_proyecto: `n_hitos`, `n_hitos_atrasados` (hito no entregado con fecha planeada anterior al
        corte, o entregado después de lo planeado) y `dias_retraso_promedio` salen de `hito_entregable`.
  D-12  hecho_consultoria.sk_persona = consultor con rol 'lider'; `n_consultores` cuenta a todos.
  D-13  dim_linea_programa lleva una fila de nivel programa (línea 'No aplica') por programa;
        hecho_practica.sk_linea apunta a ella.
  D-14  hecho_practica.sk_persona = tutor académico.
  D-17  incremental por `fecha_modificacion` si la vista la tiene; si no, por huella de fila.
  D-18  instantáneas periódicas: un corte por fin de mes (`sk_fecha_corte` = último día del mes). Los
        agregados se recalculan desde los hechos cargados: `agg_proyecto_linea_mes` debe coincidir con
        `hecho_proyecto`; `agg_facturacion_mes` usa el primer día del mes de la factura.
  Tabla 13: ids de personas -> `seudonimo.seudonimizar`; NIT -> `seudonimo.hash_nit`; nunca en claro.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd
from sqlalchemy import Connection

from ciumb_analitica.motor.resultado import PENDIENTE

MODO_FECHA = "fecha_modificacion"
MODO_HUELLA = "huella_fila"
MODO_COMPLETA = "completa"


@dataclass(frozen=True)
class ResumenCarga:
    """Fila de `ana_.etl_ejecucion`."""

    tabla_destino: str
    modo: str
    filas_leidas: int
    filas_cargadas: int
    filas_marcadas: int
    inicio: datetime
    fin: datetime
    error: str | None = None


def huella_fila(fila: dict) -> str:
    """SHA-256 (64 hex) del contenido de una fila de origen, independiente del orden de las claves.

    Fechas en ISO, decimales normalizados (1.50 y 1.5 dan la misma huella) y nulos distinguibles de la cadena
    vacía. Se usa para detectar cambios cuando la tabla no tiene fecha de modificación (D-17).
    """
    raise NotImplementedError(PENDIENTE)


def filas_cambiadas(filas: pd.DataFrame, columna_id: str, huellas_previas: dict[int, str]) -> pd.DataFrame:
    """Filas nuevas o modificadas respecto de la carga anterior.

    Entradas: filas extraídas; `huellas_previas`: id de origen -> huella guardada en `etl_huella_fila`.
    Salida: subconjunto de `filas` cuyo id no está en `huellas_previas` o cuya huella cambió, con una columna
    adicional `_huella`. No detecta borrados (la fuente no borra: cambia el estado).
    """
    raise NotImplementedError(PENDIENTE)


def cargar_dimensiones(origen: Connection, destino: Connection, *, sal: str, hoy: date) -> list[ResumenCarga]:
    """Carga las siete dimensiones de `ana_` desde las vistas de `fuentes`.

    Entradas: conexión de SOLO LECTURA a la fuente, conexión de escritura a `ana_`, la sal de seudonimización
    y la fecha de ejecución. Idempotente: repetirla el mismo día no duplica filas ni abre versiones SCD nuevas.
    Salida: un `ResumenCarga` por dimensión.
    """
    raise NotImplementedError(PENDIENTE)


def cargar_hechos(
    origen: Connection, destino: Connection, *, sal: str, corte: date, catalogo_estados: dict[str, list[str]]
) -> list[ResumenCarga]:
    """Carga los siete hechos para la fecha de corte y registra las marcas de calidad.

    `corte`: último día del mes que se cierra. Las instantáneas periódicas insertan (o reemplazan) las filas
    de ese corte; las acumulativas y de transacción hacen upsert por su id de origen.
    Los registros que fallan una regla se cargan con `marca_calidad` y se cuentan en `filas_marcadas`.
    Un registro cuya dimensión no se encuentra (p. ej. práctica sin empresa) se carga con la clave nula.
    """
    raise NotImplementedError(PENDIENTE)


def recalcular_agregados(destino: Connection, *, corte: date) -> list[ResumenCarga]:
    """Recalcula `agg_proyecto_linea_mes` para el corte y `agg_facturacion_mes` completo, desde lo ya cargado."""
    raise NotImplementedError(PENDIENTE)


def ejecutar_etl(
    origen: Connection, destino: Connection, *, sal: str, hoy: date, catalogo_estados: dict[str, list[str]]
) -> list[ResumenCarga]:
    """Ejecución completa: dimensiones, hechos del último mes cerrado (`dw.tiempo.ultimo_mes_cerrado(hoy)`) y
    agregados, en una transacción por tabla. Si una tabla falla, registra el error en su `ResumenCarga` y
    continúa con las que no dependen de ella. Es la función que programa APScheduler."""
    raise NotImplementedError(PENDIENTE)
