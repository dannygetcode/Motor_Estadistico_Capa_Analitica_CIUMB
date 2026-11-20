# Motor de informes CIUMB: área analítica

Práctica Empresarial II, Ingeniería de Software, UMB. Autor: Daniel Barragán.
Supervisor: Ing. Héctor Vargas (CIUMB).

Servicio en Python/FastAPI que recibe una especificación de informe (`ciumb.spec/1.0`), la valida contra la capa
semántica, la compila a SQL, calcula las cifras, genera el gráfico y arma el contrato de datos
(`ciumb.informe/2.0.0`) que usa la capa de IA para redactar. Después revisa que las cifras del texto redactado
coincidan con las calculadas y exporta el informe (PDF, DOCX, XLSX, HTML, CSV).

## Reparto del trabajo

| Parte | Responsable |
|---|---|
| Área analítica (este repositorio) | Daniel Barragán |
| Capa de IA: prompt → spec, proveedores de IA, redacción | Laura Valentina Maldonado |
| Integración con el sistema PHP del CIUMB | Juan Stiven Castro y Manuel Bonilla |

Este servicio no llama a ningún modelo de lenguaje.

## Frontera con la capa de IA

Si trabajas la capa de IA, empieza por **`docs/interfaz_capa_ia.md`**. Ahí están los dos documentos que se
intercambian y los puntos que faltan por confirmar.

- Spec que envía la capa de IA: `schemas/ciumb.spec-1.0.schema.json`
- Contrato que recibe la capa de IA: `schemas/ciumb.informe-2.0.0.schema.json`
- Ejemplos válidos de los 10 prompts de prueba: `schemas/fixtures/p01.json` a `p10.json`
- Ejemplos que deben rechazarse: `schemas/fixtures/rechazados/`

Los esquemas son JSON Schema (draft 2020-12), así que se pueden validar desde cualquier lenguaje sin
instalar este repositorio.

## Reglas que no cambian

1. Ninguna cifra la produce la IA. Todos los números salen de SQL, pandas, SciPy, statsmodels o scikit-learn.
2. La IA no escribe SQL. Solo nombra métricas y dimensiones por su código de la capa semántica.
3. A la capa de IA solo llegan agregados, sin datos personales. Los grupos de menos de 5 personas se suprimen.
4. Sin IA, el informe se genera igual, con texto de plantilla.
5. Si cambia el contrato, sube su versión.

## Instalación

Requisitos: Python 3.12, [uv](https://docs.astral.sh/uv/) y Docker.

```bash
uv sync                                   # dependencias
cp .env.example .env                      # completar contraseñas y sal
docker compose up -d db                   # PostgreSQL de desarrollo
uv run python -m datos_sinteticos.generar # cargar datos sintéticos
uv run --env-file .env python -m ciumb_analitica.etl --historico 2019-01  # ETL a ana_ con cortes mensuales
uv run python -m pytest                   # pruebas (en Windows, `uv run pytest` puede fallar)
```

El servicio también corre en contenedor (WeasyPrint necesita Linux para el PDF):

```bash
docker build -t ciumb-analitica:dev .
docker run -d -p 8000:8000 --env-file <.env con host.docker.internal> ciumb-analitica:dev
```

Las rutas (`/salud`, `/semantica`, `/informes/catalogo`, `/informes/personalizado`, `/informes`,
`/informes/{id}/descargar`) exigen `Authorization: Bearer <SERVICIO_TOKEN>`, salvo `/salud`.

El motor de base de datos del CIUMB aún no está confirmado. El código no depende de un motor concreto y en
desarrollo se usa PostgreSQL con datos sintéticos generados a partir del modelo inferido.

## Estructura

```
src/ciumb_analitica/
  fuentes/           vistas de extracción sobre la base del CIUMB (solo lectura)
  etl/               extracción, seudonimización, reglas de calidad, carga y programación nocturna
  dw/                esquema ana_ (dimensiones, hechos, agregados)
  semantica/         métricas, dimensiones y compatibilidades publicadas
  spec/              modelos de ciumb.spec/1.0 y validador
  compilador/        spec -> SQL parametrizado
  motor/             estadística descriptiva, series de tiempo, inferencia y método -> secciones
  ml/                pronóstico, atípicos, segmentación
  graficos/          tipos de gráfico y recomendador
  contrato/          contrato 2.0.0 y filtro de datos personales
  validador_cifras/  cotejo de cifras del texto y plantilla sin IA
  exportacion/       PDF, DOCX, XLSX, HTML, CSV e identidad visual UMB
  trazabilidad/      esquema rpt_ y su escritura (solicitudes, resultados, validaciones, caché)
  api/               orquestación del flujo (flujo.py), configuración (servicio.py) y rutas FastAPI
schemas/             JSON Schema, ejemplos y fixtures
datos_sinteticos/    DDL del modelo inferido y generador con semilla fija
sql/                 DDL de ana_ y rpt_ para PostgreSQL
tests/               pruebas, con la misma estructura que src/
docs/                diseño por secciones, decisiones, backlog y estado actual
```

## Documentación

- `docs/diseno/00_indice.md`: índice del documento de diseño, dividido por secciones.
- `docs/decisiones.md`: decisiones tomadas durante la construcción que no estaban en el diseño.
- `docs/backlog.md`: historias por sprint.
- `docs/handoff.md`: estado actual y tareas pendientes.

## Convenciones

- Nombres de dominio en español sin tildes (`hecho_proyecto`, `pct_ejecucion`).
- Commits convencionales (`feat:`, `fix:`, `test:`, `docs:`), una rama por historia.
- Secretos solo en `.env`, que no se sube.
