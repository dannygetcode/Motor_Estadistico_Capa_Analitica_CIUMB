# Relevo entre sesiones

## Estado al cierre de la sesión 1 (2026-11-11, Fable · PROMPT_1 completo)
Ramas encadenadas, sin fusionar a `main` (lo decide Daniel): `feat/t1-interfaces-frontera` →
`feat/t2-dw-semantica` → `feat/t3-validador-spec` → `feat/t4-compilador` → `feat/t5-validador-cifras` →
`feat/t6-relevo` (la última contiene todo).

`uv run pytest`: **487 en verde, 148 `xfail` (pendiente de implementar), 1 omitida** (PDF: WeasyPrint no carga
GTK en esta máquina). `uv run ruff check .`: limpio.

### Hecho e implementado por completo (no hay que volver a escribirlo)
1. **Interfaces de frontera** — `spec/modelos.py`, `contrato/modelos.py`, `contrato/pii.py`, JSON Schema en
   `schemas/*.schema.json` (`uv run python -m ciumb_analitica.exportar_esquemas`), fixtures P1–P10 en
   `schemas/fixtures/` y rechazados en `schemas/fixtures/rechazados/`. **BORRADOR** hasta que Laura revise
   `docs/interfaz_capa_ia.md`.
2. **DW y capa semántica** — `dw/esquema.py` y `trazabilidad/esquema.py` (fuente del DDL),
   `sql/ana_rpt_postgresql.sql` (generado con `uv run python -m ciumb_analitica.dw.ddl`; verificado en
   PostgreSQL 16), `dw/tiempo.py`, `semantica/` (modelos, gramática de expresiones, semilla con 31 métricas,
   18 dimensiones y 8 plantillas, `almacen.sembrar` / `leer_capa` / `leer_plantillas`).
3. **Validador de specs** — `spec/validador.py` (`validar`, `revisar_datos`), `spec/resultado.py`
   (`SpecResuelta`, códigos de problema y aviso, umbrales), `spec/convenciones.py` (nombres de columnas).
4. **Compilador** — `compilador/compilador.py` (`compilar`, `ejecutar`, `huella_datos`), `seudonimo.py`.
   SQL de P1–P9 verificado con EXPLAIN en PostgreSQL 16.
5. **Validador de cifras** — `validador_cifras/` (`extraccion`, `validador`, `plantilla`).

Decisiones: D-06 a D-23 en `docs/decisiones.md`.

### Dejado como firma + pruebas `xfail` (tarea 6)
Cada función tiene tipos y un docstring que dice entradas, salidas, advertencias, librería de referencia y
tabla del diseño; su cuerpo es `raise NotImplementedError("pendiente de implementar")`. Las pruebas comparan
contra SciPy, statsmodels, scikit-learn y NumPy llamados directamente; los valores de referencia que las
pruebas afirman (k = 3 por silueta, tamaños 30/20/10, MAE del modelo frente a la línea base, límites de
Tukey) se comprobaron con esas librerías al escribirlas.

## Cómo trabajar una historia
1. Abrir el archivo de pruebas de la historia y leer los docstrings del módulo.
2. Implementar las funciones. **No cambiar firmas ni pruebas**; si una prueba parece equivocada, anotarlo en
   `docs/decisiones.md` y preguntar a Daniel.
3. Quitar `pytestmark = PENDIENTE` del archivo de pruebas (o, si se implementa por partes, mover la marca a las
   pruebas que sigan pendientes). La marca es estricta: una prueba que ya pasa y sigue marcada hace fallar la
   suite, a propósito.
4. `uv run pytest` y `uv run ruff check .` en verde; actualizar `docs/backlog.md` y este archivo; un commit
   convencional por historia, en su rama.

