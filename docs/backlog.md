# Backlog por sprint

Estados: [x] hecho · [~] en curso · [ ] pendiente. El detalle de cada historia está en `docs/diseno/` y `docs/handoff.md`.

## Sprint 1: preparación (hasta el 13 nov)
- [x] S0-01 Diseño dividido en markdown con índice y verificación de palabras.
- [x] S0-02 Ejemplos JSON de las Figuras 12–15 en `schemas/ejemplos/`.
- [x] S0-03 Esqueleto del repositorio (uv, ruff, pytest, pre-commit, Docker, paquetes, `GET /salud`).
- [x] S0-04 BD sintética de la fuente 1: DDL inferido y generador con semilla fija y defectos documentados.

## Sprint 2 (16–27 nov): vistas, ETL, semántica, compilador, motor, gráficos
- [ ] Modelos `ciumb.spec/1.0` y contrato 2.0.0 (Pydantic + JSON Schema) y fixtures P1–P10.
- [ ] DDL de `ana_` (Tablas 15–17) y de `rpt_` (Figura 6, Tabla 12); usuario de solo lectura.
- [ ] Seed de la capa semántica (rpt_metrica, rpt_dimension, rpt_compatibilidad).
- [ ] Validador de especificación (7 pasos).
- [ ] Compilador de spec a SQL parametrizado con huella determinista.
- [ ] Vistas de extracción de `fuentes/` sobre el esquema `ciumb`.
- [ ] ETL: extracción incremental, seudonimización, reglas de calidad, carga de dimensiones y hechos.
- [ ] Motor estadístico (descriptiva, series, inferencia; Tabla 8).
- [ ] Gráficos (6 tipos) y recomendador (Tabla 21).

## Sprint 3 (30 nov–11 dic): ML, contrato, validador, exportación
- [ ] ML: pronóstico, atípicos, segmentación.
- [ ] Empaquetador del contrato y filtro de PII.
- [ ] Validador de cifras (6 pasos) con regeneraciones y plantilla.
- [ ] Exportación PDF, DOCX, XLSX, HTML y CSV.

## Sprint 4 (14–19 dic): evaluación
- [ ] Pruebas de aceptación P1–P10 y métricas de los objetivos (Tabla 2).
