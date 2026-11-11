"""Esquema `ana_` del datawarehouse (sección 4.3, Figuras 7–8, Tablas 15–17) como metadatos de SQLAlchemy Core.

INTERFAZ CERRADA: cambiar tablas o columnas exige aprobación de Daniel. El SQL de PostgreSQL se genera con
`uv run python -m ciumb_analitica.dw.ddl` y queda en `sql/ana_rpt_postgresql.sql`.

Convenciones (docs/decisiones.md, D-09 a D-14 y D-18):
- Claves sustitutas `sk_`. `sk_fecha` es un entero AAAAMMDD (ordenable sin unir con `dim_tiempo`).
- Los ids de origen se conservan como atributo o dimensión degenerada (`id_proyecto`, `id_practica`…).
- Indicadores (`finalizada`, `a_tiempo`, `renovado`, `docs_completos`) son enteros 0/1 para poder sumarlos
  en cualquier motor.
- Cada hecho lleva `marca_calidad`: NULL si pasó todas las reglas del ETL; si no, códigos separados por coma.
- `Table.info` declara lo que el compilador necesita y el diseño fija en la Tabla 17:
    tipo        'instantanea_periodica' | 'instantanea_acumulativa' | 'transaccion' | 'agregado'
    col_tiempo  columna que une con `dim_tiempo`
    grano       columnas que identifican una fila
  En una instantánea periódica las medidas NO se suman entre fechas de corte: el compilador toma el último
  corte de cada periodo.
- Las tablas son la lista blanca de identificadores del compilador (invariante 2).
"""

from __future__ import annotations

from sqlalchemy import (
    CHAR,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    Table,
)

ESQUEMA_ANA = "ana_"

metadatos_ana = MetaData(schema=ESQUEMA_ANA)

INSTANTANEA_PERIODICA = "instantanea_periodica"
INSTANTANEA_ACUMULATIVA = "instantanea_acumulativa"
TRANSACCION = "transaccion"
AGREGADO = "agregado"


def _fk(tabla_columna: str, *, nulo: bool = False) -> Column:
    nombre = tabla_columna.split(".")[1]
    return Column(nombre, Integer, ForeignKey(f"{ESQUEMA_ANA}.{tabla_columna}"), nullable=nulo)


def _fk_como(nombre: str, tabla_columna: str, *, nulo: bool = False) -> Column:
    return Column(nombre, Integer, ForeignKey(f"{ESQUEMA_ANA}.{tabla_columna}"), nullable=nulo)


def _marca() -> Column:
    return Column("marca_calidad", String(200), nullable=True)


# --- Dimensiones (Tabla 16) ----------------------------------------------------------------------------------

dim_tiempo = Table(
    "dim_tiempo",
    metadatos_ana,
    Column("sk_fecha", Integer, primary_key=True, autoincrement=False),  # AAAAMMDD
    Column("fecha", Date, nullable=False, unique=True),
    Column("dia", SmallInteger, nullable=False),
    Column("mes", SmallInteger, nullable=False),
    Column("nombre_mes", String(12), nullable=False),
    Column("trimestre", SmallInteger, nullable=False),
    Column("semestre", SmallInteger, nullable=False),
    Column("anio", SmallInteger, nullable=False),
    Column("periodo_academico", String(6), nullable=False),  # p. ej. 2026-2
    comment="Se genera por código para 2015 a 2030 (Tabla 16).",
)

dim_persona_rol = Table(
    "dim_persona_rol",
    metadatos_ana,
    Column("sk_persona", Integer, primary_key=True),
    Column("seudonimo", CHAR(64), nullable=False),  # SHA-256 con sal del id de origen (Tabla 13)
    Column("rol", String(60), nullable=False),
    Column("tipo_participacion", String(60), nullable=False),
    comment="No guarda nombres ni documentos.",
)

dim_linea_programa = Table(
    "dim_linea_programa",
    metadatos_ana,
    Column("sk_linea", Integer, primary_key=True),
    Column("id_linea_origen", Integer, nullable=True),  # NULL en la fila de nivel programa (D-13)
    Column("id_programa_origen", Integer, nullable=False),
    Column("linea_investigacion", String(150), nullable=False),  # 'No aplica' en la fila de nivel programa
    Column("programa", String(150), nullable=False),
    Column("facultad", String(150), nullable=False),
    comment="Jerarquía facultad > programa > línea. Una fila adicional por programa con línea 'No aplica'.",
)

