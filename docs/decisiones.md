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
  No se distribuyen con el servicio. Faker y pandoc los autorizó Daniel.
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
- Contexto: el plan inicial pedía 4 tipos; la sección 4.2.2 lista además presupuesto ejecutado negativo, prácticas sin
  empresa y convenios sin fecha de fin.
- Decisión: se insertan los 7 tipos (13 claves, con conteos exactos y disjuntos), documentados en
  `datos_sinteticos/defectos.md`.

## Decisiones sobre las contradicciones y huecos del diseño (2026-11-11)
Los 12 puntos detectados al dividir el documento quedan resueltos así. D-06 a D-08 las tomó Daniel;
D-09 a D-17 se resolvieron con la opción mínima. La lista original se conserva al final.

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
- Consecuencia: el periodo aplicado por defecto viaja como aviso para el anexo. Si el periodo lo da un filtro
  temporal, la spec resuelta lleva `periodo = null` (ver D-21).

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

### D-18 · Nombres de los esquemas y agnosticismo del motor (2026-11-11)
- Decisión: los esquemas se llaman literalmente `ana_` y `rpt_` (Figura 10: `ana_.agg_facturacion_mes`); las
  tablas de `rpt_` conservan el prefijo de la Figura 6 (`rpt_.rpt_metrica`). La fuente de verdad del DDL son los
  metadatos de SQLAlchemy (`dw/esquema.py`, `trazabilidad/esquema.py`); `sql/ana_rpt_postgresql.sql` se genera.
- `sk_fecha` es un entero AAAAMMDD. Los indicadores (`finalizada`, `a_tiempo`, `renovado`, `docs_completos`) son
  enteros 0/1 para poder sumarlos en cualquier motor.
- Tablas que el diseño menciona sin detallar y se agregaron: `agg_facturacion_mes` (Figura 10),
  `agg_proyecto_linea_mes` (4.3.2), `etl_ejecucion`, `etl_marca_calidad` y `etl_huella_fila` (4.3.2, D-17).
  Cada hecho lleva `marca_calidad`. `hecho_practica` lleva `seudonimo_estudiante` para contar personas.
- Consecuencia: si el motor del CIUMB no admite esquemas (MySQL los trata como bases), se cambia el nombre en
  un solo lugar (`ESQUEMA_ANA`, `ESQUEMA_RPT`); las pruebas usan SQLite con los esquemas traducidos a ninguno.

### D-19 · Extensiones de la capa semántica frente a la Figura 6 (2026-11-11)
- `rpt_metrica.expresion_sql` no es SQL libre: es una gramática cerrada (`*`, `columna`, `[100 *] num / den`)
  cuyos nombres se resuelven contra las tablas de `ana_`. Un registro nuevo (RF-22) no puede inyectar SQL.
- Columnas agregadas a `rpt_metrica`: `descripcion`, `agregacion_defecto`, `columna_personas` (qué columna cuenta
  personas, para suprimir grupos < 5) y `agregados_json` (agregados precalculados alternos).
- Columnas agregadas a `rpt_dimension`: `descripcion`, `viaja_a_ia` (empresa y macroproyecto no viajan) y
  `binaria_de_metrica`.
- `estado_hito` (P4) es una dimensión binaria derivada de la razón `pct_hitos_atrasados`: sus dos categorías
  (atrasado, a tiempo) salen de los componentes de la razón (num, den - num) agrupados por la otra variable.
  Así el chi-cuadrado de P4 se responde desde `hecho_proyecto`, que sí tiene facultad (ver D-11).
- La compatibilidad no se escribe a mano: se deriva de las claves foráneas de `ana_` (matriz de bus) menos las
  exclusiones declaradas (D-13).
- Plantillas base: se sembraron 8 (INF-INV-01, INF-INV-02, INF-COS-02, INF-EMP-03, INF-TRA-04 a 07), con nombres
  provisionales. El diseño habla de 18 y no las enumera: las otras 10 quedan pendientes de la lista de Daniel.
  La plantilla INF-INV-02 usa histograma: el diagrama de caja que menciona la Figura 15 no es uno de los seis
  tipos de RF-15.

