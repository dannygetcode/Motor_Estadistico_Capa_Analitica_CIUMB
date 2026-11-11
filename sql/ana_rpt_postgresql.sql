-- =====================================================================
-- Esquemas ana_ (datawarehouse) y rpt_ (servicio de informes) - PostgreSQL
-- GENERADO por `uv run python -m ciumb_analitica.dw.ddl`. No editar a mano:
-- la fuente son src/ciumb_analitica/dw/esquema.py y trazabilidad/esquema.py.
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS ana_;
CREATE SCHEMA IF NOT EXISTS rpt_;

CREATE TABLE ana_.dim_empresa (
	sk_empresa SERIAL NOT NULL, 
	id_origen INTEGER NOT NULL, 
	sector VARCHAR(80), 
	ciudad VARCHAR(80), 
	tipo VARCHAR(40), 
	segmento_actividad VARCHAR(40), 
	nit_hash CHAR(64), 
	PRIMARY KEY (sk_empresa)
);

CREATE TABLE ana_.dim_estado (
	sk_estado SERIAL NOT NULL, 
	modulo VARCHAR(40) NOT NULL, 
	estado VARCHAR(30) NOT NULL, 
	es_final SMALLINT NOT NULL, 
	PRIMARY KEY (sk_estado)
);

CREATE TABLE ana_.dim_linea_programa (
	sk_linea SERIAL NOT NULL, 
	id_linea_origen INTEGER, 
	id_programa_origen INTEGER NOT NULL, 
	linea_investigacion VARCHAR(150) NOT NULL, 
	programa VARCHAR(150) NOT NULL, 
	facultad VARCHAR(150) NOT NULL, 
	PRIMARY KEY (sk_linea)
);

CREATE TABLE ana_.dim_persona_rol (
	sk_persona SERIAL NOT NULL, 
	seudonimo CHAR(64) NOT NULL, 
	rol VARCHAR(60) NOT NULL, 
	tipo_participacion VARCHAR(60) NOT NULL, 
	PRIMARY KEY (sk_persona)
);

CREATE TABLE ana_.dim_tiempo (
	sk_fecha INTEGER NOT NULL, 
	fecha DATE NOT NULL, 
	dia SMALLINT NOT NULL, 
	mes SMALLINT NOT NULL, 
	nombre_mes VARCHAR(12) NOT NULL, 
	trimestre SMALLINT NOT NULL, 
	semestre SMALLINT NOT NULL, 
	anio SMALLINT NOT NULL, 
	periodo_academico VARCHAR(6) NOT NULL, 
	PRIMARY KEY (sk_fecha), 
	UNIQUE (fecha)
);

CREATE TABLE ana_.dim_tipo_convenio (
	sk_tipo_convenio SERIAL NOT NULL, 
	tipo_convenio VARCHAR(40) NOT NULL, 
	PRIMARY KEY (sk_tipo_convenio)
);

CREATE TABLE ana_.etl_ejecucion (
	id_ejecucion SERIAL NOT NULL, 
	tabla_destino VARCHAR(60) NOT NULL, 
	inicio TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	fin TIMESTAMP WITHOUT TIME ZONE, 
	modo VARCHAR(20) NOT NULL, 
	filas_leidas INTEGER NOT NULL, 
	filas_cargadas INTEGER NOT NULL, 
	filas_marcadas INTEGER NOT NULL, 
	error VARCHAR(500), 
	PRIMARY KEY (id_ejecucion)
);

CREATE TABLE ana_.etl_huella_fila (
	entidad VARCHAR(60) NOT NULL, 
	id_origen INTEGER NOT NULL, 
	huella CHAR(64) NOT NULL, 
	PRIMARY KEY (entidad, id_origen)
);

CREATE TABLE ana_.agg_facturacion_mes (
	sk_fecha INTEGER NOT NULL, 
	sk_empresa INTEGER NOT NULL, 
	valor_facturado NUMERIC(16, 2) NOT NULL, 
	n_facturas INTEGER NOT NULL, 
	PRIMARY KEY (sk_fecha, sk_empresa), 
	FOREIGN KEY(sk_fecha) REFERENCES ana_.dim_tiempo (sk_fecha), 
	FOREIGN KEY(sk_empresa) REFERENCES ana_.dim_empresa (sk_empresa)
);

