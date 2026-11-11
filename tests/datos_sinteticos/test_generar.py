import pytest

from datos_sinteticos.generar import (
    CATALOGO_ESTADOS,
    DEFECTOS,
    FECHA_CORTE,
    INICIO,
    contar_defectos,
    generar,
)


@pytest.fixture(scope="module")
def datos():
    return generar()


def test_misma_semilla_mismas_filas(datos):
    otra = generar()
    assert otra.tablas == datos.tablas


def test_semilla_distinta_cambia_filas(datos):
    assert generar(semilla=1).tablas["proyecto_investigacion"] != datos.tablas["proyecto_investigacion"]


def test_conteos_de_defectos_exactos(datos):
    assert contar_defectos(datos) == DEFECTOS


def test_ids_de_defectos_coinciden_con_conteos(datos):
    assert {k: len(v) for k, v in datos.defectos.items()} == DEFECTOS


def test_fechas_dentro_del_periodo(datos):
    for p in datos.tablas["proyecto_investigacion"]:
        assert INICIO <= p["fecha_creacion"] <= FECHA_CORTE
    for p in datos.tablas["practica"]:
        assert INICIO <= p["fecha_inicio"] <= FECHA_CORTE


def test_estados_validos_salvo_defectos(datos):
    invalidos = {
        k: {f["estado"] for f in datos.tablas[k]} - set(CATALOGO_ESTADOS[k])
        for k in ("hito_entregable", "macroproyecto", "empresa", "consultoria", "usuario")
    }
    assert all(not v for v in invalidos.values()), invalidos


def test_integridad_referencial_basica(datos):
    t = datos.tablas
    usuarios = {u["id_usuario"] for u in t["usuario"]}
    empresas = {e["id_empresa"] for e in t["empresa"]}
    convenios = {c["id_convenio"] for c in t["convenio"]}
    for p in t["practica"]:
        assert p["id_estudiante"] in usuarios
        assert p["id_empresa"] is None or p["id_empresa"] in empresas
        assert p["id_convenio"] is None or p["id_convenio"] in convenios
    for c in t["convenio"]:
        assert c["id_convenio_anterior"] is None or c["id_convenio_anterior"] in convenios


def test_volumen_realista(datos):
    c = datos.conteos()
    assert 500 <= c["proyecto_investigacion"] <= 1000
    assert 2000 <= c["practica"] <= 5000
    assert 200 <= c["empresa"] <= 400
