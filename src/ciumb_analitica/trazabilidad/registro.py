"""Escritura de la trazabilidad en `rpt_` (Tabla 12; RF-13, RF-19, RNF-11, OE5).

  rpt_especificacion  cada spec recibida, con su huella y el resultado de la validación (válida o no).
  rpt_solicitud       quién pidió qué y cuándo (usuario SEUDONIMIZADO; prompt depurado de PII).
  rpt_resultado       cada archivo generado: formato, huella de los datos, SQL compilado y modo (con IA o no).
  rpt_validacion      cifras del primer texto de la IA, discrepantes, regeneraciones y uso de plantilla (OE5).
  rpt_narrativa_cache texto ya aprobado por el validador de cifras, por huella del contrato (RF-13): la misma
                      spec con los mismos datos produce el mismo contrato y reutiliza el texto sin llamar a la IA.
Nada de lo que se escribe aquí contiene datos personales en claro (invariante 4 y 5).
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime

from sqlalchemy import Connection, insert, select, update

from ciumb_analitica.contrato.modelos import Contrato
from ciumb_analitica.contrato.pii import PATRONES_PII
from ciumb_analitica.spec.resultado import ResultadoValidacion
from ciumb_analitica.trazabilidad import esquema as rpt
from ciumb_analitica.validador_cifras.validador import Narrativa, ResultadoFinal

ESTADO_EN_PROCESO = "en_proceso"
ESTADO_COMPLETADA = "completada"
ESTADO_RECHAZADA = "rechazada"
ESTADO_ERROR = "error"
TEXTO_RETIRADO = "[dato retirado]"


def _canonico(datos) -> str:
    return json.dumps(datos, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def huella_texto(datos) -> str:
    """SHA-256 (64 hex) del JSON canónico de `datos`."""
    return hashlib.sha256(_canonico(datos).encode("utf-8")).hexdigest()


def depurar_texto(texto: str | None) -> str | None:
    """Reemplaza lo que tenga forma de correo, documento o NIT antes de guardar un prompt (Tabla 12)."""
    if texto is None:
        return None
    for patron in PATRONES_PII.values():
        texto = patron.sub(TEXTO_RETIRADO, texto)
    return texto


def registrar_especificacion(
    con: Connection, datos_spec: dict, resultado: ResultadoValidacion, *, id_plantilla: int | None = None
) -> int:
    """Guarda la spec TAL COMO LLEGÓ (para reproducirla validándola otra vez con la misma fecha, RNF-11). Si es
    válida, `huella_spec` es la huella de la spec resuelta (la que se compila); si no, la del JSON recibido."""
    spec_json = _canonico(datos_spec)
    if resultado.spec is not None:
        huella = resultado.spec.huella()
        version = resultado.spec.esquema
        origen = resultado.spec.origen.value
    else:
        huella = huella_texto(datos_spec)
        version = str(datos_spec.get("esquema", "desconocido"))[:20]
        origen = str(datos_spec.get("origen", "desconocido"))[:20]
    motivo = None
    if resultado.problemas:
        motivo = "; ".join(f"{p.codigo}: {p.mensaje}" for p in resultado.problemas)[:500]
    fila = con.execute(
        insert(rpt.rpt_especificacion).values(
            id_plantilla=id_plantilla,
            esquema_version=version,
            origen=origen,
            spec_json=spec_json,
            huella_spec=huella,
            estado_validacion=resultado.estado.value,
            motivo=motivo,
            fecha_registro=datetime.now(),
        )
    )
    return int(fila.inserted_primary_key[0])


def registrar_solicitud(
    con: Connection,
    *,
    id_especificacion: int | None,
    seudonimo_usuario: str,
    prompt: str | None,
    fecha_corte: date | None,
    estado: str = ESTADO_EN_PROCESO,
    fecha: datetime | None = None,
) -> int:
    fila = con.execute(
        insert(rpt.rpt_solicitud).values(
            id_especificacion=id_especificacion,
            id_usuario=seudonimo_usuario,
            prompt_texto=depurar_texto(prompt),
            fecha_corte=fecha_corte,
            estado=estado,
            fecha_solicitud=fecha or datetime.now(),
        )
    )
    return int(fila.inserted_primary_key[0])


def actualizar_solicitud(con: Connection, id_solicitud: int, *, estado: str, fecha_corte: date | None = None) -> None:
    valores: dict = {"estado": estado}
    if fecha_corte is not None:
        valores["fecha_corte"] = fecha_corte
    con.execute(update(rpt.rpt_solicitud).where(rpt.rpt_solicitud.c.id_solicitud == id_solicitud).values(**valores))


def registrar_resultado(
    con: Connection,
    *,
    id_solicitud: int,
    formato: str,
    huella_datos: str,
    sql_compilado: str,
    modo: str,
    ruta_archivo: str | None = None,
) -> int:
    fila = con.execute(
        insert(rpt.rpt_resultado).values(
            id_solicitud=id_solicitud,
            formato=formato,
            huella_datos=huella_datos.removeprefix("sha256:"),
            sql_compilado=sql_compilado,
            ruta_archivo=ruta_archivo,
            modo=modo,
            fecha_generacion=datetime.now(),
        )
    )
    return int(fila.inserted_primary_key[0])


def registrar_validacion(con: Connection, id_resultado: int, final: ResultadoFinal) -> int:
    """Base de OE5. La fila la define `ResultadoFinal.registro()` (cifras del último texto de la IA evaluado,
    regeneraciones y uso de plantilla); sin IA, las cifras van en 0 y `uso_plantilla` en verdadero."""
    fila = con.execute(
        insert(rpt.rpt_validacion).values(id_resultado=id_resultado, fecha=datetime.now(), **final.registro())
    )
    return int(fila.inserted_primary_key[0])


def huella_contrato(contrato: Contrato) -> str:
    """Llave de la caché de narrativa (RF-13): el contrato completo (origen y gráfico de la spec, periodo, alcance,
    cifras, advertencias y huella de datos) SIN `especificacion.id`, que cambia en cada solicitud. Dos solicitudes
    de la misma spec sobre los mismos datos producen la misma llave."""
    volcado = contrato.model_dump(mode="json", exclude_none=True)
    volcado["especificacion"].pop("id", None)
    return huella_texto(volcado)


def narrativa_en_cache(con: Connection, contrato: Contrato) -> Narrativa | None:
    t = rpt.rpt_narrativa_cache
    texto = con.execute(select(t.c.texto_json).where(t.c.huella_entrada == huella_contrato(contrato))).scalar()
    return None if texto is None else Narrativa.model_validate_json(texto)


def guardar_narrativa(con: Connection, contrato: Contrato, narrativa: Narrativa) -> None:
    """Guarda un texto de la IA YA APROBADO por el validador de cifras. La plantilla no se guarda."""
    t = rpt.rpt_narrativa_cache
    clave = huella_contrato(contrato)
    if con.execute(select(t.c.huella_entrada).where(t.c.huella_entrada == clave)).first() is not None:
        return
    con.execute(insert(t).values(huella_entrada=clave, texto_json=narrativa.model_dump_json(), fecha=datetime.now()))


def resultado_guardado(con: Connection, id_solicitud: int, formato: str) -> dict | None:
    t = rpt.rpt_resultado
    fila = (
        con.execute(
            select(t).where(t.c.id_solicitud == id_solicitud, t.c.formato == formato).order_by(t.c.id_resultado.desc())
        )
        .mappings()
        .first()
    )
    return None if fila is None else dict(fila)


def solicitud_con_spec(con: Connection, id_solicitud: int) -> dict | None:
    """Solicitud con la spec recibida, su huella resuelta y su estado (para reproducir el informe, RNF-11)."""
    s, e = rpt.rpt_solicitud, rpt.rpt_especificacion
    fila = (
        con.execute(
            select(s, e.c.spec_json, e.c.huella_spec, e.c.estado_validacion)
            .join(e, e.c.id_especificacion == s.c.id_especificacion)
            .where(s.c.id_solicitud == id_solicitud)
        )
        .mappings()
        .first()
    )
    return None if fila is None else dict(fila)


def id_plantilla(con: Connection, codigo: str | None) -> int | None:
    if not codigo:
        return None
    t = rpt.rpt_plantilla
    return con.execute(select(t.c.id_plantilla).where(t.c.codigo_informe == codigo)).scalar()
