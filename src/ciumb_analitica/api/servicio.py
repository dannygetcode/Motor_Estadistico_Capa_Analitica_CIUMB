"""Configuración y dependencias del servicio (variables de entorno; RNF-07: ningún secreto en el código).

DATABASE_URL_LECTURA   conexión de SOLO LECTURA al esquema ana_ (invariante 3).
DATABASE_URL_RPT       conexión de escritura al esquema rpt_ (trazabilidad); por defecto, la de lectura no sirve.
SAL_SEUDONIMIZACION    secreto de seudonimización (invariante 5).
SERVICIO_TOKEN         token que debe enviar el backend del CIUMB (`Authorization: Bearer ...`; 4.4.3).
DIRECTORIO_INFORMES    carpeta donde se guardan los archivos generados (opcional).
CONSULTA_LIMITE_FILAS  tope de filas por consulta (invariante 3).
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from sqlalchemy import Connection, Engine, create_engine

from ciumb_analitica.api.flujo import Contexto, Redactor
from ciumb_analitica.compilador.compilador import LIMITE_FILAS_DEFECTO
from ciumb_analitica.semantica.almacen import leer_capa, leer_plantillas
from ciumb_analitica.semantica.modelos import CapaSemantica
from ciumb_analitica.seudonimo import sal_del_entorno


class ServicioNoConfigurado(RuntimeError):  # noqa: N818 - nombre de dominio en español
    pass


@dataclass
class Servicio:
    """Lo que la API necesita para atender una solicitud. Las pruebas lo construyen con SQLite."""

    motor_lectura: Engine
    motor_rpt: Engine
    sal: str
    token: str | None
    redactor: Redactor | None = None
    directorio: Path | None = None
    limite_filas: int = LIMITE_FILAS_DEFECTO
    hoy: Callable[[], date] = date.today
    _capa: CapaSemantica | None = field(default=None, repr=False)

    def capa(self) -> CapaSemantica:
        """Capa semántica publicada en `rpt_` (se lee una vez; reiniciar el servicio para recargarla)."""
        if self._capa is None:
            with self.motor_rpt.connect() as con:
                self._capa = leer_capa(con)
        return self._capa

    def plantillas(self, rol: str | None = None) -> list[dict]:
        with self.motor_rpt.connect() as con:
            return leer_plantillas(con, rol=rol)

    @contextmanager
    def lectura(self) -> Iterator[Connection]:
        with self.motor_lectura.connect() as con:
            if con.dialect.name == "postgresql":
                con = con.execution_options(postgresql_readonly=True)
            yield con

    @contextmanager
    def contexto(self) -> Iterator[Contexto]:
        """Una transacción de `rpt_` por solicitud: se confirma al final o se deshace si algo falla."""
        plantillas = self.plantillas()
        with self.lectura() as lectura, self.motor_rpt.begin() as rpt:
            yield Contexto(
                capa=self.capa(),
                lectura=lectura,
                rpt=rpt,
                sal=self.sal,
                redactor=self.redactor,
                plantillas=[p["codigo_informe"] for p in plantillas],
                limite_filas=self.limite_filas,
                directorio=self.directorio,
            )


def servicio_del_entorno() -> Servicio:
    """Construye el servicio con las variables de entorno. Lanza `ServicioNoConfigurado` si falta alguna."""
    url_lectura = os.environ.get("DATABASE_URL_LECTURA")
    url_rpt = os.environ.get("DATABASE_URL_RPT")
    if not url_lectura or not url_rpt:
        raise ServicioNoConfigurado("defina DATABASE_URL_LECTURA (ana_, solo lectura) y DATABASE_URL_RPT (rpt_)")
    directorio = os.environ.get("DIRECTORIO_INFORMES")
    return Servicio(
        motor_lectura=create_engine(url_lectura, pool_pre_ping=True),
        motor_rpt=create_engine(url_rpt, pool_pre_ping=True),
        sal=sal_del_entorno(),
        token=os.environ.get("SERVICIO_TOKEN") or None,
        directorio=Path(directorio) if directorio else None,
        limite_filas=int(os.environ.get("CONSULTA_LIMITE_FILAS", LIMITE_FILAS_DEFECTO)),
    )
