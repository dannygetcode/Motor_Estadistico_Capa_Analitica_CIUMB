# Interfaz entre la capa de IA y el área analítica — BORRADOR para revisión

Para: Laura Valentina Maldonado (capa de IA). De: Daniel Barragán (área analítica). Fecha: 2026-11-11.

**Estado: borrador.** Nada de esto está cerrado hasta que lo revises. Lo que necesito de ti está al final,
en «Puntos por confirmar». Mientras siga en borrador, cambiarlo no cuesta nada; después, cambiar el contrato
exige subir su versión.

Son dos documentos JSON:

| | Quién lo escribe | Quién lo lee | Esquema |
|---|---|---|---|
| **Especificación** `ciumb.spec/1.0` | Tu capa, a partir del prompt | El área analítica | `schemas/ciumb.spec-1.0.schema.json` |
| **Contrato** `ciumb.informe/2.0.0` | El área analítica, con las cifras ya calculadas | Tu capa, para redactar | `schemas/ciumb.informe-2.0.0.schema.json` |

Los esquemas son JSON Schema (draft 2020-12): puedes validar con cualquier librería, sin depender de este
repositorio. Hay ejemplos válidos de los diez prompts de la Tabla 22 en `schemas/fixtures/p01.json` … `p10.json`
y ejemplos rechazados en `schemas/fixtures/rechazados/`.

Tres reglas valen para los dos documentos:

1. **Un campo que no esté en el esquema invalida el documento.** No hay campos libres.
2. **Los tipos son estrictos.** `"6"` no es un entero.
3. **Tu capa nunca escribe SQL ni calcula cifras.** Solo nombra métricas y dimensiones por su código; los
   códigos salen de la capa semántica publicada (`GET /semantica`), que trae nombres, descripciones y sinónimos,
   sin datos ni nombres de tablas.

---

## 1. Especificación `ciumb.spec/1.0` (lo que tu capa envía)

| Campo | Obligatorio | Contenido | Si lo omites |
|---|---|---|---|
| `esquema` | sí | Siempre `"ciumb.spec/1.0"` | — |
| `origen` | sí | `"prompt"`, `"plantilla_base"` o `"guardada"` | — |
| `base` | solo si `origen` es `plantilla_base` | Código de la plantilla, p. ej. `"INF-INV-02"` | `null` |
| `metricas` | sí, de 1 a 5 | Lista de `{ "id", "agregacion"? }`. `agregacion`: `conteo`, `suma`, `promedio`, `mediana` o `razon` | Sin `agregacion`: la que la métrica tiene por defecto |
| `dimensiones` | no, hasta 3 | Lista de `{ "id", "granularidad"? }`. **Es la agrupación del gráfico.** `granularidad` solo para la dimensión `tiempo`: `mes`, `trimestre`, `semestre` o `anio` | Se calcula el total, o se lee registro a registro si el método lo necesita |
| `filtros` | no | Lista de `{ "campo", "op", "valor" }`. `op`: `=`, `!=`, `>`, `>=`, `<`, `<=`, `en` (lista), `entre` (lista de dos) | Sin filtros |
| `periodo` | no | `{ "desde", "hasta", "corte"? }`, fechas `AAAA-MM-DD` | Si hay un filtro sobre una dimensión temporal (p. ej. `periodo_academico`), ese filtro es el periodo. Si no hay ninguno, se usa el último periodo cerrado y el informe lo declara |
| `analisis` | no | Objeto con `metodo` y sus parámetros (tabla siguiente) | `descriptiva` |
| `grafico` | no | `{ "tipo", "origen"?, "max_sectores"?, "reemplaza"? }`. `tipo`: `barras`, `lineas`, `torta`, `dispersion`, `mapa_calor`, `histograma` | **Omítelo si el prompt no menciona un tipo**: lo elige el recomendador |
| `alcance` | sí | `{ "rol", "facultad"?, "id_usuario"? }`. **Lo pone el backend del CIUMB, no tu capa.** Cópialo tal cual llegue | — |
| `salida` | no | `{ "formatos"?, "secciones"? }`. Formatos: `pdf`, `docx`, `xlsx`, `html`, `csv` | Vista en el chatbot |

Métodos de `analisis`:

| `metodo` | Parámetros | Notas |
|---|---|---|
| `frecuencias` | `relativas` (booleano) | |
| `descriptiva` | `atipicos`: `{ "metodo": "RIC" o "puntaje_z", "k" }` | Media, mediana, desviación, cuartiles |
| `serie` | `acumulado` (booleano) | Necesita la dimensión `tiempo` |
| `variacion`, `variacion_interanual` | — | Frente al periodo anterior o al mismo periodo del año anterior |
| `pearson`, `spearman` | `variables`: dos métricas; `alfa` | |
| `chi_cuadrado` | `variables`: dos dimensiones; `alfa` | |
| `t_student`, `mann_whitney` | `variables`: `[métrica, dimensión de dos grupos]`; `alfa` | |
| `atipicos` | `tecnica`: `RIC` o `puntaje_z`; `k` | |
| `pronostico` | `tecnica`: `holt` o `regresion_lineal`; `horizonte`; `nivel_confianza` | Necesita `tiempo` y al menos 12 puntos: **envía el periodo histórico completo** |
| `segmentacion` | `tecnica`: `kmedias`; `k` (si se omite, se elige por silueta) | |

