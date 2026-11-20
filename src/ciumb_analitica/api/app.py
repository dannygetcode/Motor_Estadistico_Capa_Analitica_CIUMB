"""Aplicación FastAPI del servicio de informes (Figuras 9 y 11; D-16, D-28).

Rutas:
  GET  /salud                       vida del servicio (sin token).
  GET  /semantica                   capa semántica publicada para la capa de IA (sin datos ni tablas).
  GET  /informes/catalogo           plantillas base activas, filtradas por rol.
  POST /informes/personalizado      spec `ciumb.spec/1.0` (de la capa de IA) -> informe (RF-12).
  POST /informes                    plantilla base del catálogo + alcance -> informe.
  GET  /informes/{id}/descargar     archivo de una solicitud en el formato pedido (RF-16, RNF-11).
Todas menos /salud exigen `Authorization: Bearer <SERVICIO_TOKEN>` (4.4.3).
"""

from __future__ import annotations

import copy
import hmac
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from ciumb_analitica import __version__
from ciumb_analitica.api.flujo import Informe, SpecNoReproducible, procesar, reproducir
from ciumb_analitica.api.servicio import Servicio, ServicioNoConfigurado, servicio_del_entorno
from ciumb_analitica.exportacion.exportador import TIPOS_MIME, FormatoNoDisponible
from ciumb_analitica.spec.modelos import Formato
from ciumb_analitica.trazabilidad import registro

app = FastAPI(title="Servicio de informes CIUMB — área analítica", version=__version__)


@app.exception_handler(FormatoNoDisponible)
def _formato_no_disponible(_request: Request, exc: FormatoNoDisponible) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


_bearer = HTTPBearer(auto_error=False)


@app.get("/salud")
def salud() -> dict[str, str]:
    """Indica que el servicio está arriba. No consulta la BD ni proveedores de IA."""
    return {"estado": "ok", "version": __version__}


def obtener_servicio(request: Request) -> Servicio:
    servicio = getattr(request.app.state, "servicio", None)
    if servicio is None:
        try:
            servicio = servicio_del_entorno()
        except ServicioNoConfigurado as e:
            raise HTTPException(status_code=503, detail=f"servicio sin configurar: {e}") from e
        except Exception as e:  # noqa: BLE001 - p. ej. falta la sal; no se exponen detalles de conexión
            raise HTTPException(
                status_code=503, detail="servicio sin configurar; revise las variables de entorno"
            ) from e
        request.app.state.servicio = servicio
    return servicio