CREATE TABLE ana_.agg_proyecto_linea_mes (
	sk_fecha_corte INTEGER NOT NULL, 
	sk_linea INTEGER NOT NULL, 
	sk_estado INTEGER NOT NULL, 
	n_proyectos INTEGER NOT NULL, 
	presupuesto_asignado NUMERIC(16, 2), 
	presupuesto_ejecutado NUMERIC(16, 2), 
	n_hitos INTEGER, 
	n_hitos_atrasados INTEGER, 
	PRIMARY KEY (sk_fecha_corte, sk_linea, sk_estado), 
	FOREIGN KEY(sk_fecha_corte) REFERENCES ana_.dim_tiempo (sk_fecha), 
	FOREIGN KEY(sk_linea) REFERENCES ana_.dim_linea_programa (sk_linea), 
	FOREIGN KEY(sk_estado) REFERENCES ana_.dim_estado (sk_estado)
);

CREATE TABLE ana_.dim_macroproyecto (
	sk_macroproyecto SERIAL NOT NULL, 
	id_origen INTEGER NOT NULL, 
	nombre VARCHAR(250) NOT NULL, 
	estado_actual VARCHAR(30) NOT NULL, 
	sk_coordinador INTEGER, 
	vigente_desde DATE NOT NULL, 
	vigente_hasta DATE, 
	PRIMARY KEY (sk_macroproyecto), 
	FOREIGN KEY(sk_coordinador) REFERENCES ana_.dim_persona_rol (sk_persona)
);

CREATE TABLE ana_.etl_marca_calidad (
	id_marca SERIAL NOT NULL, 
	id_ejecucion INTEGER NOT NULL, 
	entidad VARCHAR(60) NOT NULL, 
	id_origen INTEGER NOT NULL, 
	regla VARCHAR(60) NOT NULL, 
	PRIMARY KEY (id_marca), 
	FOREIGN KEY(id_ejecucion) REFERENCES ana_.etl_ejecucion (id_ejecucion)
);

CREATE TABLE ana_.hecho_acceso_diario (
	sk_fecha INTEGER NOT NULL, 
	sk_persona INTEGER NOT NULL, 
	n_accesos INTEGER, 
	n_fallidos INTEGER, 
	bloqueos INTEGER, 
	PRIMARY KEY (sk_fecha, sk_persona), 
	FOREIGN KEY(sk_fecha) REFERENCES ana_.dim_tiempo (sk_fecha), 
	FOREIGN KEY(sk_persona) REFERENCES ana_.dim_persona_rol (sk_persona)
);

CREATE TABLE ana_.hecho_consultoria (
	id_consultoria INTEGER NOT NULL, 
	sk_fecha INTEGER NOT NULL, 
	sk_estado INTEGER NOT NULL, 
	sk_persona INTEGER, 
	sk_empresa INTEGER NOT NULL, 
	valor_facturado NUMERIC(14, 2), 
	satisfaccion NUMERIC(3, 1), 
	n_consultores INTEGER, 
	duracion_dias INTEGER, 
	marca_calidad VARCHAR(200), 
	PRIMARY KEY (id_consultoria), 
	FOREIGN KEY(sk_fecha) REFERENCES ana_.dim_tiempo (sk_fecha), 
	FOREIGN KEY(sk_estado) REFERENCES ana_.dim_estado (sk_estado), 
	FOREIGN KEY(sk_persona) REFERENCES ana_.dim_persona_rol (sk_persona), 
	FOREIGN KEY(sk_empresa) REFERENCES ana_.dim_empresa (sk_empresa)
);

CREATE TABLE ana_.hecho_convenio (
	sk_fecha_corte INTEGER NOT NULL, 
	id_convenio INTEGER NOT NULL, 
	sk_estado INTEGER NOT NULL, 
	sk_empresa INTEGER NOT NULL, 
	sk_tipo_convenio INTEGER NOT NULL, 
	duracion_dias INTEGER, 
	dias_para_vencer INTEGER, 
	renovado SMALLINT, 
	docs_completos SMALLINT, 
	n_actividades INTEGER, 
	marca_calidad VARCHAR(200), 
	PRIMARY KEY (sk_fecha_corte, id_convenio), 
	FOREIGN KEY(sk_fecha_corte) REFERENCES ana_.dim_tiempo (sk_fecha), 
	FOREIGN KEY(sk_estado) REFERENCES ana_.dim_estado (sk_estado), 
	FOREIGN KEY(sk_empresa) REFERENCES ana_.dim_empresa (sk_empresa), 
	FOREIGN KEY(sk_tipo_convenio) REFERENCES ana_.dim_tipo_convenio (sk_tipo_convenio)
);

