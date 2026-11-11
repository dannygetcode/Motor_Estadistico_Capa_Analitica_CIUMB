# Relevo entre sesiones

## Estado al cierre de la sesión 1 (2026-11-11, Fable · PROMPT_1)
Ramas encadenadas, sin fusionar a `main` (lo decide Daniel): `feat/t1-interfaces-frontera` →
`feat/t2-dw-semantica` → `feat/t3-validador-spec` → `feat/t4-compilador` → `feat/t5-validador-cifras` (la última
contiene todo). `uv run pytest`: 487 pruebas en verde. `uv run ruff check .`: limpio.

Hecho (tareas 1 a 5 de PROMPT_1):
1. **Interfaces de frontera** — `spec/modelos.py`, `contrato/modelos.py`, `contrato/pii.py`, JSON Schema en
   `schemas/*.schema.json` (`uv run python -m ciumb_analitica.exportar_esquemas`), fixtures P1–P10 en
   `schemas/fixtures/` y rechazados en `schemas/fixtures/rechazados/`. **BORRADOR** hasta que Laura revise
   `docs/interfaz_capa_ia.md`.
2. **DW y capa semántica** — `dw/esquema.py`, `trazabilidad/esquema.py` (fuente del DDL),
   `sql/ana_rpt_postgresql.sql` (generado con `uv run python -m ciumb_analitica.dw.ddl`; verificado en
   PostgreSQL 16), `dw/tiempo.py`, `semantica/` (modelos, gramática de expresiones, semilla con 31 métricas,
   18 dimensiones y 8 plantillas, `almacen.sembrar` / `leer_capa`).
3. **Validador de specs** — `spec/validador.py` (`validar` y `revisar_datos`), `spec/resultado.py`
   (`SpecResuelta`, códigos de problema y aviso, umbrales), `spec/convenciones.py` (nombres de columnas).
4. **Compilador** — `compilador/compilador.py` (`compilar`, `ejecutar`, `huella_datos`), `seudonimo.py`.
   SQL de P1–P9 verificado con EXPLAIN en PostgreSQL 16.
5. **Validador de cifras** — `validador_cifras/` (`extraccion`, `validador`, `plantilla`).

Decisiones: D-06 a D-23 en `docs/decisiones.md`.

## Pendiente de la sesión 1: tarea 6 (relevo para Opus) — NO se hizo
Se acabó la cuota antes de empezar. Falta, en este orden:
- Firmas con tipos y docstrings (entradas, salidas, advertencias, tabla del diseño) en `motor/`, `ml/`,
  `graficos/`, `contrato/` (empaquetador), `etl/` y `exportacion/`. Hoy esos paquetes están vacíos.
- Pruebas `xfail` («pendiente de implementar») con valores de referencia de SciPy/statsmodels.
- Completar esta lista de tareas con su prueba, su OE y su RF.

## Siguientes tareas (una por historia)
| # | Historia | Paquete | OE / RF | Parte de |
|---|---|---|---|---|
| 1 | Tarea 6 de PROMPT_1 (firmas + xfail) | varios | — | lo anterior |
| 2 | Vistas de extracción sobre `ciumb` | `fuentes/` | OE4 · RNF-06 | `datos_sinteticos/ddl.sql`, Tabla 13 |
| 3 | ETL: seudonimización, calidad, carga de dimensiones, hechos y agregados | `etl/` | OE4 · RNF-05/06 | `dw/esquema.py`, `seudonimo.py`, D-11 a D-14, D-17 |
| 4 | Descriptiva, series e inferencia | `motor/` | OE1 · RF-02 a RF-04 | Tabla 8; emite `CHI2_ESPERADO_BAJO` |
| 5 | Gráficos (6 tipos) | `graficos/` | OE3 · RF-15 | `SpecResuelta.grafico`, `revisar_datos` |
| 6 | Pronóstico, atípicos, segmentación | `ml/` | OE2 · RF-05, RF-06 | Tabla 8 |
| 7 | Empaquetador del contrato | `contrato/` | OE4 · DA-04 | debe terminar en `cargar_contrato` |
| 8 | Exportación PDF/DOCX/XLSX/HTML/CSV | `exportacion/` | OE3 · RF-16 | `validador_cifras.plantilla` |
| 9 | Rutas (`POST /informes`, `GET /semantica`, `GET /informes/catalogo`) y trazabilidad `rpt_` | `api/`, `trazabilidad/` | RF-12, RF-19 | `CapaSemantica.publicar`, `leer_plantillas` |