## Tareas, en orden de dependencia (una por historia)
| # | Historia | Módulo | Prueba | OE | RF / RNF | Diseño |
|---|---|---|---|---|---|---|
| 1 | Estadística descriptiva | `motor/descriptiva.py` | `tests/motor/test_descriptiva.py` | OE1 | RF-02 | Tabla 8 |
| 2 | Series de tiempo | `motor/series.py` | `tests/motor/test_series.py` | OE1 | RF-03 | Tabla 8 |
| 3 | Inferencia | `motor/inferencia.py` | `tests/motor/test_inferencia.py` | OE1 | RF-04, RNF-13 | Tabla 8, 3.1 |
| 4 | Atípicos | `ml/atipicos.py` | `tests/ml/test_atipicos.py` | OE2 | RF-05, RF-20 | Tabla 8 |
| 5 | Pronóstico | `ml/pronostico.py` | `tests/ml/test_pronostico.py` | OE2 | RF-06, RNF-13 | Tabla 8 |
| 6 | Segmentación | `ml/segmentacion.py` | `tests/ml/test_segmentacion.py` | OE2 | INF-EMP-03 | Tabla 8 |
| 7 | Gráficos (6 tipos) | `graficos/generador.py` | `tests/graficos/test_generador.py` | OE3 | RF-15 | Tabla 21 |
| 8 | Empaquetador del contrato | `contrato/empaquetador.py` | `tests/contrato/test_empaquetador.py` | OE4 | RNF-05, RNF-06 | 4.4.3, Figura 12 |
| 9 | Vistas de extracción | `fuentes/vistas.py` | `tests/fuentes/test_vistas.py` | OE4 | RNF-06 | 4.2, Tabla 13 |
| 10 | Reglas de calidad | `etl/calidad.py` | `tests/etl/test_calidad.py` | OE4 | INF-TRA-08 | 4.2.2 |
| 11 | Carga incremental y ETL | `etl/carga.py` | `tests/etl/test_carga.py` + integración por escribir | OE4 | RNF-04 | 4.3.2 |
| 12 | Exportación (5 formatos) | `exportacion/exportador.py` | `tests/exportacion/test_exportador.py` | OE3 | RF-16, RF-11 | 4.5 |
| 13 | Orquestación y API | `api/`, `trazabilidad/` | por escribir | OE4 | RF-12, RF-13, RF-19, RF-21 | Figuras 9 y 11 |
| 14 | Evaluación (Sprint 4) | `tests/aceptacion/` | por escribir | OE1–OE5 | Tabla 2 | 1.4, 4.4.4 |

Sin firmas todavía (no alcanzó la sesión): la **orquestación** de la historia 13 —una función que encadene el
flujo de abajo y devuelva un `InformeEnsamblado`, las rutas `POST /informes/personalizado`, `POST /informes`,
`GET /semantica` (ya existe `CapaSemantica.publicar`), `GET /informes/catalogo` (ya existe `leer_plantillas`),
`GET /informes/{id}/descargar`, la escritura en `rpt_especificacion`, `rpt_solicitud`, `rpt_resultado` y
`rpt_validacion`, y la caché por huella (RF-13)— y las pruebas de integración del ETL contra PostgreSQL.

Flujo que une todo:
`validar(spec, capa, hoy)` → `compilar(spec_resuelta, capa, sal)` → `ejecutar(con, plan)` →
`revisar_datos(spec_resuelta, datos)` → motor / ML → `generar_grafico` → `empaquetar` (termina en
`cargar_contrato`) → capa de IA (fuera de este repo) →
`validar_con_regeneracion(narrativa, contrato, regenerar, plantilla_por_defecto, extra)` → `exportar`.
En modo degradado (RF-11) la narrativa es `None`, `regenerar` es `None` y el texto sale de la plantilla.

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
- En la terminal de esta máquina fallan los heredocs con comillas simples: escribir los archivos con la
  herramienta de escritura. Un `cd` a una subcarpeta puede cambiar el directorio de la sesión.
- En el PostgreSQL de desarrollo quedó creado el rol `ciumb_lector` (sin inicio de sesión). El volumen actual no
  tiene `ana_` ni `rpt_`: aplicar `sql/ana_rpt_postgresql.sql` o recrear con `docker compose down -v`.

## Pendientes de otras personas
- **Laura (capa de IA):** revisar `docs/interfaz_capa_ia.md` (10 puntos por confirmar).
- **Daniel:** lista de las 18 plantillas base (hay 8 sembradas); fusionar las ramas a `main`.
- **Integración (Juan Stiven, Manuel):** forma de `alcance` e identificación del tutor; qué ve cada rol (D-20);
  tutor empresarial (D-14); carga de todos los consultores (D-12); motor de base de datos real; token de
  servicio de la API.

## Cómo levantar el entorno
1. `uv sync`
2. `cp .env.example .env` y completar contraseñas y `SAL_SEUDONIMIZACION` (16 caracteres o más).
3. `docker compose up -d --wait db` (aplica `datos_sinteticos/ddl.sql` y `sql/ana_rpt_postgresql.sql` solo al
   crear el volumen).
4. `uv run python -m datos_sinteticos.generar`