dim_macroproyecto = Table(
    "dim_macroproyecto",
    metadatos_ana,
    Column("sk_macroproyecto", Integer, primary_key=True),
    Column("id_origen", Integer, nullable=False),
    Column("nombre", String(250), nullable=False),  # institucional: no viaja a la IA (Tabla 13)
    Column("estado_actual", String(30), nullable=False),
    _fk_como("sk_coordinador", "dim_persona_rol.sk_persona", nulo=True),
    Column("vigente_desde", Date, nullable=False),
    Column("vigente_hasta", Date, nullable=True),  # NULL = fila vigente (SCD tipo 2, D-10)
)

dim_estado = Table(
    "dim_estado",
    metadatos_ana,
    Column("sk_estado", Integer, primary_key=True),
    Column("modulo", String(40), nullable=False),
    Column("estado", String(30), nullable=False),
    Column("es_final", SmallInteger, nullable=False),
    comment="Catálogo unificado de estados de los siete módulos.",
)

dim_empresa = Table(
    "dim_empresa",
    metadatos_ana,
    Column("sk_empresa", Integer, primary_key=True),
    Column("id_origen", Integer, nullable=False),
    Column("sector", String(80), nullable=True),
    Column("ciudad", String(80), nullable=True),
    Column("tipo", String(40), nullable=True),
    Column("segmento_actividad", String(40), nullable=True),  # lo escribe ml/ (INF-EMP-03)
    Column("nit_hash", CHAR(64), nullable=True),
    comment="Sin razón social ni NIT en claro.",
)

dim_tipo_convenio = Table(
    "dim_tipo_convenio",
    metadatos_ana,
    Column("sk_tipo_convenio", Integer, primary_key=True),
    Column("tipo_convenio", String(40), nullable=False),  # marco | especifico | cooperacion
)

# --- Hechos (Tabla 17) ---------------------------------------------------------------------------------------

hecho_macroproyecto = Table(
    "hecho_macroproyecto",
    metadatos_ana,
    _fk_como("sk_fecha_corte", "dim_tiempo.sk_fecha"),
    _fk("dim_macroproyecto.sk_macroproyecto"),
    _fk("dim_estado.sk_estado"),
    Column("pct_avance", Numeric(5, 2)),
    Column("desviacion_dias", Integer),
    Column("n_proyectos", Integer),
    Column("n_practicas", Integer),
    _marca(),
    info={"tipo": INSTANTANEA_PERIODICA, "col_tiempo": "sk_fecha_corte", "grano": ("sk_macroproyecto",)},
)
hecho_macroproyecto.append_constraint(PrimaryKeyConstraint("sk_fecha_corte", "sk_macroproyecto"))

hecho_proyecto = Table(
    "hecho_proyecto",
    metadatos_ana,
    _fk_como("sk_fecha_corte", "dim_tiempo.sk_fecha"),
    Column("id_proyecto", Integer, nullable=False),  # dimensión degenerada
    _fk("dim_macroproyecto.sk_macroproyecto", nulo=True),
    _fk("dim_linea_programa.sk_linea", nulo=True),
    _fk("dim_estado.sk_estado"),
    Column("presupuesto_asignado", Numeric(14, 2)),
    Column("presupuesto_ejecutado", Numeric(14, 2)),
    Column("pct_ejecucion", Numeric(7, 2)),
    Column("n_integrantes", Integer),
    Column("n_hitos", Integer),
    Column("n_hitos_atrasados", Integer),
    Column("dias_retraso_promedio", Numeric(8, 2)),
    Column("dias_creacion_aprobacion", Integer),
    _marca(),
    info={"tipo": INSTANTANEA_PERIODICA, "col_tiempo": "sk_fecha_corte", "grano": ("id_proyecto",)},
)
hecho_proyecto.append_constraint(PrimaryKeyConstraint("sk_fecha_corte", "id_proyecto"))

