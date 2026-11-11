# Decisiones fuera del diseño

Formato breve tipo ADR. Cada decisión: contexto, decisión, consecuencia. Las decisiones del diseño
(DA-01 … DA-09) están en `docs/diseno/4.4.1_componentes_decisiones_arquitectura.md` (Tabla 18).

## D-01 · División del diseño con python-docx (2026-11-11)
- Contexto: no hay pandoc en el equipo; python-docx ya está en la Tabla 19.
- Decisión: `herramientas/dividir_diseno.py` genera `docs/diseno/` (un archivo por sección de nivel 3 donde
  existe, de nivel 2 donde no). Las descripciones de figuras viven en `herramientas/figuras_descripciones.json`.
- Consecuencia: los .md de sección no se editan a mano; si cambia el docx, se regeneran.

## D-02 · Controlador de PostgreSQL como extra opcional (2026-11-11)
- Contexto: la Tabla 19 no nombra el controlador de BD y el motor del CIUMB no está confirmado.
- Decisión: `psycopg[binary]` (LGPL, código abierto, costo cero) va como extra `postgres` y en el grupo `dev`.
  Las dependencias base son agnósticas al motor; cuando se confirme el motor real se agrega su controlador como otro extra.
- Consecuencia: `uv sync` instala psycopg en desarrollo; el despliegue debe instalar el extra que corresponda.

## D-03 · Herramientas de desarrollo fuera de la Tabla 19 (2026-11-11)
- Decisión: ruff, pre-commit, httpx (lo exige `fastapi.testclient`) y Faker van solo en el grupo `dev`.
  No se distribuyen con el servicio. Faker y pandoc los autorizó Daniel en PROMPT_0.
- Nota: Starlette avisa que `httpx` en su TestClient está obsoleto en favor de `httpx2`; el aviso se filtró en
  `pyproject.toml`. Revisar cuando se actualice FastAPI.

## D-04 · Supuestos del modelo inferido de la fuente 1 (2026-11-11)
- `practica.id_estudiante` apunta a `usuario` (rol `estudiante`) y `id_tutor_empresarial` a `usuario`
  (rol `tutor_empresarial`); el ER inferido no define tablas de estudiante ni de tutor externo.
- `fecha_modificacion` se agregó solo a `proyecto_investigacion` y `practica`, para probar los dos caminos de la
  carga incremental que describe 4.3.2 (por fecha y, si no existe, por huella de fila).
- Las tablas de la fuente 1 viven en el esquema `ciumb` en desarrollo.
- Catálogo de estados por entidad: `CATALOGO_ESTADOS` en `datos_sinteticos/generar.py` (provisional;
  el catálogo real del CIUMB no se ha entregado). Lo debe reemplazar el catálogo único de `dim_estado`.
- Consecuencia: cuando llegue el ER real, solo cambian las vistas de `fuentes/` y el DDL sintético.

## D-05 · Defectos sintéticos adicionales (2026-11-11)
- Contexto: PROMPT_0 pide 4 tipos; la sección 4.2.2 lista además presupuesto ejecutado negativo, prácticas sin
  empresa y convenios sin fecha de fin.
- Decisión: se insertan los 7 tipos (13 claves, con conteos exactos y disjuntos), documentados en
  `datos_sinteticos/defectos.md`.

## Contradicciones y huecos detectados en el diseño (pendientes de decidir)
Se registraron al dividir el documento. La sesión que toque cada tema decide la opción mínima y la anota aquí.
1. **dim_tiempo:** la Figura 7 y la Tabla 16 usan `día`/`año`; la Figura 8 usa `anio` y agrega `nombre_mes`.
   Convención del repo (sin tildes): `anio`, `dia`.
2. **dim_macroproyecto:** la Figura 7 dice `coordinador_sk` y la Figura 8 `sk_coordinador`; solo la Figura 8 tiene
   `vigente_desde`/`vigente_hasta` (la Tabla 16 confirma SCD tipo 2).
3. **hecho_proyecto:** la Figura 8 y la Tabla 17 incluyen `n_hitos`, `n_hitos_atrasados` y `dias_retraso_promedio`;
   la Figura 7 no.
4. **hecho_consultoria y dim_persona_rol:** la Tabla 15 y una línea de la Figura 7 los relacionan, pero la
   Figura 7 no lista `sk_persona` entre las claves de `hecho_consultoria`.
5. **hecho_practica y sk_linea:** la práctica de origen no tiene línea de investigación (tiene `id_programa` e
   `id_macroproyecto`). Falta decidir cómo se llena `sk_linea` (¿nivel programa de `dim_linea_programa`?).
6. **hecho_practica y tutores:** la fuente tiene dos tutores (académico y empresarial) y el hecho tiene un solo
   `sk_persona (tutor)`.
7. **Figura 14 (P4):** `analisis.variables` usa `estado_hito`, que no aparece en `dimensiones` de la spec.
   Falta definir si las variables del chi-cuadrado deben declararse como dimensiones.
8. **Texto de 4.4.3 vs. Figura 12:** el texto dice que cada indicador lleva su método; en la Figura 12 `metodo`
   está a nivel de sección. Además, el contrato usa la clave `contrato` y la spec la clave `esquema`.
9. **Figura 12:** `huella_datos` aparece truncada (`sha256:91c4…e07b`); el ejemplo no es una huella válida.
10. **Figura 13:** la spec no tiene `periodo` (usa un filtro por `periodo_academico`), aunque la Tabla 20 dice que
    sin periodo se usa el último periodo cerrado.
11. **Endpoints:** la Figura 9 lista `GET /salud/ia`, y la Tabla 12 nombra `GET /informes/catalogo`, que no está en
    la lista de la Figura 9. La sesión 0 creó `GET /salud` (lo pidió PROMPT_0).
12. **Carga incremental:** la Figura 2 dice «carga incremental por fecha de modificación», pero ninguna tabla del
    ER inferido tiene esa columna; 4.3.2 aclara que hay respaldo por huella de fila (ver D-04).
