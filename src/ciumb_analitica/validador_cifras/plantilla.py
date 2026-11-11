"""Plantilla sin IA: texto determinista construido solo con el contrato (RF-11, DA-05, invariante 10).

Es el respaldo del paso 6 del validador de cifras y el texto del modo degradado. Es deliberadamente rígida:
una frase por indicador, con sus cifras en formato español. `exportacion/` puede reemplazarla por plantillas
Jinja2 por informe, siempre que el resultado pase `validar_narrativa`.
"""

from __future__ import annotations

from ciumb_analitica.contrato.modelos import UNIDAD_PROPORCION, Contrato, Indicador, Seccion
from ciumb_analitica.validador_cifras.extraccion import formatear_numero
from ciumb_analitica.validador_cifras.validador import Narrativa, SeccionNarrativa


def _etiqueta(codigo: str) -> str:
    return codigo.replace("_", " ").strip().capitalize()


def _con_unidad(valor, unidad: str | None) -> str:
    if unidad == UNIDAD_PROPORCION:
        return f"{formatear_numero(valor * 100)} %"
    texto = formatear_numero(valor)
    if not unidad:
        return texto
    return f"{texto} %" if unidad == "%" else f"{texto} {unidad}"


def _frase(indicador: Indicador) -> str:
    sujeto = _etiqueta(indicador.id)
    if indicador.grupo:
        sujeto += " (" + ", ".join(f"{_etiqueta(k)}: {v}" for k, v in sorted(indicador.grupo.items())) + ")"
    if indicador.mes:
        sujeto += f" en {indicador.mes}"
    partes = [f"{sujeto}: {_con_unidad(indicador.valor, indicador.unidad)}"]
    if indicador.ic_inferior is not None and indicador.ic_superior is not None:
        partes.append(
            f"intervalo de confianza entre {formatear_numero(indicador.ic_inferior)} y "
            f"{formatear_numero(indicador.ic_superior)}"
        )
    if indicador.anterior is not None:
        partes.append(f"periodo de comparación: {_con_unidad(indicador.anterior, indicador.unidad)}")
    if indicador.variacion_pct is not None:
        partes.append(f"variación: {formatear_numero(indicador.variacion_pct)} %")
    if indicador.meta is not None:
        partes.append(f"meta: {_con_unidad(indicador.meta, indicador.unidad)}")
    if indicador.valor_p is not None:
        partes.append(f"valor p: {formatear_numero(indicador.valor_p, 3)}")
    if indicador.n is not None:
        partes.append(f"tamaño de la muestra: {formatear_numero(indicador.n)}")
    if indicador.metodo:
        partes.append(f"método: {indicador.metodo}")
    return "; ".join(partes) + "."


def _texto_de_seccion(seccion: Seccion) -> str:
    lineas = [_frase(i) for i in seccion.indicadores]
    lineas.append(f"Método: {seccion.metodo}.")
    lineas += [f"Advertencia: {a}" for a in seccion.advertencias]
    return "\n".join(lineas)


def plantilla_por_defecto(contrato: Contrato) -> Narrativa:
    """Texto de plantilla para cualquier contrato. Entrada: contrato válido. Salida: `Narrativa` con una
    sección por cada sección del contrato. No agrega ninguna cifra que no esté en el contrato."""
    return Narrativa(secciones=tuple(SeccionNarrativa(id=s.id, texto=_texto_de_seccion(s)) for s in contrato.secciones))
