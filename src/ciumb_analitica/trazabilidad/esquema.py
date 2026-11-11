"""Esquema `rpt_` del servicio de informes (fuente 2; Figura 6, Tabla 12) como metadatos de SQLAlchemy Core.

INTERFAZ CERRADA: cambiar tablas o columnas exige aprobación de Daniel.

Columnas que el diseño no trae y se agregaron (docs/decisiones.md, D-19):
- rpt_metrica: `descripcion`, `agregacion_defecto`, `columna_personas`, `agregados_json`.
- rpt_dimension: `descripcion`, `viaja_a_ia`, `binaria_de_metrica`.
- claves primarias y fechas de registro donde la Figura 6 no las nombra.
"""

from __future__ import annotations

from sqlalchemy import (
    CHAR,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
)

ESQUEMA_RPT = "rpt_"

metadatos_rpt = MetaData(schema=ESQUEMA_RPT)


def _fk(nombre: str, destino: str, *, nulo: bool = False) -> Column:
    return Column(nombre, Integer, ForeignKey(f"{ESQUEMA_RPT}.{destino}"), nullable=nulo)


# --- Capa semántica (encabezado rojo de la Figura 6) -----------------------------------------------------------

rpt_metrica = Table(
    "rpt_metrica",
    metadatos_rpt,
    Column("id_metrica", Integer, primary_key=True),
    Column("codigo", String(60), nullable=False, unique=True),
    Column("nombre", String(150), nullable=False),
    Column("descripcion", String(400), nullable=False),
    Column("sinonimos_json", Text, nullable=False),
    Column("hecho_o_agregado", String(60), nullable=False),
    Column("expresion_sql", String(200), nullable=False),  # gramática cerrada: ver semantica/expresion.py
    Column("agregaciones", String(100), nullable=False),  # lista separada por comas
    Column("agregacion_defecto", String(20), nullable=False),
    Column("aditividad", String(20), nullable=False),  # aditiva | semiaditiva | no_aditiva
    Column("unidad", String(40), nullable=False),
    Column("columna_personas", String(60), nullable=True),  # columna que cuenta personas (supresión < 5)
    Column("agregados_json", Text, nullable=False),  # agregados precalculados alternos
    Column("activa", Boolean, nullable=False),
)

rpt_dimension = Table(
    "rpt_dimension",
    metadatos_rpt,
    Column("id_dimension", Integer, primary_key=True),
    Column("codigo", String(60), nullable=False, unique=True),
    Column("nombre", String(150), nullable=False),
    Column("descripcion", String(400), nullable=False),
    Column("sinonimos_json", Text, nullable=False),
    Column("tabla_columna", String(120), nullable=True),  # NULL solo en dimensiones binarias derivadas
    Column("tipo", String(20), nullable=False),  # categorica | temporal | ordinal
    Column("identifica_persona", Boolean, nullable=False),
    Column("viaja_a_ia", Boolean, nullable=False),
    Column("binaria_de_metrica", String(60), nullable=True),
)

rpt_compatibilidad = Table(
    "rpt_compatibilidad",
    metadatos_rpt,
    _fk("id_metrica", "rpt_metrica.id_metrica"),
    _fk("id_dimension", "rpt_dimension.id_dimension"),
    PrimaryKeyConstraint("id_metrica", "id_dimension"),
    comment="Matriz de bus (Tabla 15) convertida en reglas métrica x dimensión.",
)

rpt_plantilla = Table(
    "rpt_plantilla",
    metadatos_rpt,
    Column("id_plantilla", Integer, primary_key=True),
    Column("codigo_informe", String(12), nullable=False, unique=True),  # INF-XXX-NN
    Column("nombre", String(200), nullable=False),
    Column("spec_json", Text, nullable=False),
    Column("version", Integer, nullable=False),
    Column("roles_permitidos", String(200), nullable=False),  # lista separada por comas
    Column("activa", Boolean, nullable=False),
)

rpt_especificacion = Table(
    "rpt_especificacion",
    metadatos_rpt,
    Column("id_especificacion", Integer, primary_key=True),
    _fk("id_plantilla", "rpt_plantilla.id_plantilla", nulo=True),  # opcional: la relación admite cero
    Column("esquema_version", String(20), nullable=False),
    Column("origen", String(20), nullable=False),
    Column("spec_json", Text, nullable=False),
    Column("huella_spec", CHAR(64), nullable=False),
    Column("estado_validacion", String(20), nullable=False),  # valida | corregible | fuera_de_alcance
    Column("motivo", String(500), nullable=True),
    Column("fecha_registro", DateTime, nullable=False),
)

