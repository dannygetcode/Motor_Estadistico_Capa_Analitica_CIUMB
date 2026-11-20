# Servicio de informes del área analítica (FastAPI + Uvicorn). Imagen Linux: WeasyPrint necesita Pango.
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1

# Dependencias primero (capa en caché); luego el código.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev --extra postgres
COPY src ./src
RUN uv sync --frozen --no-dev --extra postgres

# Usuario sin privilegios.
RUN useradd --create-home servicio && mkdir -p /app/informes_generados && chown servicio /app/informes_generados
USER servicio

EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn", "ciumb_analitica.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
