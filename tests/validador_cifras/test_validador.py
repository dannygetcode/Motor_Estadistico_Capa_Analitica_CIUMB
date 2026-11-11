"""Validador de cifras: seis pasos de la sección 4.4.3 con casos adversos."""

from __future__ import annotations

import hashlib
import random
from decimal import Decimal

import pytest

from ciumb_analitica.contrato.modelos import cargar_contrato
from ciumb_analitica.validador_cifras.extraccion import extraer_cifras, formatear_numero
from ciumb_analitica.validador_cifras.plantilla import plantilla_por_defecto
from ciumb_analitica.validador_cifras.validador import (
    MAX_REGENERACIONES,
    Narrativa,
    PlantillaInvalida,
    validar_con_regeneracion,
    validar_narrativa,
    valores_admitidos,
)
from tests.conftest import DIR_FIXTURES, leer_json

CONTRATO = cargar_contrato(leer_json(DIR_FIXTURES / "contrato_p03.json"))  # Figura 12
SECCION = "facturacion_consultorias"

TEXTO_CORRECTO = (
    "Entre enero y octubre de 2026 la facturación de consultorías fue de 412,6 millones COP, frente a 365,0 "
    "millones en el mismo periodo de 2025, lo que representa un aumento del 13,0 %. El mes de mayor facturación "
    "fue junio de 2026, con 58,3 millones. El análisis incluye 118 consultorías."
)


def _contrato(indicadores: list[dict], *, metodo="conteo", advertencias=()) -> object:
    return cargar_contrato(
        {
            "contrato": "ciumb.informe/2.0.0",
            "especificacion": {"id": "esp-20261105-0001", "origen": "prompt", "base": None, "grafico": None},
            "periodo": {"desde": "2026-01-01", "hasta": "2026-10-31", "corte": "2026-10-31"},
            "alcance": {"rol": "directivo"},
            "secciones": [
                {"id": "s", "indicadores": indicadores, "metodo": metodo, "advertencias": list(advertencias)}
            ],
            "huella_datos": "sha256:" + hashlib.sha256(b"x").hexdigest(),
        }
    )


def _validar(texto: str, contrato=CONTRATO, **kw):
    seccion = contrato.secciones[0].id
    return validar_narrativa({seccion: texto}, contrato, **kw)


def _valores(texto: str) -> list[tuple[str, int, bool]]:
    return [(str(c.valor), c.decimales, c.es_porcentaje) for c in extraer_cifras(texto) if c.descartada is None]


# --- Paso 1: extracción en formato español ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("fueron 412,6 millones", [("412.6", 1, False)]),
        ("un total de 1.250 proyectos", [("1250", 0, False)]),
        ("sumó 1.250.000,75 pesos", [("1250000.75", 2, False)]),
        ("creció 13 %", [("13", 0, True)]),
        ("creció 13% y luego 4,5 %", [("13", 0, True), ("4.5", 1, True)]),
        ("creció 13 % (espacio duro)", [("13", 0, True)]),
        ("un 13,0 por ciento", [("13.0", 1, True)]),
        ("bajó -3,2 puntos", [("-3.2", 1, False)]),
        ("bajó −3,2 % (signo tipográfico)", [("-3.2", 1, True)]),
        ("formato inglés 58.3", [("58.3", 1, False)]),
        ("valor p de 0,003", [("0.003", 3, False)]),
        ("entre 5 y 10 días", [("5", 0, False), ("10", 0, False)]),
        ("rango 5-10", [("5", 0, False), ("10", 0, False)]),
        ("(118).", [("118", 0, False)]),
        ("12, 15 y 18.", [("12", 0, False), ("15", 0, False), ("18", 0, False)]),
        ("sin cifras", []),
    ],
)
def test_paso1_extrae_numeros_en_formato_espanol(texto, esperado):
    assert _valores(texto) == esperado


def test_paso1_un_numero_con_cuatro_decimales_no_se_parte():
    assert _valores("coeficiente 1.2345") == [("1.2345", 4, False)]
    assert _valores("total 12.345.678") == [("12345678", 0, False)]


