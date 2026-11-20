"""Demostración: pide los informes P1–P10 al servicio que está corriendo y guarda los archivos.

Uso (con el servicio arriba en http://localhost:8000):
    uv run --env-file .env python herramientas/demo.py            # los diez prompts
    uv run --env-file .env python herramientas/demo.py p03 p04    # solo algunos

Guarda en `informes_demo/` el HTML y el PDF de cada informe válido y abre el primero en el navegador.
"""

from __future__ import annotations

import json
import os
import sys
import webbrowser
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = RAIZ / "informes_demo"
URL = os.environ.get("URL_SERVICIO", "http://localhost:8000")


def main(nombres: list[str]) -> None:
    token = os.environ.get("SERVICIO_TOKEN")
    if not token:
        sys.exit("Falta SERVICIO_TOKEN: ejecute con `uv run --env-file .env ...`")
    cliente = httpx.Client(base_url=URL, headers={"Authorization": f"Bearer {token}"}, timeout=180)
    SALIDA.mkdir(exist_ok=True)
    abiertos = False
    for nombre in nombres or [f"p{i:02d}" for i in range(1, 11)]:
        fixture = json.loads((RAIZ / "schemas" / "fixtures" / f"{nombre}.json").read_text(encoding="utf-8"))
        print(f"\n{nombre.upper()} · {fixture['prompt']}")
        respuesta = cliente.post(
            "/informes/personalizado",
            json={"spec": fixture["spec"], "prompt": fixture["prompt"], "formatos": ["html", "pdf"]},
        )
        if respuesta.status_code != 200:
            print(f"  error {respuesta.status_code}: {respuesta.text[:200]}")
            continue
        cuerpo = respuesta.json()
        print(f"  estado: {cuerpo['estado']}")
        if cuerpo["estado"] != "valida":
            for p in cuerpo["problemas"]:
                print(f"  - {p['codigo']}: {p['mensaje']}")
            continue
        grafico = cuerpo["contrato"]["especificacion"]["grafico"]["tipo"]
        avisos = ", ".join(a["codigo"] for a in cuerpo["avisos"]) or "ninguno"
        print(f"  {cuerpo['titulo']} | gráfico: {grafico} | modo: {cuerpo['modo']} | avisos: {avisos}")
        for formato in ("html", "pdf"):
            archivo = cliente.get(f"/informes/{cuerpo['id_solicitud']}/descargar", params={"formato": formato})
            if archivo.status_code != 200:
                print(f"  {formato}: no disponible ({archivo.status_code})")
                continue
            ruta = SALIDA / f"{nombre}.{formato}"
            ruta.write_bytes(archivo.content)
            print(f"  {formato}: {ruta}")
            if formato == "html" and not abiertos:
                webbrowser.open(ruta.as_uri())
                abiertos = True


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:])