CREATE TABLE ana_.hecho_hito (
	id_hito INTEGER NOT NULL, 
	id_proyecto INTEGER NOT NULL, 
	sk_fecha_planeada INTEGER NOT NULL, 
	sk_estado INTEGER NOT NULL, 
	dias_retraso INTEGER, 
	a_tiempo SMALLINT, 
	marca_calidad VARCHAR(200), 
	PRIMARY KEY (id_hito), 
	FOREIGN KEY(sk_fecha_planeada) REFERENCES ana_.dim_tiempo (sk_fecha), 
	FOREIGN KEY(sk_estado) REFERENCES ana_.dim_estado (sk_estado)
);

CREATE TABLE ana_.hecho_macroproyecto (
	sk_fecha_corte INTEGER NOT NULL, 
	sk_macroproyecto INTEGER NOT NULL, 
	sk_estado INTEGER NOT NULL, 
	pct_avance NUMERIC(5, 2), 
	desviacion_dias INTEGER, 
	n_proyectos INTEGER, 
	n_practicas INTEGER, 
	marca_calidad VARCHAR(200), 
	PRIMARY KEY (sk_fecha_corte, sk_macroproyecto), 
	FOREIGN KEY(sk_fecha_corte) REFERENCES ana_.dim_tiempo (sk_fecha), 
	FOREIGN KEY(sk_macroproyecto) REFERENCES ana_.dim_macroproyecto (sk_macroproyecto), 
	FOREIGN KEY(sk_estado) REFERENCES ana_.dim_estado (sk_estado)
);

CREATE TABLE ana_.hecho_practica (
	id_practica INTEGER NOT NULL, 
	sk_fecha INTEGER NOT NULL, 
	sk_macroproyecto INTEGER, 
	sk_linea INTEGER, 
	sk_estado INTEGER NOT NULL, 
	sk_persona INTEGER, 
	sk_empresa INTEGER, 
	seudonimo_estudiante CHAR(64), 
	duracion_dias INTEGER, 
	tareas_asignadas INTEGER, 
	tareas_cumplidas INTEGER, 
	finalizada SMALLINT, 
	marca_calidad VARCHAR(200), 
	PRIMARY KEY (id_practica), 
	FOREIGN KEY(sk_fecha) REFERENCES ana_.dim_tiempo (sk_fecha), 
	FOREIGN KEY(sk_macroproyecto) REFERENCES ana_.dim_macroproyecto (sk_macroproyecto), 
	FOREIGN KEY(sk_linea) REFERENCES ana_.dim_linea_programa (sk_linea), 
	FOREIGN KEY(sk_estado) REFERENCES ana_.dim_estado (sk_estado), 
	FOREIGN KEY(sk_persona) REFERENCES ana_.dim_persona_rol (sk_persona), 
	FOREIGN KEY(sk_empresa) REFERENCES ana_.dim_empresa (sk_empresa)
);

CREATE TABLE ana_.hecho_proyecto (
	sk_fecha_corte INTEGER NOT NULL, 
	id_proyecto INTEGER NOT NULL, 
	sk_macroproyecto INTEGER, 
	sk_linea INTEGER, 
	sk_estado INTEGER NOT NULL, 
	presupuesto_asignado NUMERIC(14, 2), 
	presupuesto_ejecutado NUMERIC(14, 2), 
	pct_ejecucion NUMERIC(7, 2), 
	n_integrantes INTEGER, 
	n_hitos INTEGER, 
	n_hitos_atrasados INTEGER, 
	dias_retraso_promedio NUMERIC(8, 2), 
	dias_creacion_aprobacion INTEGER, 
	marca_calidad VARCHAR(200), 
	PRIMARY KEY (sk_fecha_corte, id_proyecto), 
	FOREIGN KEY(sk_fecha_corte) REFERENCES ana_.dim_tiempo (sk_fecha), 
	FOREIGN KEY(sk_macroproyecto) REFERENCES ana_.dim_macroproyecto (sk_macroproyecto), 
	FOREIGN KEY(sk_linea) REFERENCES ana_.dim_linea_programa (sk_linea), 
	FOREIGN KEY(sk_estado) REFERENCES ana_.dim_estado (sk_estado)
);