# --- Paso 2: fechas, años y códigos no son cifras ----------------------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        "en 2026",
        "entre 2025 y 2026",
        "2025-2026",
        "corte al 2026-10-31",
        "el 31/10/2026",
        "el 31 de octubre de 2026",
        "el 1 de enero",
        "en junio de 2026",
        "el mes 2026-06",
        "periodo académico 2026-2",
        "informe INF-INV-02",
        "especificación esp-20261105-0042",
        "trimestres T1 a T3",
        "prompts P4 y P10",
        "el 1.º y el 2.ª lugar",
    ],
)
def test_paso2_descarta_fechas_anios_y_codigos(texto):
    assert _valores(texto) == []
    assert all(c.descartada for c in extraer_cifras(texto))


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("2.026 proyectos", "2026"),  # con punto de miles no es un año
        ("2026 %", "2026"),
        ("2026,0 unidades", "2026.0"),
        ("-2026", "-2026"),
        ("12026 registros", "12026"),
        ("026 casos", "26"),
    ],
)
def test_paso2_lo_que_parece_anio_pero_es_cifra(texto, esperado):
    assert [v for v, _, _ in _valores(texto)] == [esperado]


def test_paso2_no_oculta_cifras_junto_a_fechas():
    cifras = _valores("Al 31 de octubre de 2026 había 37 proyectos y en 2025 hubo 29 (INF-INV-01).")
    assert cifras == [("37", 0, False), ("29", 0, False)]


# --- Paso 3: valores admitidos -------------------------------------------------------------------------------


def test_paso3_admite_todos_los_campos_numericos_del_contrato():
    valores = {(a.origen.split(".")[-1], a.valor) for a in valores_admitidos(CONTRATO)}
    assert {
        ("valor", Decimal("412.6")),
        ("anterior", Decimal("365.0")),
        ("variacion_pct", Decimal("13.0")),
        ("n", Decimal("118")),
        ("valor", Decimal("58.3")),
    } <= valores


def test_paso3_parametros_del_analisis():
    contrato = _contrato([{"id": "rho", "valor": 0.41, "valor_p": 0.0312, "n": 86}])
    texto = "Con un nivel de confianza del 95 % y alfa de 0,05, la correlación es 0,41 (p = 0,031; n = 86)."
    assert not _validar(texto, contrato).aprobado
    assert _validar(texto, contrato, extra=(0.95, 0.05)).aprobado


def test_paso3_los_numeros_de_las_advertencias_se_pueden_repetir():
    contrato = _contrato(
        [{"id": "pct_ejecucion", "valor": 61.4, "unidad": "%", "n": 9}],
        advertencias=["El histograma se construye con 9 observaciones (menos de 20): interprételo con cautela."],
    )
    assert _validar("La ejecución media es 61,4 % con 9 proyectos, menos de las 20 observaciones.", contrato).aprobado
    assert not _validar("La ejecución media es 61,4 % con 9 proyectos, menos de 30.", contrato).aprobado


# --- Paso 4: tolerancia de media unidad del último decimal -----------------------------------------------------


def test_texto_correcto_de_la_figura_12():
    resultado = _validar(TEXTO_CORRECTO)
    assert resultado.aprobado and resultado.cifras_texto == 5 and resultado.descartadas == 3


@pytest.mark.parametrize(
    "cifra",
    ["412,6", "413", "412,60", "412,600", "412.6"],
)
def test_redondeo_valido(cifra):
    assert _validar(f"La facturación fue de {cifra} millones.").aprobado


@pytest.mark.parametrize(
    "cifra",
    ["412,9", "412", "414", "412,7", "412,5", "412,61", "4.126", "41,26", "412.600.000", "-412,6"],
)
def test_redondeo_invalido_o_cifra_alterada(cifra):
    resultado = _validar(f"La facturación fue de {cifra} millones.")
    assert not resultado.aprobado and resultado.discrepancias[0].texto == cifra


