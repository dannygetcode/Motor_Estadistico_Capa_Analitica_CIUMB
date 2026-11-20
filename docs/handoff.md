# Relevo entre sesiones

## Estado al cierre de la sesión 2 (2026-11-19)
Rama de trabajo: `feat/motor-ml-graficos-contrato-etl-exportacion-api` (sin commit: pendiente de revisión de
Daniel). Windows: `uv run python -m pytest` -> **700 en verde, 1 omitida** (PDF, falta GTK). Linux (Docker):
**701 en verde, sin omitidas**. `uv run ruff check .`: limpio. Única interfaz cerrada tocada, con aprobación:
constante `PRONOSTICO_SIN_MEJORA` en `spec/resultado.py` (D-24).

### Validado en Docker + PostgreSQL 16 (D-32)
- Contenedor `ciumb_db` recreado sobre su volumen; `ana_` y `rpt_` aplicados; `ciumb_lector` con LOGIN.
- `python -m ciumb_analitica.etl --historico 2019-01`: sin errores, 94 cortes, marcas = defectos sembrados.
- Imagen `ciumb-analitica:dev` (`Dockerfile`): P1–P10 por HTTP con token; 9 PDF descargados; sin token -> 401.

### Hecho en la sesión 2 (historias 1 a 13 del relevo anterior)
| # | Historia | Módulo | Pruebas |
|---|---|---|---|
| 1–3 | Descriptiva, series, inferencia | `motor/descriptiva.py`, `series.py`, `inferencia.py` | contra NumPy y SciPy |
| 4–6 | Atípicos, pronóstico, segmentación | `ml/` | contra SciPy, statsmodels, scikit-learn |
| 7 | Gráficos (6 tipos) | `graficos/generador.py`, `exportacion/identidad.py` | PNG determinista + Plotly |
| 8 | Empaquetador del contrato | `contrato/empaquetador.py` | Figura 12 reproducida |
| 9 | Vistas de extracción | `fuentes/vistas.py` (`metadatos_fuente` = lista blanca) | sin campos sensibles |
| 10 | Reglas de calidad | `etl/calidad.py` | defectos sembrados exactos |
| 11 | Carga incremental y ETL | `etl/carga.py`, `etl/programacion.py` | `tests/etl/test_integracion.py` (SQLite) |
| 12 | Exportación | `exportacion/exportador.py` | DOCX, XLSX, HTML, CSV (PDF omitida) |
| 13 | Orquestación y API | `motor/analisis.py`, `api/flujo.py`, `api/servicio.py`, `api/app.py`, `trazabilidad/registro.py` | `tests/api/` (P1–P10 de punta a punta) |

Decisiones nuevas: D-24 a D-32 en `docs/decisiones.md`. D-24 aprobada (2026-11-19). **D-31** son observaciones
para decidir.

### Cómo se une todo (implementado)
`api.flujo.procesar(ctx, spec, hoy=...)`: `validar` -> `compilar` -> `ejecutar` -> `revisar_datos` (por consulta
principal; P8 se une con `unir_por_dimension`) -> `motor.analisis.calcular` (método -> secciones) ->
`generar_grafico` -> `empaquetar` -> `Redactor` (capa de IA, opcional) -> `validar_con_regeneracion` -> `exportar`
-> `rpt_especificacion`, `rpt_solicitud`, `rpt_resultado`, `rpt_validacion`, `rpt_narrativa_cache`.
Sin redactor el informe sale en modo degradado. `api.flujo.reproducir` regenera una solicitud guardada (RNF-11).

### Pendiente o por validar
1. ~~PDF en Docker~~ y ~~ETL y API sobre PostgreSQL~~: hechos (D-32). Queda opcional revisar con EXPLAIN las
   consultas del ETL si el volumen real es mucho mayor que el sintético.
2. **Servicio en `docker-compose`:** hoy se levanta con `docker run` (receta abajo). Para agregarlo a compose hay
   que separar las URL de desarrollo local (`localhost`) de las del contenedor (`db`).
3. **Rol `rpt_` de escritura:** `DATABASE_URL_RPT` necesita un rol con escritura solo en `rpt_` (no existe en
   `sql/`; el DDL es cerrado). En desarrollo se puede usar el admin.
4. **Cliente HTTP de la capa de IA:** implementar `Redactor` cuando Laura cierre los puntos 7 y 9 de
   `docs/interfaz_capa_ia.md`. Hoy la IA se simula en las pruebas.
5. **Evaluación (Sprint 4, historia 14):** métricas de la Tabla 2 (exactitud de cifras por proveedor desde
   `rpt_validacion`, 18 plantillas x 5 formatos = 90 archivos, tiempos).
6. **Identidad UMB:** colores provisionales en `exportacion/identidad.py` (D-27) hasta el manual de marca.
7. **Revisar visualmente** con Daniel un DOCX y un PDF reales (el PDF de P4 se revisó: identidad, texto, prueba y
   mapa de calor correctos).
8. **D-31:** supresión de grupos antes de la segmentación; estado de `rpt_especificacion`; registro de errores.

## Cómo trabajar una historia
1. Abrir el archivo de pruebas de la historia y leer los docstrings del módulo.
2. Implementar. **No cambiar firmas ni pruebas**; si una prueba parece equivocada, anotarlo en
   `docs/decisiones.md` y preguntar a Daniel.
