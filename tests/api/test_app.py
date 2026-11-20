"""Rutas HTTP del servicio (D-16, D-28): token de servicio, capa semántica, catálogo, informes y descargas."""

from __future__ import annotations

import io
import zipfile

import openpyxl
import pytest
from fastapi.testclient import TestClient

from ciumb_analitica.api.app import app
from ciumb_analitica.api.servicio import Servicio
from tests.api.conftest import HOY, SAL
from tests.conftest import fixture_prompt

TOKEN = "token-de-prueba-del-backend"  # noqa: S105 - token ficticio de pruebas
CABECERA = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def cliente(entorno, tmp_path):
    app.state.servicio = Servicio(
        motor_lectura=entorno.ana, motor_rpt=entorno.rpt, sal=SAL, token=TOKEN, directorio=tmp_path, hoy=lambda: HOY
    )
    yield TestClient(app)
    app.state.servicio = None


def test_salud_no_pide_token(cliente):
    assert cliente.get("/salud").status_code == 200


@pytest.mark.parametrize("cabecera", [{}, {"Authorization": "Bearer otro"}, {"Authorization": "Basic x"}])
def test_sin_token_valido_no_se_atiende(cliente, cabecera):
    assert cliente.get("/semantica", headers=cabecera).status_code in (401, 403)
    assert cliente.post("/informes/personalizado", json={"spec": {}}, headers=cabecera).status_code in (401, 403)


def test_sin_token_configurado_el_servicio_no_atiende(entorno):
    app.state.servicio = Servicio(motor_lectura=entorno.ana, motor_rpt=entorno.rpt, sal=SAL, token=None)
    try:
        assert TestClient(app).get("/semantica", headers=CABECERA).status_code == 503
    finally:
        app.state.servicio = None


def test_semantica_publica_codigos_sin_tablas(cliente):
    cuerpo = cliente.get("/semantica", headers=CABECERA).json()
    codigos = {m["codigo"] for m in cuerpo["metricas"]}
    assert {"facturacion", "practicas", "pct_hitos_atrasados"} <= codigos
    texto = str(cuerpo)
    assert "hecho_" not in texto and "dim_" not in texto and "ana_" not in texto


def test_catalogo_por_rol(cliente):
    todos = cliente.get("/informes/catalogo", headers=CABECERA).json()
    assert len(todos) == 8
    coordinador = cliente.get("/informes/catalogo", params={"rol": "coordinador"}, headers=CABECERA).json()
    assert all("coordinador" in p["roles_permitidos"] for p in coordinador)


def test_informe_personalizado_valido_y_su_descarga(cliente):
    fixture = fixture_prompt("p03")
    respuesta = cliente.post(
        "/informes/personalizado",
        json={"spec": fixture["spec"], "prompt": fixture["prompt"], "formatos": ["html", "xlsx"], "id_usuario": 7},
        headers=CABECERA,
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "valida" and cuerpo["modo"] == "degradado"
    assert cuerpo["contrato"]["contrato"] == "ciumb.informe/2.0.0"
    assert cuerpo["validacion"]["uso_plantilla"] is True
    assert set(cuerpo["descargas"]) == {"html", "xlsx"}

    xlsx = cliente.get(f"/informes/{cuerpo['id_solicitud']}/descargar", params={"formato": "xlsx"}, headers=CABECERA)
    assert xlsx.status_code == 200 and xlsx.headers["content-type"].startswith("application/vnd.openxml")
    assert "attachment" in xlsx.headers["content-disposition"] and ".xlsx" in xlsx.headers["content-disposition"]
    assert openpyxl.load_workbook(io.BytesIO(xlsx.content)).sheetnames[0] == "Informe"

    # Un formato que no se generó se reproduce con la misma spec y la misma fecha (RNF-11).
    docx = cliente.get(f"/informes/{cuerpo['id_solicitud']}/descargar", params={"formato": "docx"}, headers=CABECERA)
    assert docx.status_code == 200 and zipfile.ZipFile(io.BytesIO(docx.content)).testzip() is None


def test_informe_personalizado_fuera_de_alcance(cliente):
    respuesta = cliente.post("/informes/personalizado", json={"spec": fixture_prompt("p10")["spec"]}, headers=CABECERA)
    cuerpo = respuesta.json()
    assert respuesta.status_code == 200 and cuerpo["estado"] == "fuera_de_alcance"
    assert cuerpo["problemas"][0]["codigo"] == "DIMENSION_IDENTIFICA_PERSONAS"
    assert "contrato" not in cuerpo
    descarga = cliente.get(f"/informes/{cuerpo['id_solicitud']}/descargar", headers=CABECERA)
    assert descarga.status_code == 404


def test_peticion_mal_formada(cliente):
    assert cliente.post("/informes/personalizado", json={"spec": {}, "sql": "x"}, headers=CABECERA).status_code == 422
    assert cliente.post("/informes/personalizado", json={"spec": {}}, headers=CABECERA).json()["estado"] != "valida"


def test_informe_de_plantilla_base(cliente):
    respuesta = cliente.post(
        "/informes",
        json={"codigo": "INF-COS-02", "alcance": {"rol": "directivo"}, "formatos": ["csv"]},
        headers=CABECERA,
    )
    cuerpo = respuesta.json()
    assert respuesta.status_code == 200 and cuerpo["estado"] == "valida"
    assert cuerpo["contrato"]["especificacion"]["base"] == "INF-COS-02"
    assert cuerpo["titulo"].startswith("INF-COS-02")


def test_plantilla_inexistente_o_rol_no_permitido(cliente):
    inexistente = cliente.post(
        "/informes", json={"codigo": "INF-XXX-99", "alcance": {"rol": "directivo"}}, headers=CABECERA
    )
    assert inexistente.status_code == 404
    catalogo = cliente.get("/informes/catalogo", headers=CABECERA).json()
    restringida = next(p for p in catalogo if "tutor" not in p["roles_permitidos"])
    prohibida = cliente.post(
        "/informes", json={"codigo": restringida["codigo_informe"], "alcance": {"rol": "tutor", "id_usuario": 3}},
        headers=CABECERA,
    )  # fmt: skip
    assert prohibida.status_code == 403


def test_un_formato_que_el_servidor_no_puede_producir_responde_503(cliente, monkeypatch):
    from ciumb_analitica.exportacion import exportador

    def sin_pdf(_informe):
        raise exportador.FormatoNoDisponible("el PDF no está disponible en este servidor")

    monkeypatch.setattr(exportador, "_pdf", sin_pdf)
    respuesta = cliente.post(
        "/informes/personalizado", json={"spec": fixture_prompt("p02")["spec"], "formatos": ["pdf"]}, headers=CABECERA
    )
    assert respuesta.status_code == 503 and "PDF" in respuesta.json()["detail"]
