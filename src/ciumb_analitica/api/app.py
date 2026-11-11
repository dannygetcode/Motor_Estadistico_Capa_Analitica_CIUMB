"""Aplicación FastAPI del servicio de informes."""

from fastapi import FastAPI

from ciumb_analitica import __version__

app = FastAPI(title="Servicio de informes CIUMB — área analítica", version=__version__)


@app.get("/salud")
def salud() -> dict[str, str]:
    """Indica que el servicio está arriba. No consulta la BD ni proveedores de IA."""
    return {"estado": "ok", "version": __version__}
