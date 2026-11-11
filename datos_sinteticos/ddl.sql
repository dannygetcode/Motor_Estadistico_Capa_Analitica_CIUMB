-- =====================================================================
-- Fuente 1 (BD transaccional del CIUMB) — MODELO INFERIDO
-- PROVISIONAL: nombres de tablas y columnas tomados de las Figuras 3–5 y
-- Tablas 10–12 del diseño (docs/diseno/4.2.1 y 4.2.2). El ER real no se ha
-- entregado; cuando llegue, cambian las vistas de src/ciumb_analitica/fuentes/,
-- no el datawarehouse.
--
-- Solo para desarrollo con datos sintéticos (PostgreSQL 16).
-- A propósito NO hay restricciones que impidan los defectos de calidad que
-- el ETL debe detectar (Tabla 13 / INF-TRA-08):
--   * sin CHECK fecha_fin >= fecha_inicio
--   * sin UNIQUE en empresa.nit
--   * tutores y empresa de la práctica admiten NULL
--   * los estados son texto libre (sin catálogo ni CHECK)
--   * presupuesto_ejecutado admite negativos
-- Las columnas marcadas PII existen aquí porque existen en la fuente; el ETL
-- nunca las extrae (invariante 5).
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS ciumb;
SET search_path TO ciumb;

-- ---------------------------------------------------------------------
-- Área de usuarios y seguridad (Módulo 7, Figura 5)
-- ---------------------------------------------------------------------
CREATE TABLE rol (
    id_rol              INTEGER PRIMARY KEY,
    nombre_rol          VARCHAR(60)  NOT NULL,
    alcance_modulos     VARCHAR(200)                 -- PROVISIONAL: lista de módulos separada por comas
);

CREATE TABLE usuario (
    id_usuario              INTEGER PRIMARY KEY,
    id_rol                  INTEGER NOT NULL REFERENCES rol (id_rol),
    nombre_completo         VARCHAR(150),            -- PII: no se extrae
    documento               VARCHAR(20),             -- PII: no se extrae
    correo                  VARCHAR(150),            -- PII: no se extrae
    contrasena_hash         VARCHAR(200),            -- Credencial: jamás se lee
    estado                  VARCHAR(30),
    fecha_creacion          DATE,
    ultimo_acceso           TIMESTAMP,
    fecha_vence_contrasena  DATE
);

CREATE TABLE registro_acceso (
    id_acceso           INTEGER PRIMARY KEY,
    id_usuario          INTEGER NOT NULL REFERENCES usuario (id_usuario),
    fecha_hora          TIMESTAMP NOT NULL,
    exitoso             BOOLEAN NOT NULL,
    bloqueo_generado    BOOLEAN NOT NULL DEFAULT FALSE
);

-- ---------------------------------------------------------------------
-- Área de investigación (Figura 3, Tabla 10)
-- ---------------------------------------------------------------------
CREATE TABLE facultad_programa (
    id_programa         INTEGER PRIMARY KEY,
    nombre_programa     VARCHAR(150) NOT NULL,
    facultad            VARCHAR(150) NOT NULL
);

CREATE TABLE linea_investigacion (
    id_linea            INTEGER PRIMARY KEY,
    nombre              VARCHAR(150) NOT NULL,
    id_programa         INTEGER REFERENCES facultad_programa (id_programa)
);

CREATE TABLE macroproyecto (
    id_macroproyecto    INTEGER PRIMARY KEY,
    nombre              VARCHAR(250) NOT NULL,       -- institucional: no viaja a la IA
    estado              VARCHAR(30),
    id_coordinador      INTEGER REFERENCES usuario (id_usuario),
    id_programa         INTEGER REFERENCES facultad_programa (id_programa),
    fecha_inicio        DATE,
    fecha_fin_planeada  DATE,
    fecha_fin_real      DATE,
    porcentaje_avance   NUMERIC(5, 2)
);

CREATE TABLE fase_macroproyecto (
    id_fase             INTEGER PRIMARY KEY,
    id_macroproyecto    INTEGER NOT NULL REFERENCES macroproyecto (id_macroproyecto),
    nombre_fase         VARCHAR(150),
    avance              NUMERIC(5, 2),
    fecha_fin_planeada  DATE,
    fecha_fin_real      DATE
);

CREATE TABLE proyecto_investigacion (
    id_proyecto             INTEGER PRIMARY KEY,
    id_macroproyecto        INTEGER REFERENCES macroproyecto (id_macroproyecto),
    id_linea                INTEGER REFERENCES linea_investigacion (id_linea),
    titulo                  VARCHAR(300),            -- institucional: no viaja a la IA
    estado                  VARCHAR(30),
    fecha_creacion          DATE,
    fecha_validacion        DATE,
    fecha_aprobacion        DATE,
    fecha_inicio            DATE,
    fecha_fin               DATE,
    presupuesto_asignado    NUMERIC(14, 2),
    presupuesto_ejecutado   NUMERIC(14, 2),
    fecha_modificacion      TIMESTAMP                -- SUPUESTO (no está en la Figura 3): prueba la carga incremental
);