CREATE TABLE rpt_.rpt_alerta (
	id_alerta SERIAL NOT NULL, 
	codigo_regla VARCHAR(40) NOT NULL, 
	entidad VARCHAR(60) NOT NULL, 
	valor NUMERIC(16, 4), 
	umbral NUMERIC(16, 4), 
	estado VARCHAR(20) NOT NULL, 
	fecha TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id_alerta)
);

CREATE TABLE rpt_.rpt_dimension (
	id_dimension SERIAL NOT NULL, 
	codigo VARCHAR(60) NOT NULL, 
	nombre VARCHAR(150) NOT NULL, 
	descripcion VARCHAR(400) NOT NULL, 
	sinonimos_json TEXT NOT NULL, 
	tabla_columna VARCHAR(120), 
	tipo VARCHAR(20) NOT NULL, 
	identifica_persona BOOLEAN NOT NULL, 
	viaja_a_ia BOOLEAN NOT NULL, 
	binaria_de_metrica VARCHAR(60), 
	PRIMARY KEY (id_dimension), 
	UNIQUE (codigo)
);

CREATE TABLE rpt_.rpt_metrica (
	id_metrica SERIAL NOT NULL, 
	codigo VARCHAR(60) NOT NULL, 
	nombre VARCHAR(150) NOT NULL, 
	descripcion VARCHAR(400) NOT NULL, 
	sinonimos_json TEXT NOT NULL, 
	hecho_o_agregado VARCHAR(60) NOT NULL, 
	expresion_sql VARCHAR(200) NOT NULL, 
	agregaciones VARCHAR(100) NOT NULL, 
	agregacion_defecto VARCHAR(20) NOT NULL, 
	aditividad VARCHAR(20) NOT NULL, 
	unidad VARCHAR(40) NOT NULL, 
	columna_personas VARCHAR(60), 
	agregados_json TEXT NOT NULL, 
	activa BOOLEAN NOT NULL, 
	PRIMARY KEY (id_metrica), 
	UNIQUE (codigo)
);

CREATE TABLE rpt_.rpt_plantilla (
	id_plantilla SERIAL NOT NULL, 
	codigo_informe VARCHAR(12) NOT NULL, 
	nombre VARCHAR(200) NOT NULL, 
	spec_json TEXT NOT NULL, 
	version INTEGER NOT NULL, 
	roles_permitidos VARCHAR(200) NOT NULL, 
	activa BOOLEAN NOT NULL, 
	PRIMARY KEY (id_plantilla), 
	UNIQUE (codigo_informe)
);

CREATE TABLE rpt_.rpt_proveedor_ia (
	id_proveedor SERIAL NOT NULL, 
	nombre VARCHAR(60) NOT NULL, 
	modelo VARCHAR(100) NOT NULL, 
	prioridad INTEGER NOT NULL, 
	estado VARCHAR(20) NOT NULL, 
	PRIMARY KEY (id_proveedor)
);

CREATE TABLE rpt_.rpt_compatibilidad (
	id_metrica INTEGER NOT NULL, 
	id_dimension INTEGER NOT NULL, 
	PRIMARY KEY (id_metrica, id_dimension), 
	FOREIGN KEY(id_metrica) REFERENCES rpt_.rpt_metrica (id_metrica), 
	FOREIGN KEY(id_dimension) REFERENCES rpt_.rpt_dimension (id_dimension)
);

CREATE TABLE rpt_.rpt_especificacion (
	id_especificacion SERIAL NOT NULL, 
	id_plantilla INTEGER, 
	esquema_version VARCHAR(20) NOT NULL, 
	origen VARCHAR(20) NOT NULL, 
	spec_json TEXT NOT NULL, 
	huella_spec CHAR(64) NOT NULL, 
	estado_validacion VARCHAR(20) NOT NULL, 
	motivo VARCHAR(500), 
	fecha_registro TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id_especificacion), 
	FOREIGN KEY(id_plantilla) REFERENCES rpt_.rpt_plantilla (id_plantilla)
);