def autorizado(
    servicio: Annotated[Servicio, Depends(obtener_servicio)],
    credenciales: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Servicio:
    if not servicio.token:
        raise HTTPException(status_code=503, detail="defina SERVICIO_TOKEN para atender solicitudes")
    if credenciales is None or not hmac.compare_digest(credenciales.credentials.encode(), servicio.token.encode()):
        raise HTTPException(
            status_code=401, detail="token de servicio inválido", headers={"WWW-Authenticate": "Bearer"}
        )
    return servicio


ServicioAutorizado = Annotated[Servicio, Depends(autorizado)]


class PeticionPersonalizada(BaseModel):
    """Lo que envía la capa de IA (o el backend) para un informe a la medida."""

    model_config = ConfigDict(extra="forbid")

    spec: dict = Field(description="Especificación ciumb.spec/1.0 tal como la propone la capa de IA.")
    prompt: str | None = Field(default=None, max_length=4000, description="Se guarda depurado de PII.")
    formatos: list[Formato] = Field(default=[Formato.HTML], min_length=1, max_length=5)
    id_usuario: int | None = Field(default=None, ge=1, description="Id de origen; se guarda seudonimizado.")


class PeticionPlantilla(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: str = Field(pattern=r"^INF-[A-Z]{3}-[0-9]{2}$")
    alcance: dict = Field(description="Lo agrega el backend del CIUMB (RF-21).")
    periodo: dict | None = Field(default=None, description="{desde, hasta, corte?}; si se omite, el de la plantilla.")
    formatos: list[Formato] = Field(default=[Formato.HTML], min_length=1, max_length=5)
    id_usuario: int | None = Field(default=None, ge=1)


def _respuesta(informe: Informe, request: Request) -> dict:
    cuerpo: dict = {
        "estado": informe.estado,
        "id_solicitud": informe.id_solicitud,
        "problemas": [p.model_dump() for p in informe.problemas],
        "avisos": [a.model_dump() for a in informe.avisos],
    }
    if informe.ensamblado is not None:
        final = informe.validacion
        cuerpo |= {
            "titulo": informe.ensamblado.titulo,
            "modo": informe.ensamblado.modo,
            "contrato": informe.contrato.model_dump(mode="json", exclude_none=True),
            "narrativa": final.narrativa.model_dump(),
            "validacion": final.registro() | {"motivo_plantilla": final.motivo_plantilla},
            "huella_spec": informe.huella_spec,
            "descargas": {
                f: str(request.url_for("descargar", id_solicitud=informe.id_solicitud)) + f"?formato={f}"
                for f in informe.archivos
            },
        }
    return cuerpo


def _nombres_plantillas(servicio: Servicio) -> dict[str, str]:
    return {p["codigo_informe"]: p["nombre"] for p in servicio.plantillas()}


@app.get("/semantica")
def semantica(servicio: ServicioAutorizado) -> dict:
    """Capa semántica publicada: códigos, nombres, descripciones y sinónimos; sin datos ni nombres de tablas."""
    return servicio.capa().publicar()


@app.get("/informes/catalogo")
def catalogo(servicio: ServicioAutorizado, rol: str | None = None) -> list[dict]:
    return servicio.plantillas(rol)


@app.post("/informes/personalizado")
def informe_personalizado(peticion: PeticionPersonalizada, request: Request, servicio: ServicioAutorizado) -> dict:
    """Pasos 5 a 19 de la Figura 11. Si la spec no es válida responde 200 con `estado` y `problemas` para que la
    capa de IA repregunte; si es válida, con el contrato, el texto aprobado y los enlaces de descarga."""
    nombres = _nombres_plantillas(servicio)
    with servicio.contexto() as ctx:
        informe = procesar(
            ctx, peticion.spec, hoy=servicio.hoy(), formatos=peticion.formatos, prompt=peticion.prompt,
            id_usuario=peticion.id_usuario, plantillas_nombres=nombres,
        )  # fmt: skip
    return _respuesta(informe, request)


@app.post("/informes")
def informe_de_plantilla(peticion: PeticionPlantilla, request: Request, servicio: ServicioAutorizado) -> dict:
    """Informe de una plantilla base del catálogo con el alcance del usuario (y, si se indica, otro periodo)."""
    plantilla = next((p for p in servicio.plantillas() if p["codigo_informe"] == peticion.codigo), None)
    if plantilla is None:
        raise HTTPException(status_code=404, detail=f"no existe la plantilla activa {peticion.codigo}")
    rol = peticion.alcance.get("rol")
    if rol not in plantilla["roles_permitidos"]:
        raise HTTPException(status_code=403, detail=f"el rol {rol} no puede usar {peticion.codigo}")
    spec = copy.deepcopy(plantilla["spec"]) | {"alcance": peticion.alcance}
    if peticion.periodo is not None:
        spec["periodo"] = peticion.periodo
    nombres = _nombres_plantillas(servicio)
    with servicio.contexto() as ctx:
        informe = procesar(
            ctx, spec, hoy=servicio.hoy(), formatos=peticion.formatos, id_usuario=peticion.id_usuario,
            plantillas_nombres=nombres,
        )  # fmt: skip
    return _respuesta(informe, request)


@app.get("/informes/{id_solicitud}/descargar", name="descargar")
def descargar(id_solicitud: int, servicio: ServicioAutorizado, formato: Annotated[Formato, Query()] = Formato.PDF):
    """Devuelve el archivo guardado; si no se guardó (o se pide otro formato), lo reproduce con la spec resuelta y
    la fecha de la solicitud (RNF-11) y el texto aprobado de la caché (RF-13)."""
    with servicio.motor_rpt.connect() as con:
        guardado = registro.resultado_guardado(con, id_solicitud, formato.value)
    if guardado and guardado["ruta_archivo"] and Path(guardado["ruta_archivo"]).is_file():
        contenido = Path(guardado["ruta_archivo"]).read_bytes()
        nombre = Path(guardado["ruta_archivo"]).name.split("_", 1)[-1]
    else:
        try:
            with servicio.contexto() as ctx:
                informe = reproducir(ctx, id_solicitud, formato, plantillas_nombres=_nombres_plantillas(servicio))
        except SpecNoReproducible as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        if informe is None:
            raise HTTPException(status_code=404, detail="la solicitud no existe o no produjo un informe")
        if informe.ensamblado is None:
            raise HTTPException(status_code=409, detail="los datos ya no permiten reproducir el informe")
        contenido, nombre = informe.archivos[formato.value], informe.nombres[formato.value]
    return Response(
        content=contenido,
        media_type=TIPOS_MIME[formato],
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
