"""Vistas de extracción sobre la fuente 1 (capa de traducción; sección 4.2, Tablas 10–13).

Es el ÚNICO lugar que conoce los nombres de tablas y columnas de la base transaccional del CIUMB. Hoy apuntan
al modelo INFERIDO (`datos_sinteticos/ddl.sql`, esquema `ciumb`); cuando llegue el modelo real solo cambia este
módulo, no el datawarehouse.

Minimización (Tabla 13, invariante 5): una vista nunca selecciona `nombre_completo`, `documento`, `correo`,
`contrasena_hash`, `razon_social` ni `titulo`. El NIT y los ids de personas se leen solo para convertirlos en
hash dentro del ETL; nunca se escriben en `ana_`.
Pruebas: `tests/fuentes/test_vistas.py`.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Integer,
    MetaData,
    Numeric,
    Select,
    String,
    Table,
    select,
)

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


metadatos_fuente = MetaData(schema=ESQUEMA_FUENTE)
"""Tablas de la fuente 1 con SOLO las columnas que el ETL puede leer. Es la lista blanca de la extracción: una
columna que no está aquí no se puede seleccionar, aunque exista en la base del CIUMB. Las pruebas de integración
crean estas mismas tablas en SQLite para correr el ETL sin PostgreSQL."""


def _t(nombre: str, *columnas: Column) -> Table:
    return Table(nombre, metadatos_fuente, *columnas)


def _id(nombre: str, *, pk: bool = False) -> Column:
    return Column(nombre, Integer, primary_key=pk, autoincrement=False)


_t("rol", _id("id_rol", pk=True), Column("nombre_rol", String(60)), Column("alcance_modulos", String(200)))
_t(
    "usuario",
    _id("id_usuario", pk=True),
    _id("id_rol"),
    Column("estado", String(30)),
    Column("fecha_creacion", Date),
    Column("ultimo_acceso", DateTime),
    Column("fecha_vence_contrasena", Date),
)
_t(
    "registro_acceso",
    _id("id_acceso", pk=True),
    _id("id_usuario"),
    Column("fecha_hora", DateTime),
    Column("exitoso", Boolean),
    Column("bloqueo_generado", Boolean),
)
_t(
    "facultad_programa",
    _id("id_programa", pk=True),
    Column("nombre_programa", String(150)),
    Column("facultad", String(150)),
)
_t("linea_investigacion", _id("id_linea", pk=True), Column("nombre", String(150)), _id("id_programa"))
_t(
    "macroproyecto",
    _id("id_macroproyecto", pk=True),
    Column("nombre", String(250)),  # institucional: se lee, nunca viaja a la IA (Tabla 13)
    Column("estado", String(30)),
    _id("id_coordinador"),
    _id("id_programa"),
    Column("fecha_inicio", Date),
    Column("fecha_fin_planeada", Date),
    Column("fecha_fin_real", Date),
    Column("porcentaje_avance", Numeric(5, 2)),
)
_t(
    "fase_macroproyecto",
    _id("id_fase", pk=True),
    _id("id_macroproyecto"),
    Column("nombre_fase", String(150)),
    Column("avance", Numeric(5, 2)),
    Column("fecha_fin_planeada", Date),
    Column("fecha_fin_real", Date),
)
_t(
    "proyecto_investigacion",
    _id("id_proyecto", pk=True),
    _id("id_macroproyecto"),
    _id("id_linea"),
    Column("estado", String(30)),
    Column("fecha_creacion", Date),
    Column("fecha_validacion", Date),
    Column("fecha_aprobacion", Date),
    Column("fecha_inicio", Date),
    Column("fecha_fin", Date),
    Column("presupuesto_asignado", Numeric(14, 2)),
    Column("presupuesto_ejecutado", Numeric(14, 2)),
    Column("fecha_modificacion", DateTime),
)
_t(
    "hito_entregable",
    _id("id_hito", pk=True),
    _id("id_proyecto"),
    Column("tipo", String(60)),
    Column("fecha_planeada", Date),
    Column("fecha_real", Date),
    Column("estado", String(30)),
)
_t(
    "integrante_proyecto",
    _id("id_proyecto", pk=True),
    _id("id_usuario", pk=True),
    Column("rol_en_proyecto", String(60)),
)
_t(
    "empresa",
    _id("id_empresa", pk=True),
    Column("nit", String(20)),  # solo para `seudonimo.hash_nit` y la regla nit_repetido
    Column("sector", String(80)),
    Column("ciudad", String(80)),
    Column("tipo", String(40)),
    Column("fecha_registro", Date),
    Column("estado", String(30)),
)
_t(
    "convenio",
    _id("id_convenio", pk=True),
    _id("id_empresa"),
    Column("tipo", String(40)),
    Column("fecha_firma", Date),
    Column("fecha_inicio", Date),
    Column("fecha_fin", Date),
    _id("id_convenio_anterior"),
    Column("estado", String(30)),
)
_t(
    "documento_convenio",
    _id("id_documento", pk=True),
    _id("id_convenio"),
    Column("tipo_documento", String(80)),
    Column("cargado", Boolean),
)
_t(
    "practica",
    _id("id_practica", pk=True),
    _id("id_estudiante"),
    _id("id_empresa"),
    _id("id_convenio"),
    _id("id_macroproyecto"),
    _id("id_programa"),
    _id("id_tutor_academico"),
    _id("id_tutor_empresarial"),
    Column("periodo", String(10)),
    Column("estado", String(30)),
    Column("fecha_inicio", Date),
    Column("fecha_fin", Date),
    Column("tareas_asignadas", Integer),
    Column("tareas_cumplidas", Integer),
    Column("fecha_modificacion", DateTime),
)
_t(
    "consultoria",
    _id("id_consultoria", pk=True),
    _id("id_empresa"),
    _id("id_convenio"),
    Column("estado", String(30)),
    Column("fecha_inicio", Date),
    Column("fecha_fin", Date),
    Column("valor_contratado", Numeric(14, 2)),
    Column("calificacion_satisfaccion", Numeric(3, 1)),
)
_t(
    "factura_consultoria",
    _id("id_factura", pk=True),
    _id("id_consultoria"),
    Column("fecha_factura", Date),
    Column("valor", Numeric(14, 2)),
)
_t("consultor_consultoria", _id("id_consultoria", pk=True), _id("id_usuario", pk=True), Column("rol", String(60)))

_RENOMBRES: dict[str, dict[str, str]] = {}
"""Columna de la fuente -> nombre canónico, por entidad. Vacío con el modelo inferido; cuando llegue el modelo
real del CIUMB, aquí se traducen sus nombres a los que espera el ETL."""


def tabla_fuente(entidad: str) -> Table:
    """Tabla de la lista blanca de la fuente. Lanza `KeyError` si la entidad no existe."""
    if entidad not in ENTIDADES:
        raise KeyError(entidad)
    return metadatos_fuente.tables[f"{ESQUEMA_FUENTE}.{entidad}"]


def vista(entidad: str) -> Select:
    """SELECT de solo lectura de una entidad de la fuente, con nombres de columna canónicos.

    Entradas: `entidad`, una de `ENTIDADES`. Salida: `sqlalchemy.Select` (SQLAlchemy Core, sin texto SQL
    libre) que expone solo los campos analíticos de las Tablas 10–12 más los ids necesarios para unir.
    Si la entidad tiene fecha de modificación, la expone como `fecha_modificacion` (carga incremental, D-17).
    Lanza `KeyError` si la entidad no existe.
    """
    tabla = tabla_fuente(entidad)
    renombres = _RENOMBRES.get(entidad, {})
    return select(*(c.label(renombres.get(c.name, c.name)) for c in tabla.columns))


def columnas(entidad: str) -> tuple[str, ...]:
    """Nombres canónicos de las columnas que expone `vista(entidad)`."""
    renombres = _RENOMBRES.get(entidad, {})
    return tuple(renombres.get(c.name, c.name) for c in tabla_fuente(entidad).columns)


def tiene_fecha_modificacion(entidad: str) -> bool:
    """True si la vista expone `fecha_modificacion` (hoy: proyecto_investigacion y practica, D-04)."""
    return "fecha_modificacion" in columnas(entidad)
