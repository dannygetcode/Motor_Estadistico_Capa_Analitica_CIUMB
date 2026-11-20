"""Ejecución y programación del ETL nocturno (RNF-04: horario de baja actividad).

Variables de entorno:
  DATABASE_URL_FUENTE        conexión de SOLO LECTURA a la base del CIUMB (esquema `ciumb` o el real).
  DATABASE_URL_ANA_ESCRITURA conexión con permiso de escritura en `ana_` (solo la usa el ETL).
  SAL_SEUDONIMIZACION        secreto de seudonimización.
  ETL_HORA                   hora local de la ejecución diaria (0-23; por defecto 2).

Uso:
  uv run python -m ciumb_analitica.etl                      # una ejecución ahora (último mes cerrado)
  uv run python -m ciumb_analitica.etl --historico 2019-01  # además, cortes mensuales desde ese mes
  uv run python -m ciumb_analitica.etl --programar          # deja el proceso programado cada noche
"""

from __future__ import annotations

import argparse
import logging
import os
from collections.abc import Callable
from datetime import date

from sqlalchemy import Engine, create_engine

from ciumb_analitica.dw.tiempo import ultimo_mes_cerrado
from ciumb_analitica.etl import carga
from ciumb_analitica.seudonimo import sal_del_entorno

log = logging.getLogger(__name__)

CATALOGO_ESTADOS: dict[str, list[str]] = {
    "usuario": ["activo", "inactivo", "bloqueado"],
    "macroproyecto": ["activo", "en_cierre", "cerrado", "suspendido"],
    "proyecto_investigacion": ["formulado", "en_validacion", "aprobado", "en_ejecucion", "finalizado", "cancelado"],
    "hito_entregable": ["pendiente", "entregado", "vencido"],
    "empresa": ["activa", "inactiva"],
    "convenio": ["vigente", "vencido", "en_renovacion", "terminado"],
    "practica": ["por_iniciar", "en_curso", "finalizada", "cancelada"],
    "consultoria": ["propuesta", "en_ejecucion", "finalizada", "cancelada"],
}
"""Catálogo de estados válidos (PROVISIONAL, D-04): copia de `datos_sinteticos.generar.CATALOGO_ESTADOS` para que
el servicio no dependa del generador. Se reemplaza por el catálogo oficial cuando lo entregue el CIUMB."""


def _motor(variable: str) -> Engine:
    url = os.environ.get(variable)
    if not url:
        raise RuntimeError(f"defina {variable}")
    return create_engine(url, pool_pre_ping=True)


def ejecutar_una_vez(
    *, hoy: date | None = None, historico_desde: date | None = None, origen: Engine | None = None,
    destino: Engine | None = None, sal: str | None = None,
) -> list[carga.ResumenCarga]:  # fmt: skip
    """Una ejecución completa en una transacción de `ana_` (se confirma al final; cada tabla en su punto de
    guardado). Con `historico_desde`, también carga los cortes mensuales desde ese mes (carga inicial, D-29)."""
    hoy = hoy or date.today()
    origen = origen or _motor("DATABASE_URL_FUENTE")
    destino = destino or _motor("DATABASE_URL_ANA_ESCRITURA")
    sal = sal or sal_del_entorno()
    with origen.connect() as o, destino.begin() as d:
        if o.dialect.name == "postgresql":
            o = o.execution_options(postgresql_readonly=True)
        resumenes = carga.ejecutar_etl(o, d, sal=sal, hoy=hoy, catalogo_estados=CATALOGO_ESTADOS)
        if historico_desde is not None:
            hasta = ultimo_mes_cerrado(date(hoy.year, hoy.month, 1))  # el mes anterior al corte de hoy
            resumenes += carga.cargar_cortes_historicos(
                o, d, sal=sal, desde=historico_desde, hasta=hasta, catalogo_estados=CATALOGO_ESTADOS
            )
    for r in resumenes:
        nivel = logging.ERROR if r.error else logging.INFO
        log.log(nivel, "%s %s leídas=%s cargadas=%s marcadas=%s %s", r.tabla_destino, r.modo, r.filas_leidas,
                r.filas_cargadas, r.filas_marcadas, r.error or "")  # fmt: skip
    return resumenes


def programar(tarea: Callable[[], object] = ejecutar_una_vez, *, hora: int | None = None):
    """Programa `tarea` cada día a `hora` (ETL_HORA, por defecto 2:00) con APScheduler y devuelve el planificador
    sin iniciarlo. Una ejecución que se retrasa más de una hora se omite (no se acumulan ejecuciones)."""
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    hora = int(os.environ.get("ETL_HORA", 2)) if hora is None else hora
    planificador = BlockingScheduler()
    planificador.add_job(
        tarea, CronTrigger(hour=hora, minute=0), id="etl_nocturno", max_instances=1, coalesce=True,
        misfire_grace_time=3600, replace_existing=True,
    )  # fmt: skip
    return planificador


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ETL nocturno del área analítica del CIUMB.")
    parser.add_argument("--historico", help="carga además los cortes mensuales desde AAAA-MM")
    parser.add_argument("--programar", action="store_true", help="queda programado cada noche (ETL_HORA)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.programar:
        programar().start()
        return 0
    desde = date.fromisoformat(f"{args.historico}-01") if args.historico else None
    resumenes = ejecutar_una_vez(historico_desde=desde)
    return 1 if any(r.error for r in resumenes) else 0