Flujo que une lo hecho: `validar(spec, capa, hoy)` → `compilar(spec_resuelta, capa, sal)` → `ejecutar(con, plan)`
→ `revisar_datos(spec_resuelta, datos)` → motor/gráficos → empaquetador → `cargar_contrato` → (capa de IA) →
`validar_con_regeneracion(narrativa, contrato, regenerar, plantilla_por_defecto, extra)` → exportación.

## Qué NO tocar sin preguntar a Daniel
`spec/`, `contrato/modelos.py`, `contrato/pii.py`, `compilador/`, `validador_cifras/`, `semantica/expresion.py`,
`schemas/`, `dw/esquema.py`, `trazabilidad/esquema.py`. Si una prueba existente falla, se arregla el código nuevo,
no la prueba. Cambiar el contrato exige subir su versión una vez Laura lo apruebe.

## Trampas conocidas
- El motor recibe un DataFrame por consulta. P8 trae tres (`principal:<tabla>`), que hay que unir por la
  dimensión común; el chi-cuadrado lee la consulta `prueba`, no la `principal` (D-06, D-22).
- Una razón nunca se promedia: usar las columnas `<metrica>__num` y `<metrica>__den` para cualquier total.
- Las columnas que empiezan por `_` (`_n_personas`, `_persona`, `_registro`) nunca se exportan ni van al
  contrato. Llamar siempre a `revisar_datos` antes de calcular: es quien suprime los grupos < 5.
- Las dimensiones con `viaja_a_ia = False` (empresa, macroproyecto) no pueden aparecer en `grupo` del contrato.
- Si `SpecResuelta.periodo` es `None` (filtro temporal), el periodo del contrato sale del rango de los datos.
- Los parámetros del análisis (alfa, nivel de confianza, k) se pasan al validador de cifras en `extra`.
- Instantáneas mensuales: el ETL debe cargar un corte por fin de mes; `agg_proyecto_linea_mes` debe coincidir
  con `hecho_proyecto` y `agg_facturacion_mes` usa el primer día del mes de la factura.
- `dim_linea_programa` necesita una fila de nivel programa por programa (D-13).
- Validar specs siempre con `cargar_especificacion` / `validar`, no con `Especificacion.model_validate`.
- En la terminal de esta máquina fallan los heredocs con comillas simples: escribir los archivos con la
  herramienta de escritura. Un `cd` a una subcarpeta puede cambiar el directorio de la sesión.
- En el PostgreSQL de desarrollo quedó creado el rol `ciumb_lector` (sin acceso de inicio de sesión). El volumen
  actual no tiene `ana_` ni `rpt_`: aplicar `sql/ana_rpt_postgresql.sql` o recrear con `docker compose down -v`.
- WeasyPrint en Windows necesita GTK; no se ha probado. Docker Desktop no arranca solo.

## Pendientes de otras personas
- **Laura:** revisar `docs/interfaz_capa_ia.md` (10 puntos por confirmar).
- **Daniel:** lista de las 18 plantillas base (hay 8 sembradas).
- **Integración (Juan Stiven, Manuel):** forma de `alcance` e identificación del tutor; qué ve cada rol (D-20);
  tutor empresarial (D-14); carga de todos los consultores (D-12); motor de base de datos real.

## Cómo levantar el entorno
1. `uv sync`
2. `cp .env.example .env` y completar contraseñas y `SAL_SEUDONIMIZACION` (16 caracteres o más).
3. `docker compose up -d --wait db` (aplica `datos_sinteticos/ddl.sql` y `sql/ana_rpt_postgresql.sql` solo al
   crear el volumen).
4. `uv run python -m datos_sinteticos.generar`