# --- Operación (encabezado azul de la Figura 6) ----------------------------------------------------------------

rpt_programacion = Table(
    "rpt_programacion",
    metadatos_rpt,
    Column("id_programacion", Integer, primary_key=True),
    _fk("id_especificacion", "rpt_especificacion.id_especificacion"),
    Column("periodicidad", String(20), nullable=False),
    Column("destinatarios_rol", String(200), nullable=False),
    Column("activa", Boolean, nullable=False),
)

rpt_solicitud = Table(
    "rpt_solicitud",
    metadatos_rpt,
    Column("id_solicitud", Integer, primary_key=True),
    _fk("id_especificacion", "rpt_especificacion.id_especificacion", nulo=True),
    Column("id_usuario", CHAR(64), nullable=False),  # seudónimo, nunca el id en claro
    Column("prompt_texto", Text, nullable=True),  # depurado con PATRONES_PII antes de guardar
    Column("fecha_corte", Date, nullable=True),
    Column("estado", String(20), nullable=False),
    Column("fecha_solicitud", DateTime, nullable=False),
)

rpt_resultado = Table(
    "rpt_resultado",
    metadatos_rpt,
    Column("id_resultado", Integer, primary_key=True),
    _fk("id_solicitud", "rpt_solicitud.id_solicitud"),
    Column("formato", String(10), nullable=False),
    Column("huella_datos", CHAR(64), nullable=False),  # solo el hexadecimal (D-15)
    Column("sql_compilado", Text, nullable=False),
    Column("ruta_archivo", String(300), nullable=True),
    Column("modo", String(20), nullable=False),  # con_ia | degradado
    Column("fecha_generacion", DateTime, nullable=False),
)

rpt_validacion = Table(
    "rpt_validacion",
    metadatos_rpt,
    Column("id_validacion", Integer, primary_key=True),
    _fk("id_resultado", "rpt_resultado.id_resultado"),
    Column("cifras_texto", Integer, nullable=False),
    Column("cifras_discrepantes", Integer, nullable=False),
    Column("regeneraciones", Integer, nullable=False),
    Column("uso_plantilla", Boolean, nullable=False),
    Column("fecha", DateTime, nullable=False),
    comment="Base del objetivo OE5: exactitud de cifras por informe.",
)

rpt_proveedor_ia = Table(
    "rpt_proveedor_ia",
    metadatos_rpt,
    Column("id_proveedor", Integer, primary_key=True),
    Column("nombre", String(60), nullable=False),
    Column("modelo", String(100), nullable=False),
    Column("prioridad", Integer, nullable=False),
    Column("estado", String(20), nullable=False),
    comment="La administra la capa de IA; este servicio no llama a ningún proveedor.",
)

rpt_uso_ia = Table(
    "rpt_uso_ia",
    metadatos_rpt,
    Column("id_uso", Integer, primary_key=True),
    _fk("id_proveedor", "rpt_proveedor_ia.id_proveedor"),
    _fk("id_solicitud", "rpt_solicitud.id_solicitud"),
    Column("tarea", String(30), nullable=False),
    Column("tokens", Integer, nullable=True),
    Column("latencia_ms", Integer, nullable=True),
    Column("error", String(300), nullable=True),
    Column("fecha", DateTime, nullable=False),
)

rpt_narrativa_cache = Table(
    "rpt_narrativa_cache",
    metadatos_rpt,
    Column("huella_entrada", CHAR(64), primary_key=True),
    Column("texto_json", Text, nullable=False),
    _fk("id_proveedor", "rpt_proveedor_ia.id_proveedor", nulo=True),
    Column("fecha", DateTime, nullable=False),
)

rpt_alerta = Table(
    "rpt_alerta",
    metadatos_rpt,
    Column("id_alerta", Integer, primary_key=True),
    Column("codigo_regla", String(40), nullable=False),
    Column("entidad", String(60), nullable=False),
    Column("valor", Numeric(16, 4), nullable=True),
    Column("umbral", Numeric(16, 4), nullable=True),
    Column("estado", String(20), nullable=False),
    Column("fecha", DateTime, nullable=False),
)
