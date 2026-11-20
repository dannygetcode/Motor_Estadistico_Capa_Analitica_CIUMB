"""Orquestación (Figura 11; RF-11, RF-12, RF-13, RF-19, RNF-11): de la spec al informe exportado y trazado.

Los diez prompts de la Tabla 22 se corren de punta a punta sobre el datawarehouse cargado por el ETL desde la
fuente sintética. La capa de IA se simula con redactores falsos: este repositorio nunca llama a un LLM.
"""

from __future__ import annotations

import copy
import re

import pytest
from sqlalchemy import select

from ciumb_analitica.api import flujo
from ciumb_analitica.contrato.modelos import Contrato
from ciumb_analitica.contrato.pii import buscar_pii
from ciumb_analitica.exportacion.exportador import MODO_CON_IA, MODO_DEGRADADO
from ciumb_analitica.spec.modelos import Formato
from ciumb_analitica.trazabilidad import esquema as rpt
from ciumb_analitica.trazabilidad import registro
from ciumb_analitica.validador_cifras.plantilla import plantilla_por_defecto
from ciumb_analitica.validador_cifras.validador import Narrativa, SeccionNarrativa
from tests.api.conftest import HOY, SAL
from tests.conftest import IDS_PROMPTS, fixture_prompt

HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _procesar(entorno, spec: dict, *, redactor=None, formatos=(Formato.HTML,), **kw):
    with entorno.ana.connect() as lectura, entorno.rpt.begin() as con_rpt:
        ctx = flujo.Contexto(capa=entorno.capa, lectura=lectura, rpt=con_rpt, sal=SAL, redactor=redactor)
        return flujo.procesar(ctx, spec, hoy=HOY, formatos=formatos, **kw)


def _fila(entorno, tabla, **filtros) -> list[dict]:
    with entorno.rpt.connect() as con:
        consulta = select(tabla).where(*(tabla.c[k] == v for k, v in filtros.items()))
        return [dict(f) for f in con.execute(consulta).mappings()]


@pytest.mark.parametrize("nombre", IDS_PROMPTS)
def test_los_diez_prompts_de_la_tabla_22_de_punta_a_punta(entorno, nombre):
    fixture = fixture_prompt(nombre)
    esperado = fixture["esperado"]
    informe = _procesar(entorno, fixture["spec"], prompt=fixture["prompt"], formatos=(Formato.HTML, Formato.XLSX))
    assert informe.estado == esperado["resultado"]
    solicitud = _fila(entorno, rpt.rpt_solicitud, id_solicitud=informe.id_solicitud)[0]
    if esperado["resultado"] != "valida":
        assert informe.problemas[0].codigo == esperado["motivo"]
        assert solicitud["estado"] == registro.ESTADO_RECHAZADA
        return
    ensamblado = informe.ensamblado
    assert ensamblado.graficos[0].tipo == esperado["grafico_final"]
    assert set(esperado["avisos"]) <= {a.codigo for a in informe.avisos}
    assert ensamblado.modo == MODO_DEGRADADO and informe.validacion.uso_plantilla  # sin redactor: RF-11
    assert buscar_pii(informe.contrato.model_dump(mode="json")) == []
    assert informe.archivos["html"].lstrip().lower().startswith(b"<!doctype html")
    assert informe.archivos["xlsx"].startswith(b"PK")
    assert (
        solicitud["estado"] == registro.ESTADO_COMPLETADA
        and solicitud["fecha_corte"] == ensamblado.contrato.periodo.corte
    )
    resultados = _fila(entorno, rpt.rpt_resultado, id_solicitud=informe.id_solicitud)
    assert sorted(r["formato"] for r in resultados) == ["html", "xlsx"]
    assert all(HEX64.match(r["huella_datos"]) and r["sql_compilado"].startswith("-- principal") for r in resultados)
    validaciones = [v for r in resultados for v in _fila(entorno, rpt.rpt_validacion, id_resultado=r["id_resultado"])]
    assert len(validaciones) == 1 and validaciones[0]["uso_plantilla"] is True


