"""Validador de cifras: algoritmo de seis pasos de la sección 4.4.3 (DA-05, OE5).

INTERFAZ CERRADA. Ninguna cifra sin verificar llega al usuario (invariante 1).

 1. Extraer las expresiones numéricas del texto (formato español).            -> `extraccion.extraer_cifras`
 2. Descartar fechas, años y códigos de informe.                               -> `extraccion.extraer_cifras`
 3. Construir el conjunto de valores admitidos a partir del contrato.          -> `valores_admitidos`
 4. Comparar cada número con tolerancia de media unidad del último decimal.    -> `validar_narrativa`
 5. Si alguna cifra no coincide, pedir regeneración indicando cuáles (máx. 2). -> `validar_con_regeneracion`
 6. Si persiste, reemplazar por la plantilla sin IA y registrar el caso.       -> `validar_con_regeneracion`

Este módulo no llama a ningún LLM: la regeneración es una función que inyecta quien orquesta (la capa de IA).

Qué se admite (paso 3):
- Cada campo numérico de cada indicador (`valor`, `anterior`, `variacion_pct`, `n`, `meta`, `valor_p`,
  `ic_inferior`, `ic_superior`), tal como se calculó o redondeado: la tolerancia del paso 4 cubre el redondeo
  a cualquier número de decimales mostrados.
- Un valor con `unidad: "proporcion"` (y `valor_p`) también como porcentaje: 0,137 -> «13,7 %». Solo con el
  signo `%` o «por ciento».
- Un número con `%` solo coincide con `variacion_pct`, con valores cuya unidad es un porcentaje o con una
  proporción multiplicada por cien. «13 %» no valida un conteo de 13.
- Un valor negativo se puede escribir sin signo («cayó 5,2 %»); un valor positivo no se puede escribir con
  signo negativo.
- Los números que aparecen en los textos del propio contrato (`advertencias`, `metodo`, etiquetas de `grupo`, ids)
  y los parámetros del análisis que pase quien llama (`extra`: alfa, nivel de confianza, k…).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from ciumb_analitica.contrato.modelos import UNIDAD_PROPORCION, Contrato
from ciumb_analitica.spec.modelos import PATRON_CODIGO
from ciumb_analitica.validador_cifras.extraccion import CifraTexto, extraer_cifras

MAX_REGENERACIONES = 2
_EPSILON = Decimal("1e-9")
_CAMPOS_NUMERICOS = ("valor", "anterior", "variacion_pct", "n", "meta", "valor_p", "ic_inferior", "ic_superior")
_CAMPOS_CON_UNIDAD = ("valor", "anterior", "meta", "ic_inferior", "ic_superior")


class SeccionNarrativa(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=PATRON_CODIGO)
    texto: str = Field(max_length=20_000)


class Narrativa(BaseModel):
    """Texto que devuelve la capa de IA: una entrada por sección del contrato. BORRADOR (lo define la capa de IA)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    secciones: tuple[SeccionNarrativa, ...]


@dataclass(frozen=True)
class Admitido:
    """Un valor que el texto puede citar. `origen` dice de dónde sale (para depurar y auditar)."""

    valor: Decimal
    origen: str
    como_porcentaje: bool = False  # se puede escribir con `%` tal cual (variación, unidad en %)
    es_proporcion: bool = False  # multiplicado por cien se puede escribir con `%`


@dataclass(frozen=True)
class Discrepancia:
    """Cifra del texto que no está en el contrato. Es lo que se le devuelve a la capa de IA para regenerar."""

    seccion: str
    texto: str
    valor: float
    contexto: str


@dataclass(frozen=True)
class ResultadoCifras:
    aprobado: bool
    cifras_texto: int  # cifras del análisis encontradas (sin las descartadas en el paso 2)
    discrepancias: tuple[Discrepancia, ...]
    descartadas: int


@dataclass(frozen=True)
class ResultadoFinal:
    """Resultado de los pasos 5 y 6.

    narrativa: texto aprobado (el de la IA o la plantilla). uso_plantilla: True si se reemplazó.
    regeneraciones: cuántas se pidieron (0 a 2). intentos: resultado de cada texto de la IA, en orden.
    motivo_plantilla: 'discrepancias' | 'sin_respuesta' | None.
    """

    narrativa: Narrativa
    uso_plantilla: bool
    regeneraciones: int
    intentos: tuple[ResultadoCifras, ...]
    motivo_plantilla: str | None = None

    def registro(self) -> dict:
        """Fila para `rpt_validacion` (base de OE5): cifras del último texto de la IA evaluado."""
        ultimo = self.intentos[-1] if self.intentos else None
        return {
            "cifras_texto": ultimo.cifras_texto if ultimo else 0,
            "cifras_discrepantes": len(ultimo.discrepancias) if ultimo else 0,
            "regeneraciones": self.regeneraciones,
            "uso_plantilla": self.uso_plantilla,
        }