def test_media_unidad_exacta_se_acepta_en_ambos_sentidos():
    contrato = _contrato([{"id": "x", "valor": 0.125}, {"id": "y", "valor": 2.5}])
    for cifra in ("0,13", "0,12", "0,125", "0,1"):
        assert _validar(f"valor {cifra}", contrato).aprobado, cifra
    assert _validar("valores 2 y 3", contrato).aprobado
    assert not _validar("valor 0,14", contrato).aprobado
    assert not _validar("valor 0,2", contrato).aprobado


def test_cifra_inventada():
    resultado = _validar(TEXTO_CORRECTO + " Se proyecta un crecimiento del 20 % para 2027, con 47 clientes nuevos.")
    assert not resultado.aprobado
    assert [d.texto for d in resultado.discrepancias] == ["20 %", "47"]
    assert resultado.discrepancias[0].seccion == SECCION and "crecimiento" in resultado.discrepancias[0].contexto
    assert resultado.cifras_texto == 7


def test_cifra_calculada_por_la_ia_aunque_sea_correcta_es_discrepancia():
    # 412,6 - 365,0 = 47,6: la resta es correcta, pero no viene en el contrato.
    assert not _validar("La facturación aumentó 47,6 millones, hasta 412,6 millones.").aprobado


def test_porcentaje_frente_a_proporcion():
    proporcion = _contrato([{"id": "tasa", "valor": 0.137, "unidad": "proporcion"}])
    for texto in ("13,7 %", "14 %", "13,70 por ciento", "0,137", "0,14"):
        assert _validar(f"La tasa es {texto}.", proporcion).aprobado, texto
    for texto in ("13,7", "14", "0,137 %", "1,37 %", "137 %", "13,9 %"):
        assert not _validar(f"La tasa es {texto}.", proporcion).aprobado, texto

    porcentaje = _contrato([{"id": "pct_ejecucion", "valor": 13.7, "unidad": "%"}])
    for texto in ("13,7 %", "14 %", "13,7"):
        assert _validar(f"La ejecución es {texto}.", porcentaje).aprobado, texto
    for texto in ("0,137", "0,14", "1.370 %", "0,137 %"):
        assert not _validar(f"La ejecución es {texto}.", porcentaje).aprobado, texto


def test_un_porcentaje_no_valida_un_conteo():
    contrato = _contrato([{"id": "proyectos", "valor": 13, "n": 13}])
    assert _validar("Hay 13 proyectos.", contrato).aprobado
    assert not _validar("Hay 13 % de proyectos.", contrato).aprobado


def test_variacion_negativa_se_puede_escribir_sin_signo_pero_no_al_reves():
    contrato = _contrato([{"id": "facturacion", "valor": 300.0, "anterior": 316.5, "variacion_pct": -5.2}])
    assert _validar("La facturación cayó 5,2 % hasta 300.", contrato).aprobado
    assert _validar("La variación fue de -5,2 %.", contrato).aprobado
    assert not _validar("La facturación fue de -300.", contrato).aprobado
    assert not _validar("La variación fue de 5,3 %.", contrato).aprobado


def test_valor_p_e_intervalo_de_confianza():
    contrato = _contrato(
        [{"id": "pronostico", "valor": 131.4, "ic_inferior": 112.08, "ic_superior": 150.72, "valor_p": 0.0312}]
    )
    assert _validar("Se esperan 131 prácticas (entre 112 y 151); p = 0,03.", contrato).aprobado
    assert _validar("Se esperan 131,4 prácticas (IC 112,1 a 150,7); p = 3,1 %.", contrato).aprobado
    assert not _validar("Se esperan 131 prácticas (entre 110 y 151).", contrato).aprobado


def test_miles_con_punto():
    contrato = _contrato([{"id": "presupuesto", "valor": 1250000.5, "unidad": "COP"}, {"id": "n", "valor": 1250}])
    assert _validar("El presupuesto es 1.250.000,5 COP (1.250.001 redondeado) en 1.250 proyectos.", contrato).aprobado
    assert not _validar("El presupuesto es 1.250 millones y medio: 1,25.", contrato).aprobado


