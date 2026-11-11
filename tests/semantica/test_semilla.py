"""Capa semántica: semilla, aditividad, compatibilidad (Tabla 15), publicación y persistencia en rpt_."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError
from sqlalchemy import update

from ciumb_analitica.dw import esquema as dw
from ciumb_analitica.semantica.almacen import leer_capa, leer_plantillas, sembrar
from ciumb_analitica.semantica.expresion import ExpresionInvalida, analizar
from ciumb_analitica.semantica.modelos import Aditividad, Dimension, Metrica, alcanzable
from ciumb_analitica.semantica.semilla import PLANTILLAS, capa_semilla
from ciumb_analitica.spec.modelos import Agregacion, cargar_especificacion
from ciumb_analitica.trazabilidad.esquema import rpt_metrica
from tests.conftest import IDS_PROMPTS, fixture_prompt

CAPA = capa_semilla()


def _codigos_de(spec: dict) -> tuple[set[str], set[str]]:
    metricas = {m["id"] for m in spec["metricas"]}
    dims = {d["id"] for d in spec.get("dimensiones", [])} | {f["campo"] for f in spec.get("filtros", [])}
    variables = set((spec.get("analisis") or {}).get("variables", []))
    return metricas, dims | (variables - metricas)


@pytest.mark.parametrize("nombre", IDS_PROMPTS)
def test_la_semilla_cubre_p1_p10(nombre):
    metricas, dims = _codigos_de(fixture_prompt(nombre)["spec"])
    assert metricas <= set(CAPA.metricas)
    assert dims <= set(CAPA.dimensiones)


@pytest.mark.parametrize("plantilla", PLANTILLAS, ids=lambda p: p["codigo_informe"])
def test_cada_plantilla_base_es_una_spec_valida_y_cubierta(plantilla):
    spec = cargar_especificacion(plantilla["spec"])
    assert spec.base == plantilla["codigo_informe"]
    metricas, dims = _codigos_de(plantilla["spec"])
    assert metricas <= set(CAPA.metricas) and dims <= set(CAPA.dimensiones)
    for m in metricas:
        for d in dims:
            assert CAPA.es_compatible(m, d), f"{m} x {d}"


def test_las_razones_no_son_aditivas_y_solo_admiten_razon():
    razones = [m for m in CAPA.metricas.values() if m.es_razon]
    assert {"pct_ejecucion", "pct_hitos_atrasados"} <= {m.codigo for m in razones}
    for m in razones:
        assert m.aditividad is Aditividad.NO_ADITIVA
        assert m.agregaciones == (Agregacion.RAZON,)
        assert m.expresion.numerador and m.unidad == "%"


def test_ningun_porcentaje_se_declara_sumable():
    for m in CAPA.metricas.values():
        if m.unidad == "%" or m.codigo.startswith("pct_"):
            assert Agregacion.SUMA not in m.agregaciones, m.codigo
            assert m.aditividad is Aditividad.NO_ADITIVA, m.codigo


def test_las_metricas_de_instantaneas_periodicas_no_son_aditivas_en_el_tiempo():
    for m in CAPA.metricas.values():
        if m.tabla.info["tipo"] == dw.INSTANTANEA_PERIODICA:
            assert m.aditividad is not Aditividad.ADITIVA, m.codigo


def test_compatibilidad_sigue_la_matriz_de_bus():
    # Tabla 15: hecho_convenio no tiene línea ni programa; hecho_hito solo tiempo y estado.
    assert not CAPA.es_compatible("convenios", "linea_investigacion")
    assert not CAPA.es_compatible("convenios", "facultad")
    assert CAPA.es_compatible("convenios", "tipo_convenio") and CAPA.es_compatible("convenios", "empresa")
    assert set(CAPA.dimensiones_compatibles("hitos")) == {"tiempo", "periodo_academico", "anio", "estado"}
    assert CAPA.es_compatible("proyectos", "facultad") and CAPA.es_compatible("proyectos", "estado")
    assert not CAPA.es_compatible("proyectos", "empresa")
    assert CAPA.es_compatible("facturacion", "tiempo") and CAPA.es_compatible("facturacion", "empresa")
    assert not CAPA.es_compatible("facturacion", "estado")
    for m, d in CAPA.compatibilidad:
        assert alcanzable(CAPA.metricas[m], CAPA.dimensiones[d])


def test_todas_las_metricas_tienen_tiempo():
    for m in CAPA.metricas:
        assert CAPA.es_compatible(m, "tiempo"), m


def test_practicas_sin_linea_de_investigacion_d13():
    assert not CAPA.es_compatible("practicas", "linea_investigacion")
    assert CAPA.es_compatible("practicas", "programa") and CAPA.es_compatible("practicas", "facultad")


def test_estado_hito_solo_con_su_metrica_d19():
    assert CAPA.es_compatible("pct_hitos_atrasados", "estado_hito")
    assert [m for m, d in CAPA.compatibilidad if d == "estado_hito"] == ["pct_hitos_atrasados"]


def test_dimensiones_que_identifican_personas():
    personas = {d.codigo for d in CAPA.dimensiones.values() if d.identifica_persona}
    assert personas == {"persona", "estudiante"}
    assert "estudiante" not in CAPA.dimensiones_compatibles("practicas")
    assert "estudiante" in CAPA.dimensiones_compatibles("practicas", sin_personas=False)
    assert all(not CAPA.dimensiones[c].viaja_a_ia for c in personas | {"empresa", "macroproyecto"})


def test_metricas_que_cuentan_personas():
    assert CAPA.metricas["practicas"].columna_personas == "seudonimo_estudiante"
    assert CAPA.metricas["accesos"].columna_personas == "sk_persona"
    assert CAPA.metricas["proyectos"].columna_personas is None


def test_la_publicacion_no_revela_el_esquema_fisico():
    publicado = CAPA.publicar()
    texto = json.dumps(publicado, ensure_ascii=False)
    for tabla in dw.metadatos_ana.tables.values():
        assert tabla.name not in texto, tabla.name
    for prohibido in ("expresion_sql", "hecho_o_agregado", "tabla_columna", "ana_", "sk_", "seudonimo"):
        assert prohibido not in texto, prohibido
    facturacion = next(m for m in publicado["metricas"] if m["codigo"] == "facturacion")
    assert "plata facturada" in facturacion["sinonimos"]
    practicas = next(m for m in publicado["metricas"] if m["codigo"] == "practicas")
    assert "estudiante" not in practicas["dimensiones_compatibles"]
    assert len(publicado["metodos"]) == 13 and len(publicado["graficos"]) == 6


@pytest.mark.parametrize(
    ("texto", "tipo"),
    [
        ("*", "conteo"),
        ("valor_facturado", "columna"),
        ("100 * a / b", "razon"),
        ("a/b", "razon"),
        ("100*a / *", "razon"),
    ],
)
def test_gramatica_de_expresiones(texto, tipo):
    assert analizar(texto).tipo == tipo


@pytest.mark.parametrize(
    "texto",
    ["SUM(valor)", "a; DROP TABLE x", "a / b / c", "50 * a / b", "a + b", "ana_.hecho.a", "(select 1)", "a -- x", ""],
)
def test_gramatica_rechaza_sql_libre(texto):
    with pytest.raises(ExpresionInvalida):
        analizar(texto)


def _metrica(**cambios) -> dict:
    return CAPA.metricas["pct_ejecucion"].model_dump() | cambios


@pytest.mark.parametrize(
    "cambios",
    [
        {"hecho_o_agregado": "usuario"},
        {"expresion_sql": "100 * contrasena_hash / presupuesto_asignado"},
        {"agregaciones": ("suma",), "agregacion_defecto": "suma"},
        {"aditividad": "aditiva"},
        {"columna_personas": "correo"},
        {"expresion_sql": "1; DROP TABLE ana_.hecho_proyecto"},
    ],
    ids=lambda c: next(iter(c)),
)
def test_una_metrica_incoherente_no_entra_a_la_capa(cambios):
    with pytest.raises((ValidationError, ExpresionInvalida)):
        Metrica(**_metrica(**cambios))


def test_una_dimension_fuera_de_la_lista_blanca_no_entra():
    base = CAPA.dimensiones["facultad"].model_dump()
    with pytest.raises(ValidationError):
        Dimension(**(base | {"tabla_columna": "usuario.correo"}))
    with pytest.raises(ValidationError):
        Dimension(**(base | {"tabla_columna": "dim_linea_programa.no_existe"}))
    with pytest.raises(ValidationError):
        Dimension(**(base | {"identifica_persona": True}))


def test_sembrar_y_leer_devuelve_la_misma_capa(motor_bd):
    with motor_bd.begin() as con:
        sembrar(con)
        sembrar(con)  # idempotente
        leida = leer_capa(con)
        plantillas = leer_plantillas(con)
        de_coordinador = leer_plantillas(con, rol="coordinador")
    assert leida == CAPA
    assert [p["codigo_informe"] for p in plantillas] == sorted(p["codigo_informe"] for p in PLANTILLAS)
    assert "INF-EMP-03" not in [p["codigo_informe"] for p in de_coordinador]


def test_un_registro_malicioso_en_rpt_metrica_no_llega_al_compilador(motor_bd):
    with motor_bd.begin() as con:
        sembrar(con)
        con.execute(
            update(rpt_metrica)
            .where(rpt_metrica.c.codigo == "facturacion")
            .values(expresion_sql="valor_facturado); DROP TABLE x; --")
        )
        with pytest.raises((ValidationError, ExpresionInvalida)):
            leer_capa(con)