class PlantillaInvalida(Exception):  # noqa: N818 - nombre de dominio en español
    """La plantilla sin IA no pasa el validador: es un defecto del servicio, no de la IA."""


# --- Paso 3 --------------------------------------------------------------------------------------------------


def _decimal(valor) -> Decimal:
    return Decimal(str(valor))


def _unidad_es_porcentaje(unidad: str | None) -> bool:
    return bool(unidad) and ("%" in unidad or "porcent" in unidad.lower() or "por ciento" in unidad.lower())


def valores_admitidos(contrato: Contrato, extra: Iterable[float] = ()) -> list[Admitido]:
    """Paso 3: conjunto de valores que el texto puede citar.

    `extra`: parámetros del análisis que no viajan como indicadores (alfa, nivel de confianza, k, horizonte).
    Un `extra` entre 0 y 1 también se admite como porcentaje (0,95 -> «95 %»).
    """
    admitidos: list[Admitido] = []
    for seccion in contrato.secciones:
        for indicador in seccion.indicadores:
            pct = _unidad_es_porcentaje(indicador.unidad)
            proporcion = indicador.unidad == UNIDAD_PROPORCION
            for campo in _CAMPOS_NUMERICOS:
                valor = getattr(indicador, campo)
                if valor is None:
                    continue
                con_unidad = campo in _CAMPOS_CON_UNIDAD
                admitidos.append(
                    Admitido(
                        valor=_decimal(valor),
                        origen=f"{seccion.id}.{indicador.id}.{campo}",
                        como_porcentaje=campo == "variacion_pct" or (con_unidad and pct),
                        es_proporcion=campo == "valor_p" or (con_unidad and proporcion),
                    )
                )
            textos = [indicador.metodo, indicador.id.replace("_", " "), *(indicador.grupo or {}).values()]
            admitidos += _de_textos(textos, f"{seccion.id}.{indicador.id}")
        textos = [seccion.metodo, seccion.id.replace("_", " "), *seccion.advertencias]
        admitidos += _de_textos(textos, f"{seccion.id}.texto")
    for valor in extra:
        d = _decimal(valor)
        admitidos.append(Admitido(valor=d, origen="parametro", como_porcentaje=True, es_proporcion=0 < d < 1))
    return admitidos


def _de_textos(textos: Iterable[str | None], origen: str) -> list[Admitido]:
    """Los números que el propio contrato trae escritos (advertencias, método, etiquetas) se pueden repetir."""
    return [
        Admitido(valor=c.valor, origen=origen, como_porcentaje=c.es_porcentaje)
        for texto in textos
        if texto
        for c in extraer_cifras(texto)
        if c.descartada is None
    ]


# --- Paso 4 --------------------------------------------------------------------------------------------------


def _cerca(cifra: CifraTexto, valor: Decimal) -> bool:
    tolerancia = cifra.tolerancia + _EPSILON
    if abs(cifra.valor - valor) <= tolerancia:
        return True
    # Un valor negativo se puede escribir sin signo («disminuyó 5,2 %»).
    return valor < 0 and not cifra.con_signo and abs(cifra.valor - abs(valor)) <= tolerancia


def coincide(cifra: CifraTexto, admitidos: Iterable[Admitido]) -> bool:
    """¿La cifra del texto corresponde a algún valor admitido, con media unidad del último decimal mostrado?"""
    for a in admitidos:
        if cifra.es_porcentaje:
            if a.como_porcentaje and _cerca(cifra, a.valor):
                return True
            if a.es_proporcion and _cerca(cifra, a.valor * 100):
                return True
        elif _cerca(cifra, a.valor):
            return True
    return False


def _contexto(texto: str, cifra: CifraTexto, margen: int = 30) -> str:
    return texto[max(0, cifra.inicio - margen) : cifra.fin + margen].strip()


