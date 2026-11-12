"""Vistas de extracción sobre la fuente 1 (capa de traducción; sección 4.2, Tablas 10–13).

Es el ÚNICO lugar que conoce los nombres de tablas y columnas de la base transaccional del CIUMB. Hoy apuntan
al modelo INFERIDO (`datos_sinteticos/ddl.sql`, esquema `ciumb`); cuando llegue el modelo real solo cambia este
módulo, no el datawarehouse (CLAUDE.md, «Estado conocido»).

Minimización (Tabla 13, invariante 5): una vista nunca selecciona `nombre_completo`, `documento`, `correo`,
`contrasena_hash`, `razon_social` ni `titulo`. El NIT y los ids de personas se leen solo para convertirlos en
hash dentro del ETL; nunca se escriben en `ana_`.
Pruebas: `tests/fuentes/test_vistas.py`.
"""

from __future__ import annotations

from sqlalchemy import Select

from ciumb_analitica.motor.resultado import PENDIENTE

ESQUEMA_FUENTE = "ciumb"

COLUMNAS_PROHIBIDAS = frozenset({"nombre_completo", "documento", "correo", "contrasena_hash", "razon_social", "titulo"})
"""Columnas que ninguna vista puede leer. `macroproyecto.nombre` sí se lee (información institucional)."""

COLUMNAS_A_SEUDONIMIZAR = frozenset(
    {"id_usuario", "id_coordinador", "id_estudiante", "id_tutor_academico", "id_tutor_empresarial", "nit"}
)
"""Columnas que se leen solo para aplicar `seudonimo.seudonimizar` / `seudonimo.hash_nit` en el ETL."""

ENTIDADES = (
    "rol", "usuario", "registro_acceso", "facultad_programa", "linea_investigacion", "macroproyecto",
    "fase_macroproyecto", "proyecto_investigacion", "hito_entregable", "integrante_proyecto", "empresa",
    "convenio", "documento_convenio", "practica", "consultoria", "factura_consultoria", "consultor_consultoria",
)  # fmt: skip


def vista(entidad: str) -> Select:
    """SELECT de solo lectura de una entidad de la fuente, con nombres de columna canónicos.

    Entradas: `entidad`, una de `ENTIDADES`. Salida: `sqlalchemy.Select` (SQLAlchemy Core, sin texto SQL
    libre) que expone solo los campos analíticos de las Tablas 10–12 más los ids necesarios para unir.
    Si la entidad tiene fecha de modificación, la expone como `fecha_modificacion` (carga incremental, D-17).
    Lanza `KeyError` si la entidad no existe.
    """
    raise NotImplementedError(PENDIENTE)


def columnas(entidad: str) -> tuple[str, ...]:
    """Nombres canónicos de las columnas que expone `vista(entidad)`."""
    raise NotImplementedError(PENDIENTE)


def tiene_fecha_modificacion(entidad: str) -> bool:
    """True si la vista expone `fecha_modificacion` (hoy: proyecto_investigacion y practica, D-04)."""
    raise NotImplementedError(PENDIENTE)
