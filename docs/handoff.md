# Relevo entre sesiones

## Estado al cierre de la sesión 0 (2026-11-11, Opus · rama `chore/sesion-0-preparacion`)
Hecho:
- `docs/diseno/`: diseño dividido en 66 secciones + `00_indice.md` + figuras con descripción. Verificación de
  palabras: 17 547 en el docx y 17 547 en los .md (0 % de diferencia). Se regenera con
  `uv run --no-project --with python-docx python herramientas/dividir_diseno.py`.
- `schemas/ejemplos/`: JSON de las Figuras 12–15 (sus comentarios están en `README.md`). Todavía no hay JSON Schema.
- Esqueleto: `pyproject.toml` (uv, Python 3.12), ruff, pytest, pre-commit, `docker-compose.yml` (PostgreSQL 16),
  `.env.example`, paquetes vacíos de `src/ciumb_analitica/` y `GET /salud` con su prueba.
- `datos_sinteticos/`: `ddl.sql` (esquema `ciumb`, modelo inferido, provisional) y `generar.py`
  (semilla 20261111, 2019–2026, 13 claves de defecto con conteos exactos en `defectos.md`). Verificado en
  PostgreSQL: los conteos de filas y de defectos coinciden.
- `docs/decisiones.md`: D-01 a D-05 y 12 contradicciones o huecos del diseño pendientes de decidir.

Pruebas: `uv run pytest` da 9 pruebas en verde. `uv run ruff check .` sale limpio.

## Cómo levantar el entorno
1. `uv sync`
2. `cp .env.example .env` y poner una contraseña en `POSTGRES_PASSWORD` y en `DATABASE_URL_ADMIN`.
3. `docker compose up -d --wait db`. El DDL se aplica solo cuando se crea el volumen; para reaplicarlo:
   `docker compose down -v`.
4. Cargar las variables de `.env` en el shell y correr `uv run python -m datos_sinteticos.generar`
   (o `--sql archivo.sql` para volcar INSERT, o `--resumen` para ver solo los conteos).

## Siguiente tarea (sesión 1, PROMPT_1)
Interfaces de frontera: modelos Pydantic de `ciumb.spec/1.0` (Tabla 20, `4.4.2`) y del contrato 2.0.0
(`4.4.3`, Figura 12) con JSON Schema exportado a `schemas/`, y fixtures P1–P10 (Tabla 22, `4.4.4`).
Antes de empezar, decidir los puntos 7, 8 y 10 de `docs/decisiones.md`, que afectan esos modelos.

## Trampas conocidas
- Todavía no existen en el DDL el usuario de solo lectura (`ciumb_lector`) ni el esquema `ana_`.
- WeasyPrint en Windows necesita GTK para renderizar; se instala, pero no se ha probado (Sprint 3).
- En esta máquina, un `cd` a una subcarpeta puede cambiar el directorio de trabajo de la sesión: usar rutas
  relativas a la raíz.
- Docker Desktop no arranca solo; si `docker info` falla, hay que abrirlo antes del `docker compose`.