CREATE TABLE hito_entregable (
    id_hito             INTEGER PRIMARY KEY,
    id_proyecto         INTEGER NOT NULL REFERENCES proyecto_investigacion (id_proyecto),
    tipo                VARCHAR(60),
    fecha_planeada      DATE,
    fecha_real          DATE,
    estado              VARCHAR(30)
);

CREATE TABLE integrante_proyecto (
    id_proyecto         INTEGER NOT NULL REFERENCES proyecto_investigacion (id_proyecto),
    id_usuario          INTEGER NOT NULL REFERENCES usuario (id_usuario),
    rol_en_proyecto     VARCHAR(60),
    PRIMARY KEY (id_proyecto, id_usuario)
);

-- ---------------------------------------------------------------------
-- Área de relación externa (Figura 4, Tabla 11)
-- ---------------------------------------------------------------------
CREATE TABLE empresa (
    id_empresa          INTEGER PRIMARY KEY,
    nit                 VARCHAR(20),                 -- PII*: solo se extrae como hash; SIN UNIQUE a propósito
    razon_social        VARCHAR(200),
    sector              VARCHAR(80),
    ciudad              VARCHAR(80),
    tipo                VARCHAR(40),
    fecha_registro      DATE,
    estado              VARCHAR(30)
);

CREATE TABLE convenio (
    id_convenio             INTEGER PRIMARY KEY,
    id_empresa              INTEGER NOT NULL REFERENCES empresa (id_empresa),
    tipo                    VARCHAR(40),             -- marco | especifico | cooperacion (Figura 7)
    fecha_firma             DATE,
    fecha_inicio            DATE,
    fecha_fin               DATE,                    -- admite NULL (defecto: convenio sin fecha de fin)
    id_convenio_anterior    INTEGER REFERENCES convenio (id_convenio),
    estado                  VARCHAR(30)
);

CREATE TABLE documento_convenio (
    id_documento        INTEGER PRIMARY KEY,
    id_convenio         INTEGER NOT NULL REFERENCES convenio (id_convenio),
    tipo_documento      VARCHAR(80),
    cargado             BOOLEAN NOT NULL
);

CREATE TABLE practica (
    id_practica             INTEGER PRIMARY KEY,
    id_estudiante           INTEGER REFERENCES usuario (id_usuario),   -- SUPUESTO: el estudiante es un usuario
    id_empresa              INTEGER REFERENCES empresa (id_empresa),   -- admite NULL (defecto)
    id_convenio             INTEGER REFERENCES convenio (id_convenio),
    id_macroproyecto        INTEGER REFERENCES macroproyecto (id_macroproyecto),
    id_programa             INTEGER REFERENCES facultad_programa (id_programa),
    id_tutor_academico      INTEGER REFERENCES usuario (id_usuario),   -- admite NULL (defecto)
    id_tutor_empresarial    INTEGER REFERENCES usuario (id_usuario),   -- admite NULL (defecto)
    periodo                 VARCHAR(10),             -- p. ej. 2026-2
    estado                  VARCHAR(30),
    fecha_inicio            DATE,
    fecha_fin               DATE,
    tareas_asignadas        INTEGER,
    tareas_cumplidas        INTEGER,
    fecha_modificacion      TIMESTAMP                -- SUPUESTO (no está en la Figura 4): prueba la carga incremental
);

CREATE TABLE consultoria (
    id_consultoria              INTEGER PRIMARY KEY,
    id_empresa                  INTEGER NOT NULL REFERENCES empresa (id_empresa),
    id_convenio                 INTEGER REFERENCES convenio (id_convenio),
    estado                      VARCHAR(30),
    fecha_inicio                DATE,
    fecha_fin                   DATE,
    valor_contratado            NUMERIC(14, 2),
    calificacion_satisfaccion   NUMERIC(3, 1)
);

CREATE TABLE factura_consultoria (
    id_factura          INTEGER PRIMARY KEY,
    id_consultoria      INTEGER NOT NULL REFERENCES consultoria (id_consultoria),
    fecha_factura       DATE,
    valor               NUMERIC(14, 2)
);

CREATE TABLE consultor_consultoria (
    id_consultoria      INTEGER NOT NULL REFERENCES consultoria (id_consultoria),
    id_usuario          INTEGER NOT NULL REFERENCES usuario (id_usuario),
    rol                 VARCHAR(60),
    PRIMARY KEY (id_consultoria, id_usuario)
);
