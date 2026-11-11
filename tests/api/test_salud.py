from fastapi.testclient import TestClient

from ciumb_analitica import __version__
from ciumb_analitica.api.app import app


def test_salud_responde_ok():
    respuesta = TestClient(app).get("/salud")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok", "version": __version__}