def test_p8_no_publica_empresas_ni_centroides_de_grupos_diminutos(entorno):
    informe = _procesar(entorno, fixture_prompt("p08")["spec"])
    seccion = informe.contrato.secciones[0]
    grupos = [i.grupo for i in seccion.indicadores if i.grupo]
    assert all(set(g) == {"segmento"} for g in grupos)  # nunca la dimensión empresa
    tamanos = {i.grupo["segmento"]: i.valor for i in seccion.indicadores if i.id == "tamano"}
    con_centroide = {i.grupo["segmento"] for i in seccion.indicadores if i.id.endswith("_centroide")}
    assert con_centroide == {g for g, n in tamanos.items() if n >= 5}


class RedactorFiel:
    """Simula una IA que redacta sin inventar cifras (repite el texto de plantilla)."""

    def __init__(self):
        self.llamadas = 0

    def redactar(self, contrato: Contrato):
        self.llamadas += 1
        return plantilla_por_defecto(contrato)

    def regenerar(self, contrato, anterior, discrepancias):
        self.llamadas += 1
        return plantilla_por_defecto(contrato)


class RedactorInventor(RedactorFiel):
    """Inventa una cifra en los primeros `errores` textos."""

    def __init__(self, errores: int):
        super().__init__()
        self.errores = errores

    def _texto(self, contrato):
        self.llamadas += 1
        base = plantilla_por_defecto(contrato)
        if self.llamadas > self.errores:
            return base
        primera = base.secciones[0]
        inventada = SeccionNarrativa(id=primera.id, texto=primera.texto + "\nEl total creció 987,6 %.")
        return Narrativa(secciones=(inventada, *base.secciones[1:]))

    def redactar(self, contrato):
        return self._texto(contrato)

    def regenerar(self, contrato, anterior, discrepancias):
        assert [d.texto for d in discrepancias] == ["987,6 %"]
        return self._texto(contrato)


class RedactorCaido(RedactorFiel):
    def redactar(self, contrato):
        raise ConnectionError("proveedor sin cuota")


def _spec_unica(nombre: str, facultad: str) -> dict:
    """Spec de P2 con otra facultad: contrato propio, para no compartir la caché entre pruebas."""
    spec = copy.deepcopy(fixture_prompt(nombre)["spec"])
    spec["alcance"]["facultad"] = facultad
    return spec


def test_con_ia_el_texto_aprobado_se_guarda_y_la_misma_solicitud_usa_la_cache(entorno):
    spec = _spec_unica("p02", "Educación")
    redactor = RedactorFiel()
    primero = _procesar(entorno, spec, redactor=redactor)
    assert primero.ensamblado.modo == MODO_CON_IA and primero.validacion.regeneraciones == 0
    assert redactor.llamadas == 1
    segundo = _procesar(entorno, spec, redactor=redactor)
    assert redactor.llamadas == 1  # RF-13: mismo contrato (salvo el id) -> texto de la caché, sin llamar a la IA
    assert segundo.ensamblado.modo == MODO_CON_IA
    assert segundo.contrato.especificacion.id != primero.contrato.especificacion.id


def test_una_cifra_inventada_pide_regeneracion(entorno):
    redactor = RedactorInventor(errores=1)
    informe = _procesar(entorno, _spec_unica("p02", "Ciencias de la Salud"), redactor=redactor)
    assert informe.validacion.regeneraciones == 1 and not informe.validacion.uso_plantilla
    assert informe.ensamblado.modo == MODO_CON_IA
    fila = _fila(entorno, rpt.rpt_resultado, id_solicitud=informe.id_solicitud)[0]
    validacion = _fila(entorno, rpt.rpt_validacion, id_resultado=fila["id_resultado"])[0]
    assert (validacion["regeneraciones"], validacion["uso_plantilla"]) == (1, False)


def test_si_la_ia_insiste_en_inventar_sale_la_plantilla(entorno):
    redactor = RedactorInventor(errores=99)
    informe = _procesar(entorno, _spec_unica("p02", "Ciencias Sociales y Humanas"), redactor=redactor)
    assert informe.validacion.regeneraciones == 2 and informe.validacion.uso_plantilla
    assert informe.validacion.motivo_plantilla == "discrepancias"
    assert informe.ensamblado.modo == MODO_DEGRADADO
    assert "987,6" not in informe.archivos["html"].decode("utf-8")