### D-20 · Alcance por rol: si no se puede aplicar, se niega (2026-11-11)
- Contexto: RF-21 dice que un coordinador ve su facultad y un tutor las prácticas a su cargo, pero varios hechos
  no tienen facultad ni persona en la matriz de bus (convenios, consultorías, hitos, accesos).
- Decisión: directivo y administrador no tienen restricción. Coordinador: solo métricas que se registran por
  facultad; se agrega `facultad = alcance.facultad`. Tutor: solo `hecho_practica`, filtrado por su seudónimo.
  Consultor: solo `hecho_consultoria`, filtrado por su seudónimo (consultor líder, D-12). Si el alcance no se
  puede aplicar a una métrica, la solicitud queda fuera de alcance (`ALCANCE_NO_APLICABLE`); nunca se entrega sin
  restringir. Un filtro del prompt que pida otra facultad se rechaza (`ALCANCE_EXCEDIDO`).
- Pregunta para integración: qué módulos ve cada rol (`rol.alcance_modulos`) y si el coordinador debe ver
  convenios y consultorías de todo el centro. Hoy no los ve.

### D-21 · Reglas de resolución del validador de specs (2026-11-11)
- Tres estados y a quién va cada problema: un error de forma (paso 1) es `corregible` con `para: "ia"` (la
  capa de IA corrige la spec); lo que falta o es ambiguo es `corregible` con `para: "usuario"`; lo que la capa
  semántica no tiene, un cruce que la matriz de bus no permite, datos personales o alcance es
  `fuera_de_alcance`.
- Un código que no existe nunca se reemplaza por el más parecido: si hay parecidos (similitud >= 0,75) se
  devuelven como opciones (`METRICA_PARECIDA`); si no, `METRICA_INEXISTENTE`.
- El validador recibe la fecha de referencia (`hoy`) como parámetro. Último periodo cerrado = del 1 de enero
  del año del último mes calendario completo hasta el fin de ese mes. Un `periodo.hasta` posterior se recorta
  con aviso (`PERIODO_RECORTADO`).
- Si el periodo lo da un filtro temporal (D-08), la spec resuelta lleva `periodo = null` y la consulta se
  acota solo con el filtro; el empaquetador del contrato toma `desde` y `hasta` del rango real de los datos.
- Nivel de lectura: `registro` (una fila por proyecto, práctica o consultoría) para descriptiva y atípicos sobre
  medidas, t de Student, Mann-Whitney, correlación sin dimensiones, mediana e histograma; `agregado` en lo
  demás. La mediana se calcula con pandas porque no es portable en SQL.
- `revisar_datos` aplica después de la consulta lo que depende de los datos: supresión de grupos con menos de
  cinco personas distintas, pronóstico con menos de 12 puntos, histograma con menos de 20 observaciones, torta
  con más de seis sectores o con negativos y mapa de calor de menos de 3 x 3.
- Sin tipo pedido y con dos dimensiones se recomiendan barras agrupadas; si el cruce real tiene al menos
  3 x 3 y más de 30 celdas, pasa a mapa de calor (así se concreta «muchas celdas» de la Tabla 21).

### D-22 · Reglas del compilador de consultas (2026-11-11)
- Instantáneas periódicas (Tabla 17): una medida no se suma entre fechas de corte. Si la consulta agrupa por
  tiempo se toma el último corte de cada periodo (mes, trimestre, semestre o año); si no, el último corte del
  periodo completo. Así se lee «en la última fecha de corte del periodo» de 4.3.2.
- El periodo se filtra sobre la clave de fecha del hecho (`sk_fecha`, entero AAAAMMDD). Sin periodo (filtro
  temporal, D-08) se agrega `sk_fecha <= corte` para no leer meses sin cerrar.
