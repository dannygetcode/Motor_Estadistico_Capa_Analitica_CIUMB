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

## Decisiones sobre las contradicciones y huecos del diseño (2026-11-11)
Los 12 puntos detectados al dividir el documento quedan resueltos así. D-06 a D-08 las tomó Daniel;
D-09 a D-17 las tomó la sesión 1 con la opción mínima (PROMPT_1). La lista original se conserva al final.

> **BORRADOR — frontera con la capa de IA.** `ciumb.spec/1.0` y el contrato `ciumb.informe/2.0.0` son el acuerdo
> con la capa de IA (Laura Valentina Maldonado) y ella **aún no los ha revisado**. D-06, D-07, D-08 y D-15 son
> por eso decisiones en borrador: pueden cambiar tras su revisión. El resumen para ella está en
> `docs/interfaz_capa_ia.md`. Mientras sigan en borrador, un cambio pedido por ella no exige subir la versión
> del contrato (invariante 8); una vez los apruebe, sí.

### D-06 · `analisis.variables` y `dimensiones` son independientes (punto 7) — Daniel · BORRADOR
- Contexto: en la Figura 14 (P4) `analisis.variables` usa `estado_hito`, que no está en `dimensiones`.
- Decisión: `analisis.variables` puede referir dimensiones de la capa semántica que no estén en
  `spec.dimensiones`. El validador verifica que existan y que sean compatibles con el hecho de la métrica.
  `dimensiones` = agrupación del gráfico; `variables` = cruce de la prueba.
- Consecuencia: el compilador puede necesitar una segunda consulta (la tabla de contingencia de la prueba) con
  un GROUP BY distinto al del gráfico. A `variables` se le aplican las mismas reglas que a `dimensiones`
  (lista blanca, no identificar personas, supresión de grupos < 5).

### D-07 · `metodo` por sección, con reemplazo opcional por indicador (punto 8) — Daniel · BORRADOR
- Contexto: el texto de 4.4.3 dice que cada indicador lleva su método; en la Figura 12 está en la sección.
- Decisión: `metodo` va a nivel de sección; cada indicador puede traer un `metodo` opcional que reemplaza al de
  la sección. Se mantienen las claves `"contrato"` (en el contrato) y `"esquema"` (en la spec).
- Consecuencia: quien lea un indicador usa `indicador.metodo` si existe y, si no, `seccion.metodo`.

### D-08 · `periodo` opcional (punto 10) — Daniel · BORRADOR
- Contexto: la Figura 13 no tiene `periodo` (filtra por `periodo_academico`); la Tabla 20 dice que sin periodo
  se usa el último periodo cerrado.
- Decisión: `periodo` es opcional. Un filtro sobre una dimensión temporal cuenta como periodo. Si no hay
  ninguno de los dos, el validador aplica el último periodo cerrado y lo declara en el anexo.
- Consecuencia: la spec resuelta (la que se compila y se huella) siempre tiene periodo explícito; el
  periodo aplicado por defecto viaja como aviso para el anexo.

### D-09 · Nombres de `dim_tiempo` (punto 1)
- Decisión: columnas sin tildes, `dia` y `anio` (convención del repo), y se incluye `nombre_mes` (Figura 8, la
  más detallada). Atributos: `fecha, dia, mes, nombre_mes, trimestre, semestre, anio, periodo_academico`.

### D-10 · `dim_macroproyecto` (punto 2)
- Decisión: la clave del coordinador se llama `sk_coordinador` (prefijo `sk_`, como todas las claves
  sustitutas; apunta a `dim_persona_rol`) y la dimensión lleva `vigente_desde`/`vigente_hasta` (SCD tipo 2,
  Tabla 16). Fila vigente = `vigente_hasta IS NULL`; no se agrega una columna `es_vigente`.

### D-11 · Medidas de hitos en `hecho_proyecto` (punto 3)
- Decisión: `hecho_proyecto` incluye `n_hitos`, `n_hitos_atrasados` y `dias_retraso_promedio` (Figura 8 y
  Tabla 17).
- Razón: `hecho_hito` no tiene línea ni programa en la matriz de bus (Tabla 15), así que P4 (hitos atrasados por
  facultad) solo se puede responder desde `hecho_proyecto`. `pct_hitos_atrasados` =
  SUM(`n_hitos_atrasados`) / SUM(`n_hitos`), razón no aditiva.

### D-12 · `hecho_consultoria.sk_persona` (punto 4)
- Decisión: `hecho_consultoria` lleva `sk_persona` (Tabla 15), que admite nulo y apunta al consultor con rol
  líder de `consultor_consultoria`. El resto de consultores solo cuenta en `n_consultores`.
- Consecuencia: la carga por consultor (INF-COS-04) se mide sobre el líder. Si el CIUMB necesita la carga de
  todos los consultores hará falta una tabla puente; queda como pregunta para integración.

### D-13 · `hecho_practica.sk_linea` (punto 5)
- Decisión: `dim_linea_programa` tiene, además de una fila por línea, una fila de nivel programa por cada
  programa (`linea_investigacion = 'No aplica'`). `hecho_practica.sk_linea` apunta a esa fila según
  `practica.id_programa`.
- Consecuencia: las prácticas se pueden agrupar por programa y facultad, no por línea. La capa semántica no
  declara compatibles las métricas de prácticas con la dimensión `linea_investigacion`.

### D-14 · Tutor de `hecho_practica` (punto 6)
- Decisión: `sk_persona` es el tutor académico (es el usuario del CIUMB cuyo alcance de rol restringe RF-21 y
  cuya carga mide el centro). El tutor empresarial no se carga en el hecho; su ausencia sí se revisa en la
  regla de calidad «práctica sin tutor».
- Pregunta para integración: si el tutor empresarial entra al sistema con alcance propio.

### D-15 · Formato de `huella_datos` (punto 9) · BORRADOR
- Decisión: en el contrato, `huella_datos` cumple `^sha256:[0-9a-f]{64}$`. En `rpt_resultado.huella_datos`
  (CHAR(64)) se guarda solo el hexadecimal. El ejemplo de la Figura 12 se conserva literal en
  `schemas/ejemplos/` como transcripción; el fixture válido lleva una huella completa.

### D-16 · Endpoints (punto 11)
- Decisión: se mantiene `GET /salud` (vida del servicio). `GET /salud/ia` informa el estado de los proveedores
  y es de la capa de IA; este repo no lo implementa (nunca llama a un LLM). `GET /informes/catalogo` sí se
  implementa aquí, leyendo `rpt_plantilla` (Tabla 12).

### D-17 · Carga incremental (punto 12)
- Decisión: por tabla. Si la vista de extracción expone `fecha_modificacion`, se filtra por ella; si no, se
  compara la huella de cada fila con la de la carga anterior (4.3.2). Confirma D-04.

## Lista original de contradicciones y huecos (resueltos arriba)
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