hecho_hito = Table(
    "hecho_hito",
    metadatos_ana,
    Column("id_hito", Integer, primary_key=True, autoincrement=False),
    Column("id_proyecto", Integer, nullable=False),  # dimensión degenerada
    _fk_como("sk_fecha_planeada", "dim_tiempo.sk_fecha"),
    _fk("dim_estado.sk_estado"),
    Column("dias_retraso", Integer),
    Column("a_tiempo", SmallInteger),
    _marca(),
    info={"tipo": TRANSACCION, "col_tiempo": "sk_fecha_planeada", "grano": ("id_hito",)},
)

hecho_practica = Table(
    "hecho_practica",
    metadatos_ana,
    Column("id_practica", Integer, primary_key=True, autoincrement=False),
    _fk("dim_tiempo.sk_fecha"),  # fecha de inicio
    _fk("dim_macroproyecto.sk_macroproyecto", nulo=True),
    _fk("dim_linea_programa.sk_linea", nulo=True),  # fila de nivel programa (D-13)
    _fk("dim_estado.sk_estado"),
    _fk("dim_persona_rol.sk_persona", nulo=True),  # tutor académico (D-14)
    _fk("dim_empresa.sk_empresa", nulo=True),
    Column("seudonimo_estudiante", CHAR(64), nullable=True),  # para contar personas (supresión < 5)
    Column("duracion_dias", Integer),
    Column("tareas_asignadas", Integer),
    Column("tareas_cumplidas", Integer),
    Column("finalizada", SmallInteger),
    _marca(),
    info={"tipo": INSTANTANEA_ACUMULATIVA, "col_tiempo": "sk_fecha", "grano": ("id_practica",)},
)

hecho_convenio = Table(
    "hecho_convenio",
    metadatos_ana,
    _fk_como("sk_fecha_corte", "dim_tiempo.sk_fecha"),
    Column("id_convenio", Integer, nullable=False),  # dimensión degenerada
    _fk("dim_estado.sk_estado"),
    _fk("dim_empresa.sk_empresa"),
    _fk("dim_tipo_convenio.sk_tipo_convenio"),
    Column("duracion_dias", Integer),
    Column("dias_para_vencer", Integer),
    Column("renovado", SmallInteger),
    Column("docs_completos", SmallInteger),
    Column("n_actividades", Integer),
    _marca(),
    info={"tipo": INSTANTANEA_PERIODICA, "col_tiempo": "sk_fecha_corte", "grano": ("id_convenio",)},
)
hecho_convenio.append_constraint(PrimaryKeyConstraint("sk_fecha_corte", "id_convenio"))

hecho_consultoria = Table(
    "hecho_consultoria",
    metadatos_ana,
    Column("id_consultoria", Integer, primary_key=True, autoincrement=False),
    _fk("dim_tiempo.sk_fecha"),  # fecha de inicio
    _fk("dim_estado.sk_estado"),
    _fk("dim_persona_rol.sk_persona", nulo=True),  # consultor líder (D-12)
    _fk("dim_empresa.sk_empresa"),
    Column("valor_facturado", Numeric(14, 2)),
    Column("satisfaccion", Numeric(3, 1)),
    Column("n_consultores", Integer),
    Column("duracion_dias", Integer),
    _marca(),
    info={"tipo": INSTANTANEA_ACUMULATIVA, "col_tiempo": "sk_fecha", "grano": ("id_consultoria",)},
)

hecho_acceso_diario = Table(
    "hecho_acceso_diario",
    metadatos_ana,
    _fk("dim_tiempo.sk_fecha"),
    _fk("dim_persona_rol.sk_persona"),
    Column("n_accesos", Integer),
    Column("n_fallidos", Integer),
    Column("bloqueos", Integer),
    info={"tipo": TRANSACCION, "col_tiempo": "sk_fecha", "grano": ("sk_fecha", "sk_persona")},
)
hecho_acceso_diario.append_constraint(PrimaryKeyConstraint("sk_fecha", "sk_persona"))

# --- Agregados precalculados (4.3.2: «son las que consulta el motor para los informes más frecuentes») ----------