`analisis.variables` **no tiene que repetir** lo que hay en `dimensiones`: `dimensiones` es lo que se dibuja y
`variables` es lo que cruza la prueba. Las dos se validan contra la capa semántica.

### Ejemplo válido (P4 de la Tabla 22, Figura 14)

```json
{
  "esquema": "ciumb.spec/1.0",
  "origen": "prompt",
  "base": null,
  "metricas": [ { "id": "pct_hitos_atrasados" } ],
  "dimensiones": [ { "id": "facultad" }, { "id": "tiempo", "granularidad": "trimestre" } ],
  "periodo": { "desde": "2026-01-01", "hasta": "2026-09-30" },
  "analisis": { "metodo": "chi_cuadrado", "variables": [ "facultad", "estado_hito" ], "alfa": 0.05 },
  "grafico": { "tipo": "mapa_calor", "origen": "prompt" },
  "alcance": { "rol": "directivo" }
}
```

### Ejemplo rechazado (resumido de `schemas/fixtures/rechazados/spec_campo_desconocido.json`)

```json
{
  "esquema": "ciumb.spec/1.0",
  "origen": "prompt",
  "metricas": [ { "id": "facturacion", "agregacion": "suma" } ],
  "dimensiones": [ { "id": "tiempo", "granularidad": "mes" } ],
  "alcance": { "rol": "directivo" },
  "sql": "SELECT * FROM usuario"
}
```

Se rechaza por el campo `sql`, que no existe en el esquema. Otros rechazos de forma que hay en la carpeta:
sin `metricas`, identificador con caracteres no permitidos, método desconocido, coordinador sin `facultad`,
entero enviado como texto.

### Qué responde el área analítica a una spec

Pasar el esquema no basta: después la spec se valida contra la capa semántica. La respuesta es una de tres.

| Resultado | Significa | Qué hace tu capa |
|---|---|---|
| `valida` | Sigue al cálculo. Puede traer **avisos** (p. ej. `GRAFICO_SUSTITUIDO`: se pidió torta para una serie de tiempo y se entrega en líneas; `PERIODO_POR_DEFECTO`) | Nada; los avisos llegan en el contrato como advertencias |
| `corregible` | Falta algo o hay ambigüedad (p. ej. dos métricas parecidas). Trae la lista de problemas | Repreguntar al usuario |
| `fuera_de_alcance` | Pide algo que la capa semántica no tiene o datos personales (P10). Trae el motivo y qué sí existe | Explicarlo al usuario |

El sistema nunca adivina una métrica: si el prompt no alcanza para elegirla, no la inventes; deja que la
validación devuelva `corregible`.

---

## 2. Contrato `ciumb.informe/2.0.0` (lo que tu capa recibe)

| Campo | Contenido |
|---|---|
| `contrato` | Siempre `"ciumb.informe/2.0.0"` |
| `especificacion` | `{ "id", "origen", "base", "grafico": { "tipo", "origen" } }`. El gráfico es **el que el usuario ve** (el final, no el pedido) |
| `periodo` | `{ "desde", "hasta", "corte" }`, siempre completo |
| `alcance` | `{ "rol", "facultad"? }`. Nunca trae el usuario |
| `secciones` | Lista de `{ "id", "indicadores", "metodo", "advertencias" }` |
| `huella_datos` | `"sha256:"` + 64 hexadecimales. Identifica los datos; sirve de llave para tu caché de narrativa |

Cada indicador:

| Campo | Obligatorio | Contenido |
|---|---|---|
| `id` | sí | Código del indicador |
| `valor` | sí | La cifra, sin redondear para presentación |
| `anterior`, `variacion_pct` | no | Valor del periodo de comparación y variación porcentual |
| `unidad` | no | `"millones COP"`, `"%"`, `"dias"`… `"proporcion"` = valor entre 0 y 1 que puedes escribir como porcentaje |
| `n` | no | Tamaño de la muestra |
| `meta` | no | Meta, si aplica |
| `metodo` | no | Si viene, **reemplaza** al `metodo` de la sección para ese indicador |
| `mes` | no | Mes del valor, `AAAA-MM` |
| `grupo` | no | Categoría del valor: `{ "facultad": "Ingeniería", "estado": "en_ejecucion" }` |
| `valor_p`, `ic_inferior`, `ic_superior` | no | Valor p de la prueba e intervalo de confianza |

Las `advertencias` de una sección son obligatorias en el texto (muestra pequeña, gráfico sustituido, grupos
suprimidos por tener menos de cinco personas).

### Ejemplo válido (`schemas/fixtures/contrato_p03.json`, Figura 12)