- Un plan puede tener varias consultas: una `principal` por hecho o agregado (P8 usa tres, que el motor une
  por la dimensión común) y una `prueba` con la tabla de contingencia del chi-cuadrado (D-06).
- Las dimensiones se unen con LEFT JOIN: un registro sin línea o sin empresa queda en un grupo nulo en vez de
  desaparecer del conteo.
- Los registros con `marca_calidad` se incluyen en los cálculos (el diseño dice que no se descartan). Si el
  CIUMB prefiere excluirlos de los indicadores, es un filtro más en el compilador.
- Huella del plan = SHA-256 del SQL compilado con el dialecto genérico más los parámetros; no depende del
  motor de base de datos. `huella_datos` = SHA-256 de los datos devueltos.
- El seudónimo de una persona es SHA-256 de `sal:id` (`ciumb_analitica.seudonimo`); la sal se lee de
  `SAL_SEUDONIMIZACION` y debe tener al menos 16 caracteres.

### D-23 · Reglas del validador de cifras (2026-11-11)
- La tolerancia de media unidad del último decimal mostrado cubre el redondeo a 0, 1 y 2 decimales del paso 3
  y también a más decimales (un valor p de 0,0312 se puede escribir 0,031). La media unidad exacta se acepta en
  ambos sentidos (0,125 como 0,12 o 0,13). Truncar no es redondear: 412 no vale para 412,6.
- Año = entero de cuatro dígitos entre 1900 y 2100, sin signo, sin punto de miles y sin `%`. Riesgo aceptado:
  un conteo que valga, por ejemplo, 2025 y se escriba sin punto de miles se toma por año y no se verifica; la
  plantilla siempre escribe el punto de miles (2.025).
- Un número con `%` solo coincide con `variacion_pct`, con valores cuya unidad es un porcentaje o con una
  proporción (`unidad: "proporcion"`, `valor_p`) multiplicada por cien. Una proporción escrita como 13,7 sin
  `%` se rechaza.
- Un valor negativo se puede escribir sin signo («cayó 5,2 %»). Lo contrario no.
- También se admiten los números escritos en los textos del contrato (advertencias, método, etiquetas, ids) y
  los parámetros del análisis que pase quien orquesta (`extra`: alfa, nivel de confianza, k).
- Una cifra que la IA calcule por su cuenta (una resta, una suma) es discrepancia aunque sea correcta: si hace
  falta, debe venir en el contrato.
- La regeneración es una función inyectada; este repositorio no llama a ningún LLM. Si la función falla o
  devuelve nada, se pasa a la plantilla (modo degradado, RF-11). La plantilla también se valida: si cita una
  cifra ajena al contrato es un defecto del servicio (`PlantillaInvalida`).
- `rpt_validacion` guarda las cifras del último texto de la IA evaluado; el detalle por intento queda en
  `ResultadoFinal.intentos`.
- Formato de la narrativa (BORRADOR, lo define la capa de IA): `{"secciones": [{"id", "texto"}]}`.

## Decisiones de la sesión 2 (2026-11-19): motor, ML, gráficos, contrato, ETL, exportación y API

### D-24 · Pruebas y avisos del motor y de ML · APROBADA por Daniel (2026-11-19)
- `tests/motor/test_inferencia.py` comparaba `obtenido.significativo is (esperado.pvalue < 0.05)`. El lado derecho
  es `numpy.bool_` y `True is numpy.True_` es falso aunque el valor coincida. Se cambió `is` por `==` en las dos
  líneas (no cambia lo que la prueba exige). La alternativa —devolver `numpy.bool_`— rompía el tipo `bool` del
  resultado y su serialización a JSON. **Única prueba existente modificada en esta sesión** (además de quitar las
  marcas `xfail`).