def test_si_la_ia_no_responde_el_informe_sale_igual(entorno):
    informe = _procesar(entorno, _spec_unica("p02", "Ciencias Económicas y Administrativas"), redactor=RedactorCaido())
    assert informe.estado == "valida" and informe.ensamblado.modo == MODO_DEGRADADO


def test_misma_spec_mismo_sql_misma_huella(entorno):
    spec = fixture_prompt("p03")["spec"]
    a, b = _procesar(entorno, spec), _procesar(entorno, spec)
    assert (a.huella_spec, a.huella_sql, a.contrato.huella_datos) == (
        b.huella_spec,
        b.huella_sql,
        b.contrato.huella_datos,
    )
    assert registro.huella_contrato(a.contrato) == registro.huella_contrato(b.contrato)


def test_reproducir_una_solicitud_guardada(entorno):
    original = _procesar(entorno, fixture_prompt("p01")["spec"])
    with entorno.ana.connect() as lectura, entorno.rpt.begin() as con_rpt:
        ctx = flujo.Contexto(capa=entorno.capa, lectura=lectura, rpt=con_rpt, sal=SAL)
        copia = flujo.reproducir(ctx, original.id_solicitud, Formato.CSV)
        assert flujo.reproducir(ctx, 999_999, Formato.CSV) is None
    assert copia.contrato.huella_datos == original.contrato.huella_datos
    assert copia.contrato.secciones == original.contrato.secciones
    assert copia.archivos["csv"].startswith(b"\xef\xbb\xbf")


def test_un_metodo_que_los_datos_no_admiten_se_repregunta(entorno):
    spec = {
        "esquema": "ciumb.spec/1.0", "origen": "prompt",
        "metricas": [{"id": "satisfaccion"}],
        "analisis": {"metodo": "t_student", "variables": ["satisfaccion", "sector"]},
        "alcance": {"rol": "directivo"},
    }  # fmt: skip
    informe = _procesar(entorno, spec)
    assert informe.estado == "corregible" and informe.problemas[0].codigo == "METODO_NO_APLICABLE"
    assert "dos" in informe.problemas[0].mensaje
    assert (
        _fila(entorno, rpt.rpt_solicitud, id_solicitud=informe.id_solicitud)[0]["estado"] == registro.ESTADO_RECHAZADA
    )


def test_la_trazabilidad_no_guarda_datos_personales(entorno):
    spec = copy.deepcopy(fixture_prompt("p05")["spec"])
    informe = _procesar(entorno, spec, prompt="Soy ana.perez@umb.edu.co, cédula 1023456789", id_usuario=412)
    solicitud = _fila(entorno, rpt.rpt_solicitud, id_solicitud=informe.id_solicitud)[0]
    assert "ana.perez" not in solicitud["prompt_texto"] and "1023456789" not in solicitud["prompt_texto"]
    assert registro.TEXTO_RETIRADO in solicitud["prompt_texto"]
    assert HEX64.match(solicitud["id_usuario"]) and solicitud["id_usuario"] != "412"


def _spec_tutor(id_usuario: int) -> dict:
    return {
        "esquema": "ciumb.spec/1.0", "origen": "prompt",
        "metricas": [{"id": "practicas", "agregacion": "conteo"}],
        "periodo": {"desde": "2019-01-01", "hasta": "2026-10-31"},
        "alcance": {"rol": "tutor", "id_usuario": id_usuario},
    }  # fmt: skip


def test_el_tutor_solo_ve_lo_suyo(entorno):
    from collections import Counter

    from datos_sinteticos.generar import generar

    practicas = generar().tablas["practica"]
    tutor, esperadas = Counter(p["id_tutor_academico"] for p in practicas if p["id_tutor_academico"]).most_common(1)[0]
    propio = _procesar(entorno, _spec_tutor(tutor))
    assert propio.estado == "valida"
    assert propio.contrato.secciones[0].indicadores[0].valor == esperadas
    assert "id_usuario" not in propio.contrato.model_dump(mode="json")["alcance"]
    ajeno = _procesar(entorno, _spec_tutor(999_999))  # un tutor sin prácticas: nada, nunca lo de otro tutor
    assert ajeno.contrato.secciones[0].indicadores[0].valor == 0