def test_formas_de_entregar_la_narrativa():
    como_modelo = Narrativa(secciones=({"id": SECCION, "texto": TEXTO_CORRECTO},))
    como_dict = {"secciones": [{"id": SECCION, "texto": TEXTO_CORRECTO}]}
    for narrativa in (como_modelo, como_dict, {SECCION: TEXTO_CORRECTO}):
        assert validar_narrativa(narrativa, CONTRATO).aprobado


def test_un_texto_sin_cifras_se_aprueba():
    resultado = _validar("La facturación aumentó frente al año anterior.")
    assert resultado.aprobado and resultado.cifras_texto == 0


# --- Pasos 5 y 6: regeneración y plantilla -------------------------------------------------------------------

MALO = "La facturación fue de 500 millones."


class _IA:
    """Capa de IA simulada: devuelve las respuestas en orden y registra lo que se le pide."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.pedidos = []

    def __call__(self, anterior, discrepancias):
        self.pedidos.append((anterior, discrepancias))
        respuesta = self.respuestas.pop(0)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta if respuesta is None else {SECCION: respuesta}


def _final(primero, ia, **kw):
    narrativa = None if primero is None else {SECCION: primero}
    return validar_con_regeneracion(narrativa, CONTRATO, regenerar=ia, plantilla=plantilla_por_defecto, **kw)


def test_paso5_texto_correcto_se_aprueba_sin_regenerar():
    ia = _IA()
    final = _final(TEXTO_CORRECTO, ia)
    assert (final.uso_plantilla, final.regeneraciones, ia.pedidos) == (False, 0, [])
    assert final.registro() == {
        "cifras_texto": 5, "cifras_discrepantes": 0, "regeneraciones": 0, "uso_plantilla": False,
    }  # fmt: skip


def test_paso5_la_regeneracion_recibe_las_cifras_que_fallaron():
    ia = _IA(TEXTO_CORRECTO)
    final = _final(MALO, ia)
    assert (final.uso_plantilla, final.regeneraciones) == (False, 1)
    anterior, discrepancias = ia.pedidos[0]
    assert anterior.secciones[0].texto == MALO
    assert [(d.seccion, d.texto, d.valor) for d in discrepancias] == [(SECCION, "500", 500.0)]
    assert final.narrativa.secciones[0].texto == TEXTO_CORRECTO
    assert [i.aprobado for i in final.intentos] == [False, True]


def test_paso5_se_aprueba_en_la_segunda_regeneracion():
    ia = _IA(MALO, TEXTO_CORRECTO)
    final = _final(MALO, ia)
    assert (final.uso_plantilla, final.regeneraciones, len(ia.pedidos)) == (False, 2, 2)


def test_paso6_maximo_dos_regeneraciones_y_luego_plantilla():
    ia = _IA(MALO, MALO, TEXTO_CORRECTO)  # la tercera respuesta nunca se pide
    final = _final(MALO, ia)
    assert MAX_REGENERACIONES == 2
    assert (final.uso_plantilla, final.regeneraciones, len(ia.pedidos)) == (True, 2, 2)
    assert final.motivo_plantilla == "discrepancias" and len(final.intentos) == 3
    assert final.registro() == {
        "cifras_texto": 1, "cifras_discrepantes": 1, "regeneraciones": 2, "uso_plantilla": True,
    }  # fmt: skip
    assert final.narrativa == plantilla_por_defecto(CONTRATO)
    assert "500" not in final.narrativa.secciones[0].texto


@pytest.mark.parametrize("fallo", [None, RuntimeError("sin cuota"), TimeoutError()])
def test_paso6_si_la_ia_no_responde_al_regenerar_se_usa_la_plantilla(fallo):
    final = _final(MALO, _IA(fallo))
    assert (final.uso_plantilla, final.regeneraciones, final.motivo_plantilla) == (True, 1, "sin_respuesta")


def test_modo_degradado_sin_ia_siempre_produce_texto():
    final = validar_con_regeneracion(None, CONTRATO, regenerar=None, plantilla=plantilla_por_defecto)
    assert (final.uso_plantilla, final.regeneraciones, final.intentos) == (True, 0, ())
    assert final.motivo_plantilla == "sin_respuesta"
    assert final.registro() == {
        "cifras_texto": 0, "cifras_discrepantes": 0, "regeneraciones": 0, "uso_plantilla": True,
    }  # fmt: skip
    assert "412,6" in final.narrativa.secciones[0].texto


def test_sin_funcion_de_regeneracion_un_texto_malo_va_directo_a_plantilla():
    final = validar_con_regeneracion({SECCION: MALO}, CONTRATO, regenerar=None, plantilla=plantilla_por_defecto)
    assert (final.uso_plantilla, final.regeneraciones, final.motivo_plantilla) == (True, 0, "discrepancias")


def test_una_respuesta_con_forma_invalida_no_rompe_el_flujo():
    final = validar_con_regeneracion(
        {"secciones": "no es una lista"}, CONTRATO, regenerar=None, plantilla=plantilla_por_defecto
    )
    assert final.uso_plantilla and final.motivo_plantilla == "sin_respuesta"


def test_una_plantilla_con_cifras_ajenas_al_contrato_es_un_defecto():
    with pytest.raises(PlantillaInvalida, match="999"):
        validar_con_regeneracion(None, CONTRATO, regenerar=None, plantilla=lambda c: {SECCION: "Total: 999."})


# --- Plantilla sin IA ----------------------------------------------------------------------------------------


def test_la_plantilla_de_la_figura_12_cita_solo_cifras_del_contrato():
    texto = plantilla_por_defecto(CONTRATO).secciones[0].texto
    for esperado in ("412,6 millones COP", "365 millones COP", "variación: 13 %", "118", "en 2026-06: 58,3"):
        assert esperado in texto
    assert validar_narrativa(plantilla_por_defecto(CONTRATO), CONTRATO).aprobado


def test_la_plantilla_siempre_pasa_el_validador_con_contratos_aleatorios():
    rng = random.Random(20261111)
    unidades = [None, "%", "proporcion", "COP", "dias", "millones COP"]
    for _ in range(300):
        indicadores = []
        for i in range(rng.randint(1, 6)):
            unidad = rng.choice(unidades)
            escala = rng.choice([1, 10, 1000, 1_000_000, 1e9])
            valor = rng.random() if unidad == "proporcion" else rng.uniform(-1, 1) * escala
            indicador = {"id": f"ind_{i}", "valor": rng.choice([valor, round(valor, 2), int(valor)])}
            if unidad:
                indicador["unidad"] = unidad
            if rng.random() < 0.5:
                indicador["anterior"] = rng.random() if unidad == "proporcion" else rng.uniform(0, escala)
                indicador["variacion_pct"] = rng.uniform(-80, 300)
            if rng.random() < 0.5:
                indicador["n"] = rng.randint(0, 5000)
            if rng.random() < 0.3:
                indicador["valor_p"] = rng.random() ** 4
            if rng.random() < 0.3:
                indicador["ic_inferior"], indicador["ic_superior"] = valor - rng.random(), valor + rng.random()
            if rng.random() < 0.3:
                indicador["grupo"] = {"facultad": "Ingeniería", "periodo_academico": "2026-2"}
            if rng.random() < 0.2:
                indicador["mes"] = f"2026-{rng.randint(1, 12):02d}"
            indicadores.append(indicador)
        contrato = _contrato(indicadores, advertencias=["Se omiten 2 grupo(s) con menos de 5 personas."])
        resultado = validar_narrativa(plantilla_por_defecto(contrato), contrato)
        assert resultado.aprobado, (indicadores, resultado.discrepancias)


@pytest.mark.parametrize(
    ("valor", "decimales", "esperado"),
    [
        (412.6, None, "412,6"),
        (365.0, None, "365"),
        (1250000.5, None, "1.250.000,5"),
        (1250, None, "1.250"),
        (0.125, 3, "0,125"),
        (13.456, None, "13,46"),
        (-5.2, None, "-5,2"),
        (2026, None, "2.026"),
    ],
)
def test_formato_espanol(valor, decimales, esperado):
    assert formatear_numero(valor, decimales) == esperado
    assert extraer_cifras(esperado)[0].descartada is None