def _como_narrativa(narrativa: Narrativa | dict) -> Narrativa:
    if isinstance(narrativa, Narrativa):
        return narrativa
    if "secciones" in narrativa:
        return Narrativa.model_validate(narrativa)
    return Narrativa(secciones=tuple(SeccionNarrativa(id=k, texto=v) for k, v in narrativa.items()))


def validar_narrativa(
    narrativa: Narrativa | dict, contrato: Contrato, *, extra: Iterable[float] = ()
) -> ResultadoCifras:
    """Pasos 1 a 4 sobre un texto.

    Entradas: `narrativa` (modelo, `{"secciones": [...]}` o `{id_seccion: texto}`), el `contrato` con el que
    se generó y los parámetros `extra` del análisis.
    Salida: `ResultadoCifras`; `aprobado` solo si todas las cifras del texto están en el contrato.
    """
    narrativa = _como_narrativa(narrativa)
    admitidos = valores_admitidos(contrato, extra)
    discrepancias: list[Discrepancia] = []
    total = descartadas = 0
    for seccion in narrativa.secciones:
        for cifra in extraer_cifras(seccion.texto):
            if cifra.descartada is not None:
                descartadas += 1
                continue
            total += 1
            if not coincide(cifra, admitidos):
                discrepancias.append(
                    Discrepancia(
                        seccion=seccion.id,
                        texto=cifra.texto,
                        valor=float(cifra.valor),
                        contexto=_contexto(seccion.texto, cifra),
                    )
                )
    return ResultadoCifras(
        aprobado=not discrepancias, cifras_texto=total, discrepancias=tuple(discrepancias), descartadas=descartadas
    )


# --- Pasos 5 y 6 ---------------------------------------------------------------------------------------------

Regenerar = Callable[[Narrativa, tuple[Discrepancia, ...]], "Narrativa | dict | None"]
Plantilla = Callable[[Contrato], "Narrativa | dict"]


def validar_con_regeneracion(
    narrativa: Narrativa | dict | None,
    contrato: Contrato,
    *,
    regenerar: Regenerar | None,
    plantilla: Plantilla,
    extra: Iterable[float] = (),
    max_regeneraciones: int = MAX_REGENERACIONES,
) -> ResultadoFinal:
    """Pasos 5 y 6: aprueba el texto, pide hasta dos regeneraciones o cae a la plantilla sin IA.

    Entradas:
      narrativa: primer texto de la IA; `None` si no hubo respuesta (modo degradado, RF-11).
      regenerar(narrativa_anterior, discrepancias): lo inyecta la capa de IA. Devuelve el texto nuevo, o
        `None` / lanza una excepción si no hay proveedor. `None` como función = no hay IA.
      plantilla(contrato): texto de plantilla sin IA. Siempre debe pasar el validador.
    Salida: `ResultadoFinal`; `registro()` es la fila de `rpt_validacion`.
    Lanza `PlantillaInvalida` si la plantilla cita una cifra que no está en el contrato.
    """
    extra = tuple(extra)
    intentos: list[ResultadoCifras] = []
    regeneraciones = 0
    motivo = "sin_respuesta"
    actual = narrativa

    while actual is not None:
        try:
            actual = _como_narrativa(actual)
        except (ValueError, TypeError, AttributeError):
            motivo = "sin_respuesta"  # respuesta que no tiene la forma acordada
            break
        resultado = validar_narrativa(actual, contrato, extra=extra)
        intentos.append(resultado)
        if resultado.aprobado:
            return ResultadoFinal(
                narrativa=actual, uso_plantilla=False, regeneraciones=regeneraciones, intentos=tuple(intentos)
            )
        motivo = "discrepancias"
        if regenerar is None or regeneraciones >= max_regeneraciones:
            break
        regeneraciones += 1
        try:
            actual = regenerar(actual, resultado.discrepancias)
        except Exception:  # noqa: BLE001 - cualquier fallo de la capa de IA lleva al modo degradado
            actual = None
        if actual is None:
            motivo = "sin_respuesta"

    de_plantilla = _como_narrativa(plantilla(contrato))
    revision = validar_narrativa(de_plantilla, contrato, extra=extra)
    if not revision.aprobado:
        raise PlantillaInvalida(
            "La plantilla cita cifras que no están en el contrato: "
            + ", ".join(d.texto for d in revision.discrepancias)
        )
    return ResultadoFinal(
        narrativa=de_plantilla,
        uso_plantilla=True,
        regeneraciones=regeneraciones,
        intentos=tuple(intentos),
        motivo_plantilla=motivo,
    )
