# Índice del documento de diseño

Generado desde `docs/fuentes/*.docx` con `herramientas/dividir_diseno.py` (no editar a mano los .md de
sección: regenerar). Las descripciones de figuras (bloques `>`) salen de
`herramientas/figuras_descripciones.json`. Lee **solo** el archivo que la tarea necesita.

Leyenda: ★ = lectura frecuente durante la construcción · (T) = marco teórico, rara vez necesario.

## Portada y capítulo 1 — Introducción
- `00_portada.md` — portada, tabla de contenido, listas de tablas y figuras. Casi nunca.
- `1_introduccion.md` — contexto de la práctica; Tabla 1 (articulación con áreas del programa). Para la memoria, no para código.
- `1.1_definicion_problema.md` — problema y pregunta de investigación; Figura 1 (espina de pescado). Para justificar decisiones.
- `1.2_justificacion.md` — por qué IA + cálculo determinista. Para la sustentación.
- `1.3_objetivo_general.md` — objetivo general.
- ★ `1.4_objetivos_especificos.md` — OE1–OE5; Tabla 2 (indicadores y metas). Al definir criterios de evaluación (Sprint 4).
- `1.5.1_tipo_proyecto_enfoque.md` — tipo de proyecto y enfoque.
- `1.5.2_modelo_proceso.md` — CRISP-DM por sprint; Tabla 3. Al planear sprints.
- `1.5.3_fuentes_informacion_tecnicas_recoleccion.md` — fuentes de información del proyecto.
- ★ `1.5.4_criterios_validacion.md` — cómo se valida el sistema (contraste con SciPy/statsmodels, exactitud). Al escribir pruebas de aceptación.
- `1.5.5_consideraciones_eticas_legales.md` — Ley 1581, habeas data. Al tocar PII.

## Capítulo 2 — Marco teórico (T)
- `2_marco_teorico.md` — introducción del capítulo.
- `2.1_definicion_big_data.md` — definición de Big Data.
- `2.2_tipos_datos.md`, `2.2.1_datos_estructurados.md`, `2.2.2_datos_semiestructurados.md`, `2.2.3_datos_no_estructurados.md` — tipos de datos; Tabla 4 (tipos presentes en el proyecto y su tratamiento).
- `2.3_caracteristicas_big_data.md`, `2.3.1_volumen.md` … `2.3.5_valor.md` — las cinco V; Tabla 5 (aplicadas al CIUMB).
- `2.4_big_data_analytics.md`, `2.4.1_adquisicion_datos.md` … `2.4.4_decision.md` — ciclo adquisición → organización → análisis → decisión (base de la Figura 2).
- `2.5_areas_analisis_datos.md`, `2.5.1_…` … `2.5.6_analitica_m2m_machine_to_machine.md` — áreas de analítica; Tabla 6 (relación con el proyecto).
- `2.6_analitica_social.md`, `2.6.1_social_media.md` … `2.6.4_…` — analítica social (fuera de alcance del motor).
- `2.7_arquitectura_big_data.md` — arquitectura de referencia NIST (base de la Figura 9).
- `2.8_herramientas_teoricas_dan_soporte_tecnologias.md`, `2.8.1_google_file_system_gfs.md`, `2.8.2_mapreduce.md`, `2.8.3_bigtable.md` — GFS, MapReduce, Bigtable; Tabla 7 (equivalente en el diseño).

## Capítulo 3 — Técnicas y tecnologías
- `3_tecnicas_tecnologias.md` — introducción del capítulo.
- ★ `3.1_mineria_datos.md` — **Tabla 8: técnicas estadísticas y de minería del área analítica** (métodos, supuestos, librería). Al implementar `motor/` y `ml/`.
- `3.2_mineria_opinion.md`, `3.3_microblogging.md`, `3.4_twitter.md`, `3.5_analisis_sentimientos_twitter.md` — (T) minería de opinión, fuera de alcance.
- `3.6_facebook.md` — Facebook; Tabla 9 (aplicabilidad de las técnicas al proyecto). Explica por qué redes sociales quedan fuera.

## Capítulo 4 — Análisis y diseño (el núcleo para construir)
- `4_analisis_diseno_estructuras_datos.md` — introducción del capítulo.
- ★ `4.1_diagrama_bloques_desarrollo_proyecto.md` — Figura 2: bloques del área analítica (mapa de paquetes de CLAUDE.md). Al ubicar un componente.
- ★ `4.2_modelo_datos_fuentes.md` — fuentes 1 (BD CIUMB) y 2 (esquema rpt_); aclaración de que el ER es **inferido**.
- ★ `4.2.1_diagrama_modelo_cada_fuente.md` — Figuras 3–6: ER inferido (investigación, relación externa, usuarios) y esquema rpt_ con todos sus campos. Al tocar `fuentes/`, `datos_sinteticos/`, `trazabilidad/`, `semantica/`.
- ★ `4.2.2_descripcion_modelo.md` — Tablas 10–12 (entidades e informes que alimentan), **Tabla 13 (campos sensibles y tratamiento en ETL)** y reglas de calidad. Al tocar `etl/` o PII.
- ★ `4.3.1_diagrama_datawarehouse.md` — Figuras 7–8: constelación de hechos de ana_ y estrella de hecho_proyecto. Al tocar `dw/`.
- ★ `4.3.2_descripcion_datawarehouse.md` — Tabla 14 (DA-01), **Tabla 15 (matriz de bus)**, Tabla 16 (dimensiones), Tabla 17 (grano de hechos), carga nocturna. Al tocar `dw/`, `etl/`, `semantica/` (compatibilidad).
- `4.4_diagrama_arquitectura_general.md` — introducción de la arquitectura.
- ★ `4.4.1_componentes_decisiones_arquitectura.md` — Figura 9 (despliegue, endpoints), Tabla 18 (DA-01…DA-09), **Tabla 19 (tecnologías permitidas)**. Antes de agregar una dependencia o una ruta.
- ★ `4.4.2_especificacion_abierta_informes.md` — Figura 10, **Tabla 20 (campos ciumb.spec/1.0)**, capa semántica, validador de 7 pasos, **Tabla 21 (gráficos)**, compilador, plantillas base. Al tocar `spec/`, `semantica/`, `compilador/`, `graficos/`.
- ★ `4.4.3_flujo_solicitud_contrato_datos_validador.md` — Figura 11 (secuencia), Figura 12 (contrato 2.0.0), algoritmo del validador de cifras (6 pasos), seguridad. Al tocar `contrato/`, `validador_cifras/`, `api/`.
- ★ `4.4.4_prompts_ejemplo.md` — **Tabla 22 (P1–P10)** y Figuras 13–15 (specs). Pruebas de aceptación. JSON en `schemas/ejemplos/`.
- `4.5_diseno_dashboard.md` — Tabla 23 (pantallas y requerimientos) y Figuras 16–20 (mockups). Al definir qué devuelve la API para la UI y en `exportacion/`.

## Referencias
- `99_referencias.md` — bibliografía (APA). Al citar en la memoria.

## Figuras
`figuras/figura_NN.png` (1–20) y `figuras/imagen_sin_leyenda_1.png` (logo de portada).