agg_facturacion_mes = Table(
    "agg_facturacion_mes",
    metadatos_ana,
    _fk("dim_tiempo.sk_fecha"),  # primer día del mes de la factura
    _fk("dim_empresa.sk_empresa"),
    Column("valor_facturado", Numeric(16, 2), nullable=False),
    Column("n_facturas", Integer, nullable=False),
    info={"tipo": AGREGADO, "col_tiempo": "sk_fecha", "grano": ("sk_fecha", "sk_empresa")},
    comment="Facturación por mes de factura y empresa (factura_consultoria). Figura 10.",
)
agg_facturacion_mes.append_constraint(PrimaryKeyConstraint("sk_fecha", "sk_empresa"))

agg_proyecto_linea_mes = Table(
    "agg_proyecto_linea_mes",
    metadatos_ana,
    _fk_como("sk_fecha_corte", "dim_tiempo.sk_fecha"),
    _fk("dim_linea_programa.sk_linea"),
    _fk("dim_estado.sk_estado"),
    Column("n_proyectos", Integer, nullable=False),
    Column("presupuesto_asignado", Numeric(16, 2)),
    Column("presupuesto_ejecutado", Numeric(16, 2)),
    Column("n_hitos", Integer),
    Column("n_hitos_atrasados", Integer),
    info={
        "tipo": INSTANTANEA_PERIODICA,
        "col_tiempo": "sk_fecha_corte",
        "grano": ("sk_linea", "sk_estado"),
        "agregado_de": "hecho_proyecto",
    },
    comment="Serie mensual de proyectos por línea y estado (resumen de hecho_proyecto).",
)
agg_proyecto_linea_mes.append_constraint(PrimaryKeyConstraint("sk_fecha_corte", "sk_linea", "sk_estado"))

# --- Control del ETL (4.3.2: cada ejecución registra filas leídas, cargadas y marcadas) -------------------------

etl_ejecucion = Table(
    "etl_ejecucion",
    metadatos_ana,
    Column("id_ejecucion", Integer, primary_key=True),
    Column("tabla_destino", String(60), nullable=False),
    Column("inicio", DateTime, nullable=False),
    Column("fin", DateTime, nullable=True),
    Column("modo", String(20), nullable=False),  # 'fecha_modificacion' | 'huella_fila' | 'completa'
    Column("filas_leidas", Integer, nullable=False, default=0),
    Column("filas_cargadas", Integer, nullable=False, default=0),
    Column("filas_marcadas", Integer, nullable=False, default=0),
    Column("error", String(500), nullable=True),
)

etl_marca_calidad = Table(
    "etl_marca_calidad",
    metadatos_ana,
    Column("id_marca", Integer, primary_key=True),
    Column("id_ejecucion", Integer, ForeignKey(f"{ESQUEMA_ANA}.etl_ejecucion.id_ejecucion"), nullable=False),
    Column("entidad", String(60), nullable=False),
    Column("id_origen", Integer, nullable=False),
    Column("regla", String(60), nullable=False),
    comment="Registros que fallan una regla de calidad (INF-TRA-08). No se descartan: se cargan marcados.",
)

etl_huella_fila = Table(
    "etl_huella_fila",
    metadatos_ana,
    Column("entidad", String(60), primary_key=True),
    Column("id_origen", Integer, primary_key=True, autoincrement=False),
    Column("huella", CHAR(64), nullable=False),
    comment="Huella de cada fila de origen para la carga incremental sin fecha de modificación (D-17).",
)

DIMENSIONES_DW = (
    dim_tiempo,
    dim_macroproyecto,
    dim_linea_programa,
    dim_estado,
    dim_persona_rol,
    dim_empresa,
    dim_tipo_convenio,
)
HECHOS_DW = (
    hecho_macroproyecto,
    hecho_proyecto,
    hecho_hito,
    hecho_practica,
    hecho_convenio,
    hecho_consultoria,
    hecho_acceso_diario,
)
AGREGADOS_DW = (agg_facturacion_mes, agg_proyecto_linea_mes)


def tabla(nombre: str) -> Table:
    """Devuelve la tabla `nombre` de `ana_`. Lanza KeyError si no está en la lista blanca."""
    return metadatos_ana.tables[f"{ESQUEMA_ANA}.{nombre}"]


def columna_fk_hacia(hecho: Table, dimension: Table) -> Column | None:
    """Columna de `hecho` que es clave foránea hacia `dimension` (cada hecho tiene a lo sumo una)."""
    for col in hecho.columns:
        for fk in col.foreign_keys:
            if fk.column.table is dimension:
                return col
    return None