CREATE TABLE rpt_.rpt_narrativa_cache (
	huella_entrada CHAR(64) NOT NULL, 
	texto_json TEXT NOT NULL, 
	id_proveedor INTEGER, 
	fecha TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (huella_entrada), 
	FOREIGN KEY(id_proveedor) REFERENCES rpt_.rpt_proveedor_ia (id_proveedor)
);

CREATE TABLE rpt_.rpt_programacion (
	id_programacion SERIAL NOT NULL, 
	id_especificacion INTEGER NOT NULL, 
	periodicidad VARCHAR(20) NOT NULL, 
	destinatarios_rol VARCHAR(200) NOT NULL, 
	activa BOOLEAN NOT NULL, 
	PRIMARY KEY (id_programacion), 
	FOREIGN KEY(id_especificacion) REFERENCES rpt_.rpt_especificacion (id_especificacion)
);

CREATE TABLE rpt_.rpt_solicitud (
	id_solicitud SERIAL NOT NULL, 
	id_especificacion INTEGER, 
	id_usuario CHAR(64) NOT NULL, 
	prompt_texto TEXT, 
	fecha_corte DATE, 
	estado VARCHAR(20) NOT NULL, 
	fecha_solicitud TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id_solicitud), 
	FOREIGN KEY(id_especificacion) REFERENCES rpt_.rpt_especificacion (id_especificacion)
);

CREATE TABLE rpt_.rpt_resultado (
	id_resultado SERIAL NOT NULL, 
	id_solicitud INTEGER NOT NULL, 
	formato VARCHAR(10) NOT NULL, 
	huella_datos CHAR(64) NOT NULL, 
	sql_compilado TEXT NOT NULL, 
	ruta_archivo VARCHAR(300), 
	modo VARCHAR(20) NOT NULL, 
	fecha_generacion TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id_resultado), 
	FOREIGN KEY(id_solicitud) REFERENCES rpt_.rpt_solicitud (id_solicitud)
);

CREATE TABLE rpt_.rpt_uso_ia (
	id_uso SERIAL NOT NULL, 
	id_proveedor INTEGER NOT NULL, 
	id_solicitud INTEGER NOT NULL, 
	tarea VARCHAR(30) NOT NULL, 
	tokens INTEGER, 
	latencia_ms INTEGER, 
	error VARCHAR(300), 
	fecha TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id_uso), 
	FOREIGN KEY(id_proveedor) REFERENCES rpt_.rpt_proveedor_ia (id_proveedor), 
	FOREIGN KEY(id_solicitud) REFERENCES rpt_.rpt_solicitud (id_solicitud)
);

CREATE TABLE rpt_.rpt_validacion (
	id_validacion SERIAL NOT NULL, 
	id_resultado INTEGER NOT NULL, 
	cifras_texto INTEGER NOT NULL, 
	cifras_discrepantes INTEGER NOT NULL, 
	regeneraciones INTEGER NOT NULL, 
	uso_plantilla BOOLEAN NOT NULL, 
	fecha TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id_validacion), 
	FOREIGN KEY(id_resultado) REFERENCES rpt_.rpt_resultado (id_resultado)
);


-- ---------------------------------------------------------------------
-- Usuario de solo lectura del motor (invariante 3): solo SELECT y solo sobre ana_.
-- El rol se crea sin contraseña; se asigna fuera de git:
--   ALTER ROLE ciumb_lector LOGIN PASSWORD '...';
-- ---------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ciumb_lector') THEN
        CREATE ROLE ciumb_lector NOLOGIN;
    END IF;
END
$$;
REVOKE ALL ON SCHEMA rpt_ FROM ciumb_lector;
GRANT USAGE ON SCHEMA ana_ TO ciumb_lector;
GRANT SELECT ON ALL TABLES IN SCHEMA ana_ TO ciumb_lector;
ALTER DEFAULT PRIVILEGES IN SCHEMA ana_ GRANT SELECT ON TABLES TO ciumb_lector;
ALTER ROLE ciumb_lector SET default_transaction_read_only = on;
ALTER ROLE ciumb_lector SET statement_timeout = '30s';