3. `uv run python -m pytest` y `uv run ruff check .` en verde; actualizar `docs/backlog.md` y este archivo; un
   commit convencional por historia.

## Qué NO tocar sin preguntar a Daniel
`spec/`, `contrato/modelos.py`, `contrato/pii.py`, `compilador/`, `validador_cifras/`, `semantica/expresion.py`,
`schemas/`, `dw/esquema.py`, `trazabilidad/esquema.py`, las firmas de los módulos de la tabla y las pruebas
existentes. Cambiar el contrato exige subir su versión una vez Laura lo apruebe (invariante 8).
Ninguna dependencia nueva fuera de la Tabla 19 sin preguntar. Este repo nunca llama a un LLM.

## Trampas conocidas
- El motor recibe un DataFrame por consulta. P8 trae tres (`principal:<tabla>`), que se unen con
  `ml.segmentacion.unir_por_dimension`; el chi-cuadrado lee la consulta `prueba`, no la `principal` (D-06, D-22).
- Una razón nunca se promedia: usar `<metrica>__num` y `<metrica>__den` (`motor.descriptiva.razon_total`).
- Llamar siempre a `revisar_datos` antes de calcular: es quien suprime los grupos con menos de cinco personas y
  quien fija el gráfico final. Las columnas que empiezan por `_` nunca se exportan ni van al contrato.
- Las dimensiones con `viaja_a_ia = False` (empresa, macroproyecto) no pueden aparecer en `grupo` del contrato:
  de una segmentación solo viajan k, la silueta, los tamaños y los centroides.
- Si `SpecResuelta.periodo` es `None` (filtro temporal), el periodo del contrato sale del rango de los datos.
- Los parámetros del análisis (alfa, nivel de confianza, k) se pasan al validador de cifras en `extra`; si no,
  un «95 %» en el texto cuenta como cifra inventada.
- Toda cifra que el texto pueda necesitar debe ir como indicador en el contrato (totales, máximos, variación):
  la IA no puede calcular nada, ni una resta.
- El chi-cuadrado se calcula sin corrección de Yates; la t es la de Welch; la desviación es muestral (ddof = 1).
- Holt con `initialization_method="estimated"` emite avisos de convergencia con series cortas: silenciarlos en
  el ajuste, no globalmente.
- Matplotlib: usar el backend `Agg` y fijar tamaño, DPI y fuentes para que el PNG sea determinista.
- Instantáneas mensuales: el ETL carga un corte por fin de mes; `agg_proyecto_linea_mes` debe coincidir con
  `hecho_proyecto` y `agg_facturacion_mes` usa el primer día del mes de la factura.
- `dim_linea_programa` necesita una fila de nivel programa por programa (D-13).
- El catálogo de estados vive por ahora en `datos_sinteticos.generar.CATALOGO_ESTADOS` (provisional, D-04).
- Validar specs siempre con `cargar_especificacion` / `validar`, no con `Especificacion.model_validate`.
- WeasyPrint en Windows necesita GTK: aquí la prueba de PDF se omite; correrla en Docker (Linux) antes de dar
  por cerrada la exportación.
- En esta máquina `uv run pytest` falla con «uv trampoline failed to canonicalize script path»: usar
  `uv run python -m pytest`. Al escribir archivos desde Python en Windows, `write_text` deja CRLF.
- En el PostgreSQL de desarrollo quedó creado el rol `ciumb_lector` (sin inicio de sesión). El volumen actual no
  tiene `ana_` ni `rpt_`: aplicar `sql/ana_rpt_postgresql.sql` o recrear con `docker compose down -v`.

## Pendientes de otras personas
- **Laura (capa de IA):** revisar `docs/interfaz_capa_ia.md` (10 puntos por confirmar).
- **Daniel:** lista de las 18 plantillas base (hay 8 sembradas); revisar D-31; revisar y hacer commit de la rama `feat/motor-ml-graficos-contrato-etl-exportacion-api`.
- **Integración (Juan Stiven, Manuel):** forma de `alcance` e identificación del tutor; qué ve cada rol (D-20);
  tutor empresarial (D-14); carga de todos los consultores (D-12); motor de base de datos real; token de
  servicio de la API.

## Cómo levantar el entorno
1. `uv sync`
2. `cp .env.example .env` y completar contraseñas y `SAL_SEUDONIMIZACION` (16 caracteres o más).
3. `docker compose up -d --wait db` (aplica `datos_sinteticos/ddl.sql` y `sql/ana_rpt_postgresql.sql` solo al
   crear el volumen).
4. `uv run python -m datos_sinteticos.generar`
5. `uv run python -m ciumb_analitica.etl --historico 2025-01` (ETL + cortes mensuales; ver `.env.example`).
6. Servicio local: `uv run --env-file .env uvicorn ciumb_analitica.api.app:app`. Antes, una vez: sembrar la capa
   semántica en `rpt_` (`semantica.almacen.sembrar`) y dar LOGIN a `ciumb_lector` (comentario en el DDL).
7. Servicio en contenedor: `docker build -t ciumb-analitica:dev .` y `docker run -d --name ciumb_api -p 8000:8000
   --env-file <copia de .env con host.docker.internal en lugar de localhost> -e
   DIRECTORIO_INFORMES=/app/informes_generados ciumb-analitica:dev` (en Git Bash, anteponer
   `MSYS_NO_PATHCONV=1`; si no, `/app/...` se convierte en una ruta de Windows).
