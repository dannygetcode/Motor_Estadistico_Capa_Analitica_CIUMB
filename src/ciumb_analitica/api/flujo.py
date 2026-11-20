"""Orquestación de una solicitud (Figura 11, pasos 5 a 19; RF-11, RF-12, RF-13, RF-19, RNF-11).

    validar -> compilar -> ejecutar -> revisar_datos -> motor / ML -> generar_grafico -> empaquetar
      -> [capa de IA: redactar] -> validar_con_regeneracion -> exportar -> rpt_

La capa de IA entra como un `Redactor` inyectado. Este repositorio nunca llama a un LLM (invariante 0): si no hay
redactor, o si falla, el informe sale igual con el texto de plantilla (modo degradado, RF-11, invariante 10).
El cliente HTTP hacia la capa de IA se escribe cuando se cierre su interfaz (docs/interfaz_capa_ia.md, D-28).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Protocol

import pandas as pd
from sqlalchemy import Connection

from ciumb_analitica.compilador.compilador import (
    CONSULTA_PRINCIPAL,
    CONSULTA_PRUEBA,
    LIMITE_FILAS_DEFECTO,
    ErrorCompilacion,
    LimiteFilasExcedido,
    compilar,
    ejecutar,
    huella_datos,
)
from ciumb_analitica.contrato.empaquetador import empaquetar, id_especificacion
from ciumb_analitica.contrato.modelos import Contrato
from ciumb_analitica.dw.tiempo import fin_de_mes
from ciumb_analitica.exportacion.exportador import (
    MODO_CON_IA,
    MODO_DEGRADADO,
    InformeEnsamblado,
    exportar,
    nombre_archivo,
)
from ciumb_analitica.graficos.generador import Grafico, generar_grafico
from ciumb_analitica.ml.segmentacion import unir_por_dimension
from ciumb_analitica.motor.analisis import AnalisisNoAplicable, Calculo, calcular, tabla_para_exportar
from ciumb_analitica.motor.resultado import SeccionCalculada
from ciumb_analitica.semantica.modelos import CapaSemantica
from ciumb_analitica.seudonimo import seudonimizar
from ciumb_analitica.spec import resultado as r
from ciumb_analitica.spec.modelos import Formato, Operador
from ciumb_analitica.spec.resultado import Aviso, Estado, Problema, ResultadoValidacion, SpecResuelta
from ciumb_analitica.spec.validador import RevisionDatos, revisar_datos, validar
from ciumb_analitica.trazabilidad import registro
from ciumb_analitica.validador_cifras.plantilla import plantilla_por_defecto
from ciumb_analitica.validador_cifras.validador import Discrepancia, Narrativa, ResultadoFinal, validar_con_regeneracion

log = logging.getLogger(__name__)

FUENTE_GRAFICOS = "Fuente: datawarehouse del CIUMB (esquema ana_)."


class SpecNoReproducible(RuntimeError):  # noqa: N818 - nombre de dominio en español
    """La spec guardada ya no se resuelve igual (cambió la capa semántica): no se entrega un informe distinto."""


class Redactor(Protocol):
    """Puerto hacia la capa de IA (pasos 12 y 13 de la Figura 11). Devuelve `None` o lanza si no hay proveedor."""

    def redactar(self, contrato: Contrato) -> Narrativa | dict | None: ...

    def regenerar(
        self, contrato: Contrato, anterior: Narrativa, discrepancias: tuple[Discrepancia, ...]
    ) -> Narrativa | dict | None: ...


@dataclass(frozen=True)
class Contexto:
    """Dependencias de una solicitud. `lectura`: conexión de SOLO LECTURA a `ana_` (invariante 3);
    `rpt`: conexión de escritura a `rpt_` (trazabilidad); `sal`: secreto de seudonimización."""

    capa: CapaSemantica
    lectura: Connection
    rpt: Connection
    sal: str
    redactor: Redactor | None = None
    plantillas: Collection[str] | None = None
    limite_filas: int = LIMITE_FILAS_DEFECTO
    directorio: Path | None = None


@dataclass
class Informe:
    """Respuesta de la orquestación.

    estado: 'valida' | 'corregible' | 'fuera_de_alcance' (4.4.2). Con 'valida' trae el informe ensamblado, el
    contrato, los archivos exportados y la validación de cifras; si no, los problemas para repreguntar.
    """

    estado: str
    id_solicitud: int | None = None
    problemas: tuple[Problema, ...] = ()
    avisos: tuple[Aviso, ...] = ()
    ensamblado: InformeEnsamblado | None = None
    contrato: Contrato | None = None
    validacion: ResultadoFinal | None = None
    archivos: dict[str, bytes] = field(default_factory=dict)
    nombres: dict[str, str] = field(default_factory=dict)
    huella_spec: str | None = None
    huella_sql: str | None = None
    sql: str | None = None


# --- Pasos -----------------------------------------------------------------------------------------------------------


def _revisar(spec: SpecResuelta, resultados: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, RevisionDatos]:
    """`revisar_datos` sobre cada consulta principal; con varias (P8) se unen por la dimensión común (D-22)."""
    principales = {k: v for k, v in resultados.items() if k.startswith(CONSULTA_PRINCIPAL)}
    if len(principales) == 1:
        revision = revisar_datos(spec, next(iter(principales.values())))
        return revision.datos, revision
    revisiones = {k: revisar_datos(spec, v) for k, v in principales.items()}
    dimension = next((d.id for d in spec.dimensiones), None)
    if dimension is None:
        raise AnalisisNoAplicable("varias consultas principales sin una dimensión común para unirlas")
    unido = unir_por_dimension({k: v.datos for k, v in revisiones.items()}, dimension, [m.id for m in spec.metricas])
    final = revisar_datos(spec, unido)
    avisos: dict[tuple[str, str], Aviso] = {}
    for rev in (*revisiones.values(), final):
        for a in rev.avisos:
            avisos.setdefault((a.codigo, a.mensaje), a)
    suprimidos = sum(rev.grupos_suprimidos for rev in revisiones.values())
    revision = RevisionDatos(
        datos=final.datos,
        grafico=final.grafico,
        avisos=tuple(avisos.values()),
        publicar_pronostico=final.publicar_pronostico,
        grupos_suprimidos=suprimidos,
    )
    return final.datos, revision


def _rango_periodo(spec: SpecResuelta, datos: pd.DataFrame) -> tuple[date, date]:
    """Periodo del contrato cuando lo da un filtro temporal (D-08, D-21): del filtro si se puede leer; si no,
    del rango real de los datos; en último caso, el año de la fecha de corte."""
    for f in spec.filtros:
        valores = f.valor if isinstance(f.valor, list) else [f.valor]
        if f.campo == "periodo_academico" and f.op in (Operador.IGUAL, Operador.EN):
            rangos = []
            for v in valores:
                anio, _, semestre = str(v).partition("-")
                if not anio.isdigit() or semestre not in ("1", "2"):
                    continue
                desde = date(int(anio), 1 if semestre == "1" else 7, 1)
                rangos.append((desde, date(int(anio), 6 if semestre == "1" else 12, 30 if semestre == "1" else 31)))
            if rangos:
                return min(a for a, _ in rangos), min(max(b for _, b in rangos), spec.corte)
        if f.campo == "anio" and f.op in (Operador.IGUAL, Operador.EN):
            anios = [int(v) for v in valores]
            return date(min(anios), 1, 1), min(date(max(anios), 12, 31), spec.corte)
    if "tiempo_anio" in datos.columns and not datos.empty:
        anios = pd.to_numeric(datos["tiempo_anio"], errors="coerce").dropna()
        if len(anios):
            return date(int(anios.min()), 1, 1), min(fin_de_mes(date(int(anios.max()), 12, 1)), spec.corte)
    return date(spec.corte.year, 1, 1), spec.corte


def _con_avisos(secciones: list[SeccionCalculada], avisos: Sequence[Aviso]) -> list[SeccionCalculada]:
    """Las advertencias de la validación y de la revisión de datos van en el texto (contrato, 4.4.3)."""
    if not secciones or not avisos:
        return secciones
    primera = secciones[0]
    mensajes = [a.mensaje for a in avisos if a.mensaje not in primera.advertencias]
    return [
        SeccionCalculada(primera.id, primera.indicadores, primera.metodo, [*mensajes, *primera.advertencias][:20]),
        *secciones[1:],
    ]


def _etiquetas(capa: CapaSemantica) -> dict[str, str]:
    return {c: m.nombre for c, m in capa.metricas.items()} | {c: d.nombre for c, d in capa.dimensiones.items()}


def _titulo(spec: SpecResuelta, capa: CapaSemantica, plantillas_nombres: dict[str, str] | None) -> str:
    if spec.base and plantillas_nombres and spec.base in plantillas_nombres:
        return f"{spec.base} · {plantillas_nombres[spec.base]}"
    nombres = [capa.metricas[m.id].nombre if m.id in capa.metricas else m.id for m in spec.metricas]
    titulo = " y ".join(nombres)
    dims = [capa.dimensiones[d.id].nombre.lower() for d in spec.dimensiones if d.id in capa.dimensiones]
    if dims:
        titulo += " por " + " y ".join(dims)
    return titulo[:1].upper() + titulo[1:]


def _anexo(spec: SpecResuelta, avisos: Sequence[Aviso], revision: RevisionDatos, plan_huella: str) -> tuple[str, ...]:
    lineas = [f"Fecha de corte: {spec.corte.isoformat()} (último mes cerrado o la indicada en la solicitud)."]
    if spec.periodo is not None:
        lineas.append(f"Periodo: {spec.periodo.desde.isoformat()} a {spec.periodo.hasta.isoformat()}.")
    if spec.filtros:
        filtros = "; ".join(f"{f.campo} {f.op.value} {f.valor}" for f in spec.filtros)
        lineas.append(f"Filtros: {filtros}.")
    grafico = revision.grafico
    origen = "pedido en la solicitud" if grafico.origen.value == "prompt" else "elegido por el recomendador"
    lineas.append(f"Gráfico: {grafico.tipo.value} ({origen}).")
    lineas += [f"Aviso: {a.mensaje}" for a in avisos]
    lineas.append(f"Huella de la especificación y del SQL: {plan_huella}.")
    return tuple(lineas)


def _narrativa(ctx: Contexto, contrato: Contrato, extra: list[float]) -> ResultadoFinal:
    """Pasos 12 a 17: caché por huella del contrato (RF-13), redacción, validación de cifras y plantilla."""
    en_cache = registro.narrativa_en_cache(ctx.rpt, contrato)
    plantilla = plantilla_por_defecto
    if en_cache is not None:
        return validar_con_regeneracion(en_cache, contrato, regenerar=None, plantilla=plantilla, extra=extra)
    redactor = ctx.redactor
    primera = None
    if redactor is not None:
        try:
            primera = redactor.redactar(contrato)
        except Exception:  # noqa: BLE001 - la capa de IA no puede tumbar el informe (RF-11)
            log.warning("la capa de IA no respondió; el informe sale con la plantilla", exc_info=True)
    regenerar = None
    if redactor is not None and primera is not None:

        def regenerar(anterior: Narrativa, discrepancias: tuple[Discrepancia, ...]):
            return redactor.regenerar(contrato, anterior, discrepancias)

    final = validar_con_regeneracion(primera, contrato, regenerar=regenerar, plantilla=plantilla, extra=extra)
    if not final.uso_plantilla:
        registro.guardar_narrativa(ctx.rpt, contrato, final.narrativa)
    return final


def _grafico(ctx: Contexto, datos, spec, revision, calculo: Calculo, titulo: str) -> tuple[Grafico | None, str | None]:
    try:
        grafico = generar_grafico(
            datos,
            spec,
            revision.grafico,
            titulo=titulo,
            etiquetas=_etiquetas(ctx.capa),
            fuente=FUENTE_GRAFICOS,
            analisis=calculo.analisis,
        )
        return grafico, None
    except (ValueError, KeyError) as e:
        log.warning("no se pudo dibujar el gráfico", exc_info=True)
        return None, f"No se pudo dibujar el gráfico {revision.grafico.tipo.value}: {e}."


def _corregible(codigo: str, mensaje: str, campo: str = "analisis") -> Informe:
    problema = Problema(codigo=codigo, paso=5, campo=campo, mensaje=mensaje, para="usuario")
    return Informe(estado=Estado.CORREGIBLE.value, problemas=(problema,))


def ejecutar_spec(
    ctx: Contexto,
    spec: SpecResuelta,
    *,
    avisos_validacion: Sequence[Aviso] = (),
    formatos: Sequence[Formato] = (Formato.HTML,),
    id_especificacion_bd: int = 1,
    fecha_solicitud: date | None = None,
    plantillas_nombres: dict[str, str] | None = None,
) -> Informe:
    """Pasos 8 a 18 para una spec ya resuelta (también sirve para reproducir un informe guardado, RNF-11)."""
    try:
        plan = compilar(spec, ctx.capa, sal=ctx.sal, limite_filas=ctx.limite_filas)
    except ErrorCompilacion as e:
        return Informe(estado=Estado.FUERA_DE_ALCANCE.value, problemas=(
            Problema(codigo=r.ALCANCE_NO_APLICABLE, paso=4, campo="alcance", mensaje=str(e)),))  # fmt: skip
    try:
        resultados = ejecutar(ctx.lectura, plan)
    except LimiteFilasExcedido as e:
        return _corregible(r.METODO_NO_APLICABLE, f"{e} Acote el periodo o agregue filtros.", "periodo")
    huella = huella_datos(resultados)
    datos, revision = _revisar(spec, resultados)
    try:
        calculo = calcular(
            spec,
            datos,
            ctx.capa,
            prueba=resultados.get(CONSULTA_PRUEBA),
            publicar_pronostico=revision.publicar_pronostico,
        )
    except AnalisisNoAplicable as e:
        return _corregible(r.METODO_NO_APLICABLE, f"Con los datos del periodo no se puede aplicar el método: {e}")

    avisos = tuple({(a.codigo, a.mensaje): a for a in (*avisos_validacion, *revision.avisos)}.values())
    secciones = _con_avisos(calculo.secciones, avisos)
    fecha = fecha_solicitud or date.today()
    contrato = empaquetar(
        spec,
        revision.grafico,
        secciones,
        capa=ctx.capa,
        id_spec=id_especificacion(fecha, (id_especificacion_bd - 1) % 9999 + 1),
        huella_datos=huella,
        periodo_datos=None if spec.periodo is not None else _rango_periodo(spec, datos),
    )
    titulo = _titulo(spec, ctx.capa, plantillas_nombres)
    grafico, nota_grafico = _grafico(ctx, datos, spec, revision, calculo, titulo)
    final = _narrativa(ctx, contrato, calculo.extra)
    modo = MODO_DEGRADADO if final.uso_plantilla else MODO_CON_IA

    nombres = _etiquetas(ctx.capa)
    tablas = {"Datos": tabla_para_exportar(datos, nombres)} if not datos.empty else {}
    tablas |= calculo.tablas
    anexo = _anexo(spec, avisos, revision, plan.huella)
    if nota_grafico:
        anexo += (nota_grafico,)
    ensamblado = InformeEnsamblado(
        titulo=titulo,
        contrato=contrato,
        narrativa=final.narrativa,
        modo=modo,
        tablas=tablas,
        graficos=(grafico,) if grafico is not None else (),
        anexo=anexo,
    )
    archivos = {f.value: exportar(ensamblado, f) for f in formatos}
    return Informe(
        estado=Estado.VALIDA.value,
        avisos=avisos,
        ensamblado=ensamblado,
        contrato=contrato,
        validacion=final,
        archivos=archivos,
        nombres={f.value: nombre_archivo(ensamblado, f) for f in formatos},
        huella_spec=spec.huella(),
        huella_sql=plan.huella,
        sql=plan.sql_texto(),
    )


def _seudonimo_usuario(ctx: Contexto, spec_datos: dict, id_usuario: int | str | None) -> str:
    alcance = spec_datos.get("alcance") if isinstance(spec_datos, dict) else None
    identificador = id_usuario
    if identificador is None and isinstance(alcance, dict):
        identificador = alcance.get("id_usuario")
    return seudonimizar(identificador if identificador is not None else "sin_usuario", ctx.sal)


def _guardar(ctx: Contexto, informe: Informe, id_solicitud: int, sql: str) -> None:
    validacion_registrada = False
    for formato, contenido in informe.archivos.items():
        ruta = None
        if ctx.directorio is not None:
            ctx.directorio.mkdir(parents=True, exist_ok=True)
            destino = ctx.directorio / f"{id_solicitud:06d}_{informe.nombres[formato]}"
            destino.write_bytes(contenido)
            ruta = str(destino)
        id_resultado = registro.registrar_resultado(
            ctx.rpt,
            id_solicitud=id_solicitud,
            formato=formato,
            huella_datos=informe.contrato.huella_datos,
            sql_compilado=sql,
            modo=informe.ensamblado.modo,
            ruta_archivo=ruta,
        )
        if not validacion_registrada:
            registro.registrar_validacion(ctx.rpt, id_resultado, informe.validacion)
            validacion_registrada = True


def procesar(
    ctx: Contexto,
    datos_spec: dict,
    *,
    hoy: date,
    formatos: Sequence[Formato] = (Formato.HTML,),
    prompt: str | None = None,
    id_usuario: int | str | None = None,
    plantillas_nombres: dict[str, str] | None = None,
) -> Informe:
    """Solicitud completa desde la spec que entrega la capa de IA (o el catálogo de plantillas).

    Registra SIEMPRE la spec y la solicitud en `rpt_` (también las rechazadas: son la evidencia de RF-12). La
    conexión `ctx.rpt` debe estar en una transacción que confirma quien llama.
    """
    validacion: ResultadoValidacion = validar(datos_spec, ctx.capa, hoy=hoy, plantillas=ctx.plantillas)
    base = datos_spec.get("base") if isinstance(datos_spec, dict) else None
    id_esp = registro.registrar_especificacion(
        ctx.rpt, datos_spec, validacion, id_plantilla=registro.id_plantilla(ctx.rpt, base)
    )
    seudonimo = _seudonimo_usuario(ctx, datos_spec, id_usuario)
    momento = datetime.combine(hoy, datetime.now().time())
    if validacion.estado is not Estado.VALIDA:
        id_sol = registro.registrar_solicitud(
            ctx.rpt, id_especificacion=id_esp, seudonimo_usuario=seudonimo, prompt=prompt, fecha_corte=None,
            estado=registro.ESTADO_RECHAZADA, fecha=momento,
        )  # fmt: skip
        return Informe(
            estado=validacion.estado.value,
            id_solicitud=id_sol,
            problemas=validacion.problemas,
            avisos=validacion.avisos,
        )
    spec = validacion.spec
    id_sol = registro.registrar_solicitud(
        ctx.rpt, id_especificacion=id_esp, seudonimo_usuario=seudonimo, prompt=prompt, fecha_corte=spec.corte,
        fecha=momento,
    )  # fmt: skip
    informe = ejecutar_spec(
        ctx,
        spec,
        avisos_validacion=validacion.avisos,
        formatos=formatos,
        id_especificacion_bd=id_esp,
        fecha_solicitud=hoy,
        plantillas_nombres=plantillas_nombres,
    )
    informe.id_solicitud = id_sol
    if informe.estado != Estado.VALIDA.value:
        registro.actualizar_solicitud(ctx.rpt, id_sol, estado=registro.ESTADO_RECHAZADA)
        return informe
    _guardar(ctx, informe, id_sol, informe.sql or "")
    registro.actualizar_solicitud(ctx.rpt, id_sol, estado=registro.ESTADO_COMPLETADA)
    return informe


def reproducir(
    ctx: Contexto, id_solicitud: int, formato: Formato, *, plantillas_nombres: dict[str, str] | None = None
) -> Informe | None:
    """Vuelve a generar el informe de una solicitud (RNF-11): valida otra vez la spec recibida con la fecha de la
    solicitud, comprueba que se resuelve igual (misma huella) y la ejecuta. El texto aprobado sale de la caché de
    narrativa si los datos no cambiaron (RF-13). No registra una solicitud nueva.
    Devuelve None si la solicitud no existe o no fue válida; lanza `SpecNoReproducible` si la capa semántica
    cambió y la misma spec ya no se resuelve igual."""
    fila = registro.solicitud_con_spec(ctx.rpt, id_solicitud)
    if fila is None or fila["estado_validacion"] != Estado.VALIDA.value:
        return None
    fecha = fila["fecha_solicitud"].date() if isinstance(fila["fecha_solicitud"], datetime) else date.today()
    validacion = validar(json.loads(fila["spec_json"]), ctx.capa, hoy=fecha, plantillas=ctx.plantillas)
    if validacion.spec is None or validacion.spec.huella() != fila["huella_spec"]:
        raise SpecNoReproducible(f"la solicitud {id_solicitud} ya no se resuelve igual con la capa semántica actual")
    informe = ejecutar_spec(
        ctx,
        validacion.spec,
        avisos_validacion=validacion.avisos,
        formatos=(formato,),
        id_especificacion_bd=fila["id_especificacion"],
        fecha_solicitud=fecha,
        plantillas_nombres=plantillas_nombres,
    )
    informe.id_solicitud = id_solicitud
    return informe