- El pronóstico que no mejora a la línea base ingenua lleva el aviso `PRONOSTICO_SIN_MEJORA`. Con la
  aprobación, el código vive en `spec/resultado.py` con los demás avisos (constante nueva; nada existente cambió)
  y `ml/pronostico.py` lo reexporta.

### D-25 · Cómo carga cada tabla el ETL (aplica D-17 y D-18)
- Instantáneas periódicas (`hecho_proyecto`, `hecho_convenio`, `hecho_macroproyecto`): modo `completa` por corte
  (se borra el corte y se vuelve a insertar). Una foto del mes necesita todas las filas, cambien o no.
- `hecho_practica` (acumulativa, la vista tiene `fecha_modificacion`): lee solo las filas con `fecha_modificacion`
  posterior al inicio de la última carga exitosa de esa tabla (`etl_ejecucion`). Fechas sin zona horaria: la
  fuente y el servicio deben usar la misma hora local.
- `hecho_hito` y `hecho_consultoria` (sin fecha de modificación): huella de la fila **del hecho ya armado**, no
  de la fila de origen. Así un cambio en una tabla hija (una factura nueva, un consultor más) también se detecta.
- `hecho_acceso_diario`: se recalcula completo hasta el corte (los accesos no cambian, solo se agregan).
- `agg_facturacion_mes` se carga en `cargar_hechos` y no en `recalcular_agregados`: sale de
  `factura_consultoria`, que no tiene hecho propio en `ana_` y no se puede recalcular sin la fuente.
- `dim_estado` se llena con los estados **observados** en la fuente por módulo (`investigacion`, `practicas`,
  `convenios`…, como en las pruebas del compilador), incluidos los que están fuera del catálogo: el registro se
  carga marcado, no se descarta. Un estado nulo se carga como `sin_estado`. `es_final` sale de
  `ESTADOS_FINALES` en `etl/carga.py` (PROVISIONAL hasta el catálogo oficial).
- `dim_persona_rol`: una fila por (seudónimo, rol, tipo de participación): tutor académico, consultor (líder o
  no), coordinador de macroproyecto y usuario con su rol (para los accesos).
- SCD tipo 2 de `dim_macroproyecto`: la primera versión es vigente desde `fecha_inicio`; un cambio cierra la
  vigente el día anterior a la carga y abre otra desde el día de la carga. Repetir la carga el mismo día corrige
  la versión abierta ese día en lugar de abrir otra. Un cambio solo de nombre se corrige en el lugar (SCD 1).
- Cada tabla se escribe en un punto de guardado: si falla, se deshace solo esa tabla, el error queda en
  `etl_ejecucion` y las tablas que dependen de ella (por clave foránea) se omiten con el motivo.
- `cargar_cortes_historicos` no escribe en `etl_marca_calidad`: un registro defectuoso aparece en cada corte y
  registrarlo 94 veces inflaba INF-TRA-08 (en PostgreSQL se vio: 384 marcas para 10 proyectos). Los hechos de cada
  corte sí llevan `marca_calidad`; el conteo sale de la ejecución nocturna.
- El catálogo de estados del servicio vive en `etl/programacion.py` (copia de `datos_sinteticos`, D-04); una
  prueba exige que coincidan mientras no llegue el oficial.

### D-26 · Exportación: filtro de PII, formato de cifras y CSV
- El filtro de PII revisa título, anexo y tablas con la lista completa. En la narrativa solo busca correos y NIT:
  sus números ya pasaron el validador de cifras y un total como «1.250.000» tiene la forma del patrón de
  documento. Los SHA-256 (huellas) se excluyen antes de revisar, como `huella_datos` en el contrato.
- Una columna de tabla se muestra con los decimales que necesita su valor más preciso (365,0 y 412,6). Las
  columnas de tiempo se combinan en una etiqueta de periodo («2026-T1») para que un año no salga como «2.026».
- CSV: UTF-8 con BOM, `;`, coma decimal y sin punto de miles. HTML: autocontenido, gráficos en PNG base64 (no se
  incrusta plotly.js; la figura Plotly queda en `Grafico.plotly` para el chatbot).

