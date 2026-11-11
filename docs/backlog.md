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
- [ ] Vistas de extracción de `fuentes/` sobre el esquema `ciumb`.
- [ ] ETL: extracción incremental, seudonimización, reglas de calidad, carga de dimensiones y hechos.
- [ ] Motor estadístico (descriptiva, series, inferencia; Tabla 8).
- [ ] Gráficos (6 tipos) y recomendador (Tabla 21).

## Sprint 3 (30 nov–11 dic): ML, contrato, validador, exportación
- [ ] ML: pronóstico, atípicos, segmentación.
- [ ] Empaquetador del contrato y filtro de PII.
- [x] Validador de cifras (6 pasos) con regeneraciones y plantilla sin IA por defecto (adelantado en la sesión 1).
- [ ] Exportación PDF, DOCX, XLSX, HTML y CSV.

## Sprint 4 (14–19 dic): evaluación
- [ ] Pruebas de aceptación P1–P10 y métricas de los objetivos (Tabla 2).
