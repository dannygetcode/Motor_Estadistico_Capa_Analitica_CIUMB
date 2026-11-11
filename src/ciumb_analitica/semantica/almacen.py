"""Persistencia de la capa semántica en `rpt_metrica`, `rpt_dimension`, `rpt_compatibilidad` y `rpt_plantilla`.

`sembrar` escribe la semilla (idempotente: borra y vuelve a insertar). `leer_capa` reconstruye la
`CapaSemantica` desde la base; al hacerlo vuelve a validar cada expresión y cada columna contra el esquema
`ana_`, de modo que un registro mal escrito en la base nunca llega al compilador.
"""

from __future__ import annotations

import json

from sqlalchemy import Connection, delete, insert, select

from ciumb_analitica.semantica.modelos import AgregadoAlterno, CapaSemantica, Dimension, Metrica
from ciumb_analitica.semantica.semilla import PLANTILLAS, capa_semilla
from ciumb_analitica.spec.modelos import cargar_especificacion
from ciumb_analitica.trazabilidad.esquema import rpt_compatibilidad, rpt_dimension, rpt_metrica, rpt_plantilla


def _json(valor) -> str:
    return json.dumps(valor, ensure_ascii=False, sort_keys=True)


def sembrar(conexion: Connection, capa: CapaSemantica | None = None, plantillas: tuple[dict, ...] = PLANTILLAS) -> None:
    """Carga la capa semántica y las plantillas base. No hace commit: lo decide quien llama."""
    capa = capa or capa_semilla()
    for t in (rpt_compatibilidad, rpt_plantilla, rpt_metrica, rpt_dimension):
        conexion.execute(delete(t))

    ids_metrica = {c: i for i, c in enumerate(sorted(capa.metricas), start=1)}
    ids_dimension = {c: i for i, c in enumerate(sorted(capa.dimensiones), start=1)}
    conexion.execute(
        insert(rpt_metrica),
        [
            {
                "id_metrica": ids_metrica[m.codigo],
                "codigo": m.codigo,
                "nombre": m.nombre,
                "descripcion": m.descripcion,
                "sinonimos_json": _json(list(m.sinonimos)),
                "hecho_o_agregado": m.hecho_o_agregado,
                "expresion_sql": m.expresion_sql,
                "agregaciones": ",".join(a.value for a in m.agregaciones),
                "agregacion_defecto": m.agregacion_defecto.value,
                "aditividad": m.aditividad.value,
                "unidad": m.unidad,
                "columna_personas": m.columna_personas,
                "agregados_json": _json([a.model_dump() for a in m.agregados]),
                "activa": m.activa,
            }
            for m in capa.metricas.values()
        ],
    )
    conexion.execute(
        insert(rpt_dimension),
        [
            {
                "id_dimension": ids_dimension[d.codigo],
                "codigo": d.codigo,
                "nombre": d.nombre,
                "descripcion": d.descripcion,
                "sinonimos_json": _json(list(d.sinonimos)),
                "tabla_columna": d.tabla_columna,
                "tipo": d.tipo.value,
                "identifica_persona": d.identifica_persona,
                "viaja_a_ia": d.viaja_a_ia,
                "binaria_de_metrica": d.binaria_de_metrica,
            }
            for d in capa.dimensiones.values()
        ],
    )
    conexion.execute(
        insert(rpt_compatibilidad),
        [{"id_metrica": ids_metrica[m], "id_dimension": ids_dimension[d]} for m, d in sorted(capa.compatibilidad)],
    )
    for i, p in enumerate(plantillas, start=1):
        cargar_especificacion(p["spec"])  # una plantilla es una spec válida (DA-09)
        conexion.execute(
            insert(rpt_plantilla),
            {
                "id_plantilla": i,
                "codigo_informe": p["codigo_informe"],
                "nombre": p["nombre"],
                "spec_json": _json(p["spec"]),
                "version": 1,
                "roles_permitidos": ",".join(p["roles_permitidos"]),
                "activa": True,
            },
        )


def leer_capa(conexion: Connection) -> CapaSemantica:
    """Reconstruye la capa semántica desde `rpt_`. Lanza `ValidationError` si un registro no es coherente."""
    metricas, por_id_m = {}, {}
    for f in conexion.execute(select(rpt_metrica)).mappings():
        m = Metrica(
            codigo=f["codigo"],
            nombre=f["nombre"],
            descripcion=f["descripcion"],
            sinonimos=tuple(json.loads(f["sinonimos_json"])),
            hecho_o_agregado=f["hecho_o_agregado"],
            expresion_sql=f["expresion_sql"],
            agregaciones=tuple(f["agregaciones"].split(",")),
            agregacion_defecto=f["agregacion_defecto"],
            aditividad=f["aditividad"],
            unidad=f["unidad"],
            columna_personas=f["columna_personas"],
            agregados=tuple(AgregadoAlterno(**a) for a in json.loads(f["agregados_json"])),
            activa=bool(f["activa"]),
        )
        metricas[m.codigo] = m
        por_id_m[f["id_metrica"]] = m.codigo
    dimensiones, por_id_d = {}, {}
    for f in conexion.execute(select(rpt_dimension)).mappings():
        d = Dimension(
            codigo=f["codigo"],
            nombre=f["nombre"],
            descripcion=f["descripcion"],
            sinonimos=tuple(json.loads(f["sinonimos_json"])),
            tabla_columna=f["tabla_columna"],
            tipo=f["tipo"],
            identifica_persona=bool(f["identifica_persona"]),
            viaja_a_ia=bool(f["viaja_a_ia"]),
            binaria_de_metrica=f["binaria_de_metrica"],
        )
        dimensiones[d.codigo] = d
        por_id_d[f["id_dimension"]] = d.codigo
    compatibilidad = frozenset(
        (por_id_m[f["id_metrica"]], por_id_d[f["id_dimension"]])
        for f in conexion.execute(select(rpt_compatibilidad)).mappings()
    )
    return CapaSemantica(metricas=metricas, dimensiones=dimensiones, compatibilidad=compatibilidad)


def leer_plantillas(conexion: Connection, *, rol: str | None = None) -> list[dict]:
    """Catálogo de plantillas base activas (GET /informes/catalogo), filtrado por rol si se indica."""
    salida = []
    for f in conexion.execute(select(rpt_plantilla).order_by(rpt_plantilla.c.codigo_informe)).mappings():
        roles = f["roles_permitidos"].split(",")
        if f["activa"] and (rol is None or rol in roles):
            salida.append(
                {
                    "codigo_informe": f["codigo_informe"],
                    "nombre": f["nombre"],
                    "version": f["version"],
                    "roles_permitidos": roles,
                    "spec": json.loads(f["spec_json"]),
                }
            )
    return salida