### D-27 · Identidad visual (PROVISIONAL)
- `exportacion/identidad.py` concentra colores y tipografías: rojo institucional para la marca y azul oscuro para
  los datos (4.5). Los valores hexadecimales son provisionales hasta recibir el manual de marca de la UMB.

### D-28 · Orquestación y API (BORRADOR hasta cerrar la interfaz con la capa de IA)
- La capa de IA entra como un puerto (`api.flujo.Redactor`: `redactar(contrato)` y `regenerar(contrato,
  anterior, discrepancias)`). Sin redactor, o si falla, el informe sale con la plantilla (RF-11). El cliente HTTP
  hacia la capa de Laura se escribe cuando ella confirme los puntos 7 y 9 de `docs/interfaz_capa_ia.md`.
- Rutas: `GET /salud` (sin token), `GET /semantica`, `GET /informes/catalogo?rol=`, `POST /informes/personalizado`
  (`{spec, prompt?, formatos?, id_usuario?}`), `POST /informes` (`{codigo, alcance, periodo?, formatos?}`),
  `GET /informes/{id}/descargar?formato=`. Todas menos `/salud` exigen `Authorization: Bearer <SERVICIO_TOKEN>`;
  sin token configurado responden 503. Una spec no válida responde **200** con `estado` y `problemas` (para que
  la capa de IA repregunte); 422 queda para peticiones mal formadas.
- `rpt_especificacion.spec_json` guarda la spec **tal como llegó**; `huella_spec`, la de la resuelta. Para
  reproducir (RNF-11) se vuelve a validar con la fecha de la solicitud y se exige la misma huella; si la capa
  semántica cambió, la descarga responde 409 en lugar de entregar otro informe.
- Caché de RF-13: `rpt_narrativa_cache` guarda solo textos de la IA ya aprobados. La llave es la huella del
  contrato **sin** `especificacion.id` (que cambia en cada solicitud): misma spec y mismos datos, mismo texto, sin
  llamar a la IA.
- `rpt_validacion` se escribe con `ResultadoFinal.registro()` (una fila por informe, en el primer formato).
- Las advertencias de la validación y de la revisión de datos van a la primera sección del contrato.
- Conexiones: `DATABASE_URL_LECTURA` (solo `ana_`, marcada de solo lectura en PostgreSQL) y `DATABASE_URL_RPT`
  (escritura en `rpt_`). Falta crear en `sql/` un rol con escritura solo en `rpt_` (hoy, en desarrollo, el admin).

### D-29 · Carga histórica de cortes mensuales
- `carga.cargar_cortes_historicos` (y `python -m ciumb_analitica.etl --historico AAAA-MM`) construye un corte por
  fin de mes para las instantáneas periódicas. Sin ella, `ana_` solo tiene el último mes cerrado y P1, P3, P4 y
  P9 no tienen serie.
- Limitación: la fuente no guarda la historia de estados, así que un corte pasado usa el estado ACTUAL de cada
  registro (los que existían a esa fecha sí se filtran por creación, inicio o firma). Las medidas que dependen
  de la fecha (hitos atrasados, días para vencer) sí se calculan al corte.

### D-30 · Del método de la spec a las secciones del contrato (`motor/analisis.py`)
- Cada sección trae todas las cifras que el texto puede citar: valores por grupo, total, máximo, número de grupos
  y, según el método, estadístico con valor p y n, grados de libertad, intervalos, MAE del modelo y de la línea
  base, tamaños y centroides. Los parámetros (alfa, nivel de confianza, k, horizonte) van en `extra`.
- Total de una métrica: aditiva = suma; razón = desde `__num`/`__den`; **semiaditiva con tiempo = el último corte**
  (nunca la suma de los cortes). La variación interanual de una semiaditiva compara el último corte con el mismo
  corte del año anterior. Un corte que falta queda vacío, no en 0.