```json
{
  "contrato": "ciumb.informe/2.0.0",
  "especificacion": {
    "id": "esp-20261105-0042", "origen": "prompt", "base": null,
    "grafico": { "tipo": "lineas", "origen": "prompt" }
  },
  "periodo": { "desde": "2025-01-01", "hasta": "2026-10-31", "corte": "2026-10-31" },
  "alcance": { "rol": "directivo" },
  "secciones": [
    {
      "id": "facturacion_consultorias",
      "indicadores": [
        { "id": "facturacion_ene_oct", "valor": 412.6, "anterior": 365.0,
          "variacion_pct": 13.0, "unidad": "millones COP", "n": 118 },
        { "id": "mes_mayor_facturacion", "mes": "2026-06", "valor": 58.3 }
      ],
      "metodo": "suma mensual; variación frente al mismo periodo del año anterior",
      "advertencias": []
    }
  ],
  "huella_datos": "sha256:<64 caracteres hexadecimales>"
}
```

### Ejemplo rechazado (`schemas/fixtures/rechazados/contrato_pii_correo.json`)

El mismo paquete con esta sección:

```json
"advertencias": [ "Dato reportado por juan.gomez@empresa.com" ]
```

El esquema lo acepta, pero el filtro de PII lo bloquea antes de enviarlo: ningún texto del paquete puede
parecer un correo, un número de documento o un NIT. Otros rechazos en la carpeta: campo desconocido en un
indicador, huella truncada, `alcance.id_usuario`, versión distinta de 2.0.0.

La lista de patrones es `PATRONES_PII` en `src/ciumb_analitica/contrato/pii.py`. El diseño pide que tu capa
aplique **la misma lista** al prompt antes de enviarlo a un proveedor (sección 4.4.1).

---

## 3. Qué pasa con el texto que devuelves

El validador de cifras extrae todos los números de tu narrativa y los compara con el contrato.

- Acepta formato español: coma decimal, punto de miles y `%` (`412,6`, `1.250`, `13 %`).
- Acepta cada valor tal como viene y redondeado a 0, 1 o 2 decimales, con tolerancia de media unidad del
  último decimal que escribas. `412,6` y `413` pasan para `412.6`; `412,9` no.
- Un valor con `unidad: "proporcion"` (p. ej. `0.137`) se puede escribir como `13,7 %`.
- No cuentan como cifras: los años, las fechas del periodo y los códigos de informe (`INF-INV-02`).
- **Cualquier otro número que no esté en el contrato es una discrepancia.** No calcules sumas, diferencias ni
  porcentajes nuevos en el texto: si hace falta una cifra, debe venir en el contrato.
- Si hay discrepancias se te pide regenerar indicando cuáles cifras fallaron, máximo dos veces. Si persisten,
  el informe sale con el texto de plantilla.

---

## Puntos por confirmar contigo

1. **`analisis.variables` separado de `dimensiones`** (así está en la Figura 14). ¿Te sirve o prefieres
   declararlas siempre en `dimensiones`?
2. **`metodo` por sección, con reemplazo opcional por indicador.** El texto del diseño lo pone por indicador y
   la Figura 12 por sección.
3. **`periodo` opcional.** ¿Tu intérprete puede enviar siempre el periodo explícito cuando el prompt lo dice
   («este año», «2026-2»), o prefieres que lo resolvamos nosotros?
4. **Granularidad `anio`** (sin tilde ni ñ) en lugar de `año`, por la convención de nombres del repositorio.
5. **Atípicos:** anidados en `descriptiva` usan `{ "metodo": "RIC" }` (Figura 15); como análisis propio usan
   `"tecnica": "RIC"`. ¿Lo unificamos?
6. **Indicadores por categoría:** usamos `grupo` (general) y `mes` (como en la Figura 12). ¿Te alcanza para
   redactar un cruce de dos dimensiones?
7. **Formato de la narrativa que devuelves.** Propuesta mínima, ya implementada del lado analítico:
   `{ "secciones": [ { "id", "texto" } ] }`, con los mismos `id` de sección del contrato. Este formato lo
   defines tú; si prefieres otro, se cambia.
8. **Respuesta a una spec no válida.** Ya está implementada: `{ "estado", "problemas": [ { "codigo", "paso",
   "campo", "mensaje", "para", "opciones" } ] }`. `para` vale `"ia"` cuando el error es de forma y tu capa puede
   corregir la spec sin molestar al usuario, y `"usuario"` cuando hay que repreguntar; `opciones` trae los
   códigos que sí sirven. ¿Te alcanza para armar la repregunta?
9. **Petición de regeneración.** Tu capa recibe la narrativa anterior y la lista de cifras que fallaron:
   `[ { "seccion", "texto", "valor", "contexto" } ]` (`texto` es la cifra tal como la escribiste y `contexto`
   unos 30 caracteres a cada lado). Máximo dos regeneraciones.
10. **Parámetros del análisis en el texto.** El nivel de confianza (95 %) o el alfa (0,05) no viajan como
    indicadores; el validador los admite porque los toma de la spec. ¿Los necesitas dentro del contrato?
