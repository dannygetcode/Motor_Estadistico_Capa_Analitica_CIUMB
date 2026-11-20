# Backlog por sprint

Estados: [x] hecho · [~] en curso · [ ] pendiente. El detalle de cada historia está en `docs/diseno/` y `docs/handoff.md`.

## Sprint 1: preparación (hasta el 13 nov)
- [x] S0-01 Diseño dividido en markdown con índice y verificación de palabras.
- [x] S0-02 Ejemplos JSON de las Figuras 12–15 en `schemas/ejemplos/`.
- [x] S0-03 Esqueleto del repositorio (uv, ruff, pytest, pre-commit, Docker, paquetes, `GET /salud`).
- [x] S0-04 BD sintética de la fuente 1: DDL inferido y generador con semilla fija y defectos documentados.

## Sprint 2 (16–27 nov): vistas, ETL, semántica, compilador, motor, gráficos
- [x] Modelos `ciumb.spec/1.0` y contrato 2.0.0 (Pydantic + JSON Schema), filtro de PII y fixtures P1–P10. BORRADOR hasta la revisión de la capa de IA (`docs/interfaz_capa_ia.md`).
- [x] DDL de `ana_` (Tablas 15–17) y de `rpt_` (Figura 6, Tabla 12); usuario de solo lectura. Verificado en PostgreSQL 16.
- [x] Seed de la capa semántica (rpt_metrica, rpt_dimension, rpt_compatibilidad) y 8 plantillas base.
- [ ] Las otras 10 plantillas base (falta la lista de las 18 priorizadas).
- [x] Validador de especificación (7 pasos) y revisión posterior a los datos (supresión < 5, muestra, gráfico).
- [x] Compilador de spec a SQL parametrizado con huella determinista (razones, agregados, instantáneas, alcance). SQL de P1–P9 verificado con EXPLAIN en PostgreSQL 16.
- [x] Vistas de extracción de `fuentes/` sobre el esquema `ciumb`: lista blanca de columnas por entidad (`metadatos_fuente`), sin campos sensibles.
- [x] ETL: extracción incremental (fecha de modificación o huella), seudonimización, reglas de calidad, carga de dimensiones (SCD 2), hechos, agregados y cortes históricos; programación con APScheduler (`python -m ciumb_analitica.etl`). Integración probada en SQLite y en PostgreSQL 16 (Docker), sin errores (D-25, D-29, D-32).
- [x] Motor estadístico (descriptiva, series, inferencia; Tabla 8), contrastado con NumPy y SciPy, y despacho método -> secciones del contrato (`motor/analisis.py`, D-30).
- [x] Gráficos (6 tipos, Matplotlib + Plotly, deterministas) y recomendador (Tabla 21). Identidad visual provisional (D-27).

## Sprint 3 (30 nov–11 dic): ML, contrato, validador, exportación
- [x] ML: pronóstico (Holt, regresión; validación de origen móvil), atípicos (RIC, Z), segmentación (k-medias con silueta), contra statsmodels y scikit-learn.
- [x] Empaquetador del contrato y filtro de PII.
- [x] Validador de cifras (6 pasos) con regeneraciones y plantilla sin IA por defecto (adelantado en la sesión 1).
- [x] Exportación PDF, DOCX, XLSX, HTML y CSV con identidad UMB. PDF probado en Linux (Docker) y por HTTP; en Windows la API responde 503 para PDF (D-32).
- [x] Orquestación del flujo (`api/flujo.py`, capa de IA como puerto `Redactor`), rutas de la API con token de servicio, trazabilidad en `rpt_` y caché de narrativa por huella (D-28). P1–P10 de punta a punta en `tests/api/test_flujo.py` (modo degradado y con IA simulada).

## Sprint 4 (14–19 dic): evaluación
- [~] Pruebas de aceptación P1–P10: el resultado, el gráfico final y los avisos de la Tabla 22 ya se comprueban de punta a punta (`tests/api/test_flujo.py`). También corren por HTTP contra el servicio en Docker y PostgreSQL. Faltan las métricas de los objetivos (Tabla 2) y la IA real.