- Una dimensión con `viaja_a_ia = False` (empresa, macroproyecto) no aparece en `grupo`: se publican los totales
  con una advertencia, y el detalle queda en las tablas del informe.
- Segmentación: un grupo con menos de 5 unidades publica su tamaño pero no su centroide (sería la actividad de
  esas empresas concretas; misma regla que la supresión de grupos < 5).
- Más de 60 grupos: se publican los 60 mayores con advertencia (el contrato admite 200 indicadores por sección).
- Si los datos reales no admiten el método (la dimensión no tiene dos grupos, el chi-cuadrado queda en menos de
  2 × 2, la serie no alcanza), la solicitud vuelve como `corregible` con `METODO_NO_APLICABLE` para repreguntar.

### D-31 · Observaciones para revisar con Daniel (no se cambió nada cerrado)
- P8: `revisar_datos` suprime las empresas con menos de cinco estudiantes en la consulta de prácticas antes de
  unir las tres consultas, así que muchas empresas entran a k-medias con 0 prácticas. Con los datos sintéticos la
  silueta elige k = 10 (el máximo) con grupos diminutos. Es correcto frente a la regla de privacidad, pero
  conviene decidir si la supresión debe aplicarse a la entrada de la segmentación o solo a lo que se publica.
- El estado de `rpt_especificacion` queda `valida` aunque luego el compilador o el motor rechacen la spec (la
  solicitud sí queda `rechazada`). Si se quiere un solo estado, hay que tocar el esquema `rpt_` (cerrado).
- Una excepción inesperada durante la exportación deshace la transacción de `rpt_`, así que esa solicitud no queda
  registrada. Registrar errores exige una segunda transacción; queda pendiente.

### D-32 · Entorno Docker de desarrollo y despliegue del servicio (2026-11-19)
- `Dockerfile`: Python 3.12 slim + uv 0.12.17 + Pango y HarfBuzz (WeasyPrint) + fuentes DejaVu; corre Uvicorn
  con un usuario sin privilegios. `.dockerignore` deja fuera `.env`, `.venv`, `.git` y `docs`.
- El contenedor `ciumb_db` se recreó sobre el volumen existente `motor_estadistico_capa_analitica_ciumb_datos_db`
  (conservaba la fuente `ciumb`); `ana_` y `rpt_` se aplicaron con `sql/ana_rpt_postgresql.sql`.
- `ciumb_lector` recibió LOGIN con la contraseña de `DATABASE_URL_LECTURA` (lo que indica el DDL, fuera de git):
  el servicio lee `ana_` con ese rol de solo lectura (invariante 3). En desarrollo, `DATABASE_URL_RPT`,
  `DATABASE_URL_FUENTE` y `DATABASE_URL_ANA_ESCRITURA` usan el admin (falta el rol de escritura en `rpt_`, D-28).
- En `.env` se generaron al azar `SAL_SEUDONIMIZACION` y `SERVICIO_TOKEN` (no están en git).
- Si el servidor no puede producir un formato (PDF sin Pango, p. ej. en Windows), la API responde 503 con el
  motivo (`FormatoNoDisponible`) en lugar de 500.
- Resultado: ETL sobre PostgreSQL sin errores (94 cortes, marcas iguales a los defectos sembrados); P1–P10 por
  HTTP contra el contenedor del servicio con los resultados de la Tabla 22; 9 PDF generados y descargados; suite
  completa en Linux: 701 en verde, sin omitidas.
- En Windows, la primera segmentación de un proceso tardó 21 s (arranque de scikit-learn/OpenBLAS); en Linux,
  P8 completo tarda 1,9 s.

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
    la lista de la Figura 9. Se creó `GET /salud`.
12. **Carga incremental:** la Figura 2 dice «carga incremental por fecha de modificación», pero ninguna tabla del
    ER inferido tiene esa columna; 4.3.2 aclara que hay respaldo por huella de fila (ver D-04).
