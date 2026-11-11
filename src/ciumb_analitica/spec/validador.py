"""Validador de especificaciones: los siete pasos de la sección 4.4.2.

INTERFAZ CERRADA. Dos funciones:

- `validar(datos, capa, hoy=...)`: antes de tocar los datos. Devuelve `ResultadoValidacion` (válida,
  corregible o fuera de alcance). Si es válida trae la `SpecResuelta` que sigue al compilador.
- `revisar_datos(spec, datos)`: después de ejecutar la consulta. Aplica la parte de los pasos 5, 6 y 7 que
  depende de los datos: tamaño de muestra, forma real del resultado frente al gráfico y supresión de grupos
  con menos de cinco personas.

Pasos de `validar`:
 1. Esquema JSON y tipos. Un campo desconocido invalida la spec.
 2. Cada métrica, dimensión, filtro y variable existe en la capa semántica.
 7a. Ninguna dimensión, filtro o variable identifica personas (se revisa aquí para explicar bien el rechazo).
 3. Compatibilidad métrica x dimensión (matriz de bus) y agregación válida. Una razón no se suma.
 4. Alcance del rol (lo envía el backend). El prompt puede estrecharlo, nunca ampliarlo.
 5. El método es aplicable a los tipos de variable. Se decide el nivel de lectura (agregado o registro).
 6. El gráfico es compatible con la forma del resultado (Tabla 21), o se elige si no se indicó.

El sistema nunca adivina: si un código no existe, no se reemplaza por el más parecido; se devuelve la lista
de parecidos para repreguntar.
"""

from __future__ import annotations

import difflib
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import date

import pandas as pd
from pydantic import ValidationError
from sqlalchemy import Date, Integer, Numeric, SmallInteger

from ciumb_analitica.dw.tiempo import ultimo_mes_cerrado
from ciumb_analitica.semantica.modelos import Aditividad, CapaSemantica, Dimension, Metrica, TipoDimension
from ciumb_analitica.spec import resultado as r
from ciumb_analitica.spec.convenciones import (
    COL_N_PERSONAS,
    COL_PERSONA,
    DIMENSION_ALCANCE_COORDINADOR,
    DIMENSION_TIEMPO,
    HECHOS_POR_ROL,
    columnas_de_dimensiones,
)
from ciumb_analitica.spec.modelos import (
    Agregacion,
    AnalisisDescriptiva,
    DimensionSpec,
    Especificacion,
    Filtro,
    Granularidad,
    Operador,
    OrigenGrafico,
    Rol,
    TipoGrafico,
    cargar_especificacion,
)
from ciumb_analitica.spec.resultado import (
    Aviso,
    Estado,
    GraficoResuelto,
    MetricaResuelta,
    Nivel,
    PeriodoResuelto,
    Problema,
    ResultadoValidacion,
    SpecResuelta,
)

_FUERA_DE_ALCANCE = {
    r.METRICA_INEXISTENTE,
    r.DIMENSION_INEXISTENTE,
    r.DIMENSION_IDENTIFICA_PERSONAS,
    r.INCOMPATIBLE,
    r.ALCANCE_NO_APLICABLE,
    r.ALCANCE_EXCEDIDO,
}

_CORRELACIONES = ("pearson", "spearman")
_DOS_GRUPOS = ("t_student", "mann_whitney")
_CON_TIEMPO = ("serie", "variacion", "variacion_interanual", "pronostico")
_POR_REGISTRO = ("descriptiva", "atipicos")
_OPERADORES_DE_ORDEN = (Operador.MAYOR, Operador.MAYOR_IGUAL, Operador.MENOR, Operador.MENOR_IGUAL, Operador.ENTRE)

_NOMBRE_GRAFICO = {
    TipoGrafico.BARRAS: "barras",
    TipoGrafico.LINEAS: "líneas",
    TipoGrafico.TORTA: "torta",
    TipoGrafico.DISPERSION: "dispersión",
    TipoGrafico.MAPA_CALOR: "mapa de calor",
    TipoGrafico.HISTOGRAMA: "histograma",
}


@dataclass
class _Contexto:
    capa: CapaSemantica
    problemas: list[Problema] = field(default_factory=list)
    avisos: list[Aviso] = field(default_factory=list)

    def problema(self, codigo: str, paso: int, campo: str, mensaje: str, *, para="usuario", opciones=()) -> None:
        self.problemas.append(
            Problema(codigo=codigo, paso=paso, campo=campo, mensaje=mensaje, para=para, opciones=tuple(opciones))
        )

    def aviso(self, codigo: str, mensaje: str) -> None:
        self.avisos.append(Aviso(codigo=codigo, mensaje=mensaje))

    def rechazo(self) -> ResultadoValidacion:
        fuera = any(p.codigo in _FUERA_DE_ALCANCE for p in self.problemas)
        return ResultadoValidacion(
            estado=Estado.FUERA_DE_ALCANCE if fuera else Estado.CORREGIBLE, problemas=tuple(self.problemas)
        )


def validar(
    datos: dict, capa: CapaSemantica, *, hoy: date, plantillas: Collection[str] | None = None
) -> ResultadoValidacion:
    """Valida una spec (JSON decodificado) contra la capa semántica.

    Entradas: `datos` tal como llega de la capa de IA; `capa` semántica publicada; `hoy`, fecha de referencia
    (se inyecta para que el resultado sea reproducible); `plantillas`, códigos INF existentes (opcional).
    Salida: `ResultadoValidacion`. Nunca lanza por una spec mal formada: la clasifica.
    """
    ctx = _Contexto(capa)

    # Paso 1 ---------------------------------------------------------------------------------------------------
    try:
        spec = cargar_especificacion(datos)
    except ValidationError as error:
        for e in error.errors(include_input=False, include_url=False):
            campo = ".".join(str(x) for x in e["loc"]) or "$"
            if campo == "metricas" and e["type"] in ("missing", "too_short"):
                ctx.problema(r.FALTA_METRICA, 1, campo, "Falta indicar qué se quiere medir.")
            else:
                ctx.problema(r.ESQUEMA_INVALIDO, 1, campo, e["msg"], para="ia")
        return ctx.rechazo()
    except (TypeError, ValueError):
        ctx.problema(r.ESQUEMA_INVALIDO, 1, "$", "La especificación no es un objeto JSON válido.", para="ia")
        return ctx.rechazo()

    # Paso 2 ---------------------------------------------------------------------------------------------------
    _paso_2_existencia(ctx, spec, plantillas)
    if ctx.problemas:
        return ctx.rechazo()
    metricas = [capa.metrica(m.id) for m in spec.metricas]
    variables_dim = _variables_dimension(spec, capa)

    # Paso 7a ---------------------------------------------------------------------------------------------------
    usadas = _dimensiones_usadas(spec, variables_dim)
    for campo, codigo in usadas:
        if capa.dimension(codigo).identifica_persona:
            opciones = sorted(set.intersection(*(set(capa.dimensiones_compatibles(m.codigo)) for m in metricas)))
            ctx.problema(
                r.DIMENSION_IDENTIFICA_PERSONAS,
                7,
                campo,
                f"«{capa.dimension(codigo).nombre}» identifica personas y no se puede consultar (RNF-05, RNF-06). "
                "Se puede entregar la misma medida agrupada por otra dimensión.",
                opciones=[o for o in opciones if capa.dimension(o).binaria_de_metrica is None],
            )
    if ctx.problemas:
        return ctx.rechazo()

    # Paso 3 ---------------------------------------------------------------------------------------------------
    resueltas = _paso_3_compatibilidad(ctx, spec, metricas, usadas)
    if ctx.problemas:
        return ctx.rechazo()

    # Paso 4 ---------------------------------------------------------------------------------------------------
    _paso_4_alcance(ctx, spec, metricas)
    periodo, corte = _resolver_periodo(ctx, spec, hoy)
    if ctx.problemas:
        return ctx.rechazo()

    # Paso 5 ---------------------------------------------------------------------------------------------------
    analisis = spec.analisis or AnalisisDescriptiva(metodo="descriptiva")
    dimensiones = tuple(
        DimensionSpec(id=d.id, granularidad=d.granularidad or Granularidad.MES) if d.id == DIMENSION_TIEMPO else d
        for d in spec.dimensiones
    )
    nivel = _paso_5_metodo(ctx, spec, analisis, metricas, dimensiones)
    if ctx.problemas:
        return ctx.rechazo()
    if nivel is Nivel.REGISTRO:
        resueltas = [
            MetricaResuelta(id=m.id, agregacion=m.agregacion if m.agregacion is Agregacion.MEDIANA else None)
            for m in resueltas
        ]

    # Paso 6 ---------------------------------------------------------------------------------------------------
    grafico = _paso_6_grafico(ctx, spec, analisis, metricas, dimensiones, nivel)

    resuelta = SpecResuelta(
        esquema=spec.esquema,
        origen=spec.origen,
        base=spec.base,
        metricas=tuple(resueltas),
        dimensiones=dimensiones,
        filtros=tuple(spec.filtros),
        periodo=periodo,
        corte=corte,
        analisis=analisis,
        grafico=grafico,
        alcance=spec.alcance,
        salida=spec.salida,
        nivel=nivel,
    )
    return ResultadoValidacion(estado=Estado.VALIDA, spec=resuelta, avisos=tuple(ctx.avisos))


# --- Paso 2 ---------------------------------------------------------------------------------------------------


def _parecidos(codigo: str, candidatos: Collection[str]) -> list[str]:
    return difflib.get_close_matches(codigo, sorted(candidatos), n=3, cutoff=0.75)


def _exigir_metrica(ctx: _Contexto, codigo: str, campo: str) -> None:
    if ctx.capa.metrica(codigo) is None:
        parecidas = _parecidos(codigo, [c for c, m in ctx.capa.metricas.items() if m.activa])
        if parecidas:
            ctx.problema(
                r.METRICA_PARECIDA,
                2,
                campo,
                f"No existe la métrica «{codigo}». ¿Es alguna de estas?",
                opciones=parecidas,
            )
        else:
            ctx.problema(r.METRICA_INEXISTENTE, 2, campo, f"El sistema no tiene una métrica «{codigo}».")


def _exigir_dimension(ctx: _Contexto, codigo: str, campo: str) -> None:
    if ctx.capa.dimension(codigo) is None:
        parecidas = _parecidos(codigo, ctx.capa.dimensiones)
        if parecidas:
            ctx.problema(
                r.DIMENSION_PARECIDA,
                2,
                campo,
                f"No existe la dimensión «{codigo}». ¿Es alguna de estas?",
                opciones=parecidas,
            )
        else:
            ctx.problema(r.DIMENSION_INEXISTENTE, 2, campo, f"El sistema no tiene una dimensión «{codigo}».")


def _paso_2_existencia(ctx: _Contexto, spec: Especificacion, plantillas: Collection[str] | None) -> None:
    for i, m in enumerate(spec.metricas):
        _exigir_metrica(ctx, m.id, f"metricas.{i}.id")
    for i, d in enumerate(spec.dimensiones):
        _exigir_dimension(ctx, d.id, f"dimensiones.{i}.id")
    for i, f in enumerate(spec.filtros):
        _exigir_dimension(ctx, f.campo, f"filtros.{i}.campo")
    for i, v in enumerate(getattr(spec.analisis, "variables", None) or []):
        if ctx.capa.metrica(v) is None and ctx.capa.dimension(v) is None:
            parecidas = _parecidos(v, list(ctx.capa.metricas) + list(ctx.capa.dimensiones))
            codigo = r.DIMENSION_PARECIDA if parecidas else r.DIMENSION_INEXISTENTE
            ctx.problema(
                codigo, 2, f"analisis.variables.{i}", f"El sistema no tiene una variable «{v}».", opciones=parecidas
            )
    if plantillas is not None and spec.base is not None and spec.base not in plantillas:
        ctx.problema(
            r.PLANTILLA_INEXISTENTE, 2, "base", f"No existe la plantilla base {spec.base}.", opciones=sorted(plantillas)
        )


def _variables_dimension(spec: Especificacion, capa: CapaSemantica) -> list[str]:
    return [v for v in (getattr(spec.analisis, "variables", None) or []) if capa.dimension(v) is not None]


def _dimensiones_usadas(spec: Especificacion, variables_dim: list[str]) -> list[tuple[str, str]]:
    """(campo de la spec, código de dimensión) de todo lo que se agrupa, se filtra o se cruza."""
    usadas = [(f"dimensiones.{i}.id", d.id) for i, d in enumerate(spec.dimensiones)]
    usadas += [(f"filtros.{i}.campo", f.campo) for i, f in enumerate(spec.filtros)]
    usadas += [("analisis.variables", v) for v in variables_dim]
    return usadas


# --- Paso 3 ---------------------------------------------------------------------------------------------------


def _paso_3_compatibilidad(
    ctx: _Contexto, spec: Especificacion, metricas: list[Metrica], usadas: list[tuple[str, str]]
) -> list[MetricaResuelta]:
    capa = ctx.capa
    for campo, codigo in usadas:
        dimension = capa.dimension(codigo)
        if dimension.binaria_de_metrica:
            if not campo.startswith("analisis"):
                ctx.problema(
                    r.DIMENSION_SOLO_PRUEBA,
                    3,
                    campo,
                    f"«{dimension.nombre}» solo se puede usar como variable de una prueba de hipótesis.",
                )
            elif dimension.binaria_de_metrica not in [m.codigo for m in metricas]:
                ctx.problema(
                    r.INCOMPATIBLE,
                    3,
                    campo,
                    f"«{dimension.nombre}» solo aplica a la métrica «{dimension.binaria_de_metrica}».",
                    opciones=[dimension.binaria_de_metrica],
                )
            continue
        for m in metricas:
            if not capa.es_compatible(m.codigo, codigo):
                ctx.problema(
                    r.INCOMPATIBLE,
                    3,
                    campo,
                    f"«{m.nombre}» no se puede cruzar con «{dimension.nombre}»: ese dato no se registra "
                    "con esa dimensión.",
                    opciones=capa.dimensiones_compatibles(m.codigo),
                )

    for i, d in enumerate(spec.dimensiones):
        if d.granularidad is not None and d.id != DIMENSION_TIEMPO:
            ctx.problema(
                r.GRANULARIDAD_NO_APLICA,
                3,
                f"dimensiones.{i}.granularidad",
                "Solo la dimensión «tiempo» admite granularidad.",
                para="ia",
            )

    for i, f in enumerate(spec.filtros):
        dimension = capa.dimension(f.campo)
        if not dimension.binaria_de_metrica:
            _revisar_filtro(ctx, f, dimension, f"filtros.{i}")

    resueltas = []
    for i, (pedida, m) in enumerate(zip(spec.metricas, metricas, strict=True)):
        agregacion = pedida.agregacion or m.agregacion_defecto
        if agregacion not in m.agregaciones:
            detalle = (
                " Es una razón: no se suma ni se promedia entre grupos, se recalcula desde sus componentes."
                if m.es_razon
                else ""
            )
            ctx.problema(
                r.AGREGACION_INVALIDA,
                3,
                f"metricas.{i}.agregacion",
                f"«{m.nombre}» no admite la agregación «{agregacion.value}».{detalle}",
                opciones=[a.value for a in m.agregaciones],
            )
        resueltas.append(MetricaResuelta(id=m.codigo, agregacion=agregacion))
    return resueltas


def _tipo_esperado(dimension: Dimension) -> type:
    tipo = dimension.columna.type
    if isinstance(tipo, Date):
        return date
    if isinstance(tipo, (Integer, SmallInteger, Numeric)):
        return int
    return str


def _revisar_filtro(ctx: _Contexto, f: Filtro, dimension: Dimension, campo: str) -> None:
    ordenable = dimension.tipo in (TipoDimension.TEMPORAL, TipoDimension.ORDINAL)
    if f.op in _OPERADORES_DE_ORDEN and not ordenable:
        ctx.problema(
            r.OPERADOR_INVALIDO,
            3,
            f"{campo}.op",
            f"«{dimension.nombre}» es una categoría: solo admite =, != y 'en'.",
            para="ia",
        )
        return
    esperado = _tipo_esperado(dimension)
    valores = f.valor if isinstance(f.valor, list) else [f.valor]
    for v in valores:
        if esperado is date:
            try:
                correcto = isinstance(v, str) and bool(date.fromisoformat(v))
            except ValueError:
                correcto = False
        elif esperado is int:
            correcto = isinstance(v, int) and not isinstance(v, bool)
        else:
            correcto = isinstance(v, str)
        if not correcto:
            nombre = {date: "una fecha AAAA-MM-DD", int: "un número entero", str: "un texto"}[esperado]
            ctx.problema(
                r.VALOR_INVALIDO, 3, f"{campo}.valor", f"El filtro por «{dimension.nombre}» espera {nombre}.", para="ia"
            )
            return


# --- Paso 4 ---------------------------------------------------------------------------------------------------


def _paso_4_alcance(ctx: _Contexto, spec: Especificacion, metricas: list[Metrica]) -> None:
    """El alcance lo fija el backend (RF-21). Si no se puede aplicar a una métrica, la métrica se niega (D-20)."""
    alcance = spec.alcance
    if alcance.rol is Rol.COORDINADOR:
        for i, m in enumerate(metricas):
            if not ctx.capa.es_compatible(m.codigo, DIMENSION_ALCANCE_COORDINADOR):
                ctx.problema(
                    r.ALCANCE_NO_APLICABLE,
                    4,
                    f"metricas.{i}.id",
                    f"«{m.nombre}» no se registra por facultad, así que no se puede limitar a "
                    f"{alcance.facultad}. La consulta un directivo.",
                )
        for i, f in enumerate(spec.filtros):
            if f.campo == DIMENSION_ALCANCE_COORDINADOR and f.op in (Operador.IGUAL, Operador.EN):
                pedidas = set(f.valor if isinstance(f.valor, list) else [f.valor])
                if pedidas - {alcance.facultad}:
                    ctx.problema(
                        r.ALCANCE_EXCEDIDO,
                        4,
                        f"filtros.{i}.valor",
                        f"Su rol solo permite consultar la facultad {alcance.facultad}.",
                    )
    elif alcance.rol in HECHOS_POR_ROL:
        permitidos = HECHOS_POR_ROL[alcance.rol]
        for i, m in enumerate(metricas):
            if m.hecho_o_agregado not in permitidos:
                ctx.problema(
                    r.ALCANCE_NO_APLICABLE,
                    4,
                    f"metricas.{i}.id",
                    f"El rol {alcance.rol.value} solo puede consultar lo que tiene a su cargo; "
                    f"«{m.nombre}» no hace parte.",
                )


def _resolver_periodo(ctx: _Contexto, spec: Especificacion, hoy: date) -> tuple[PeriodoResuelto | None, date]:
    """D-08: `periodo` es opcional; un filtro temporal cuenta como periodo; si no, último periodo cerrado."""
    cierre = ultimo_mes_cerrado(hoy)
    if spec.periodo is not None:
        desde, hasta = spec.periodo.desde, spec.periodo.hasta
        if desde > cierre:
            ctx.problema(
                r.PERIODO_FUTURO,
                4,
                "periodo.desde",
                f"El periodo pedido aún no tiene datos cerrados (último cierre: {cierre.isoformat()}).",
            )
            return None, cierre
        if hasta > cierre:
            ctx.aviso(
                r.PERIODO_RECORTADO,
                f"El periodo se limita al {cierre.isoformat()}, último mes cerrado; lo posterior está "
                "incompleto y se excluye.",
            )
            hasta = cierre
        corte = min(spec.periodo.corte or hasta, cierre)
        return PeriodoResuelto(desde=desde, hasta=hasta), corte
    if any(ctx.capa.dimension(f.campo).es_temporal for f in spec.filtros):
        return None, cierre
    desde = date(cierre.year, 1, 1)
    ctx.aviso(
        r.PERIODO_POR_DEFECTO,
        f"La solicitud no indica periodo: se usa el último periodo cerrado, del {desde.isoformat()} al "
        f"{cierre.isoformat()}.",
    )
    return PeriodoResuelto(desde=desde, hasta=cierre), cierre


# --- Paso 5 ---------------------------------------------------------------------------------------------------


def _paso_5_metodo(ctx: _Contexto, spec: Especificacion, analisis, metricas: list[Metrica], dimensiones) -> Nivel:
    capa = ctx.capa
    metodo = analisis.metodo
    codigos = [m.codigo for m in metricas]
    hay_tiempo = any(d.id == DIMENSION_TIEMPO for d in dimensiones)
    hay_conteo = any(m.es_conteo for m in metricas)
    variables = list(getattr(analisis, "variables", []))
    por_registro = False

    if metodo in _CORRELACIONES:
        if not all(v in codigos for v in variables):
            ctx.problema(
                r.VARIABLES_INVALIDAS,
                5,
                "analisis.variables",
                "La correlación necesita dos métricas numéricas que estén en `metricas`.",
                opciones=codigos,
            )
        por_registro = not dimensiones
    elif metodo == "chi_cuadrado":
        dims = [capa.dimension(v) for v in variables]
        if any(d is None or d.es_temporal for d in dims):
            ctx.problema(
                r.VARIABLES_INVALIDAS, 5, "analisis.variables", "El chi-cuadrado necesita dos dimensiones categóricas."
            )
        else:
            binarias = [d for d in dims if d.binaria_de_metrica]
            if len(binarias) == 2:
                ctx.problema(
                    r.VARIABLES_INVALIDAS,
                    5,
                    "analisis.variables",
                    "El chi-cuadrado necesita al menos una dimensión de agrupación.",
                )
            elif not binarias and not all(m.es_conteo or m.aditividad is not Aditividad.NO_ADITIVA for m in metricas):
                ctx.problema(
                    r.METODO_NO_APLICABLE,
                    5,
                    "analisis.metodo",
                    "El chi-cuadrado compara frecuencias: necesita una métrica de conteo.",
                )
    elif metodo in _DOS_GRUPOS:
        metrica, grupo = capa.metrica(variables[0]), capa.dimension(variables[1])
        if metrica is None or variables[0] not in codigos or grupo is None or grupo.es_temporal:
            ctx.problema(
                r.VARIABLES_INVALIDAS,
                5,
                "analisis.variables",
                "La prueba necesita [métrica numérica de `metricas`, dimensión de dos grupos].",
                opciones=codigos,
            )
        elif metrica.es_conteo:
            ctx.problema(
                r.METODO_NO_APLICABLE,
                5,
                "analisis.metodo",
                f"«{metrica.nombre}» es un conteo; la prueba compara una medida registro a registro.",
            )
        por_registro = True
    elif metodo in _CON_TIEMPO:
        if not hay_tiempo:
            ctx.problema(
                r.FALTA_DIMENSION_TEMPORAL,
                5,
                "dimensiones",
                "Este análisis necesita una serie de tiempo: ¿por mes, trimestre, semestre o año?",
                opciones=[g.value for g in Granularidad],
            )
    elif metodo == "segmentacion":
        if not [d for d in dimensiones if d.id != DIMENSION_TIEMPO]:
            ctx.problema(
                r.FALTA_UNIDAD_DE_ANALISIS,
                5,
                "dimensiones",
                "La segmentación necesita saber qué se agrupa (por ejemplo, empresas).",
            )
    elif metodo in _POR_REGISTRO:
        por_registro = not hay_conteo

    if any(m.agregacion is Agregacion.MEDIANA for m in spec.metricas):
        por_registro = True  # la mediana no es portable en SQL: se calcula con pandas sobre los registros
    if spec.grafico and spec.grafico.tipo is TipoGrafico.HISTOGRAMA and metodo in _POR_REGISTRO + _CORRELACIONES:
        por_registro = por_registro or not hay_conteo

    if por_registro and not ctx.problemas:
        if hay_conteo:
            ctx.problema(
                r.METODO_NO_APLICABLE,
                5,
                "metricas",
                "Un conteo no se puede leer registro a registro; pida una medida o quite la mediana.",
            )
        elif len({m.hecho_o_agregado for m in metricas}) > 1:
            ctx.problema(
                r.METRICAS_DE_HECHOS_DISTINTOS,
                5,
                "metricas",
                "Estas métricas se registran por separado: para compararlas registro a registro hay que "
                "agruparlas por una dimensión común (por ejemplo, empresa).",
            )
    return Nivel.REGISTRO if por_registro else Nivel.AGREGADO


# --- Paso 6 ---------------------------------------------------------------------------------------------------


def _compatible(tipo: TipoGrafico, capa, metricas, resueltas_agregacion, dimensiones, nivel, hay_tiempo) -> bool:
    n_dims = len(dimensiones)
    if tipo is TipoGrafico.BARRAS:
        return True
    if tipo is TipoGrafico.LINEAS:
        return hay_tiempo
    if tipo is TipoGrafico.TORTA:
        m = metricas[0]
        return (
            n_dims == 1
            and not hay_tiempo
            and len(metricas) == 1
            and nivel is Nivel.AGREGADO
            and m.aditividad is not Aditividad.NO_ADITIVA
            and resueltas_agregacion[0] in (Agregacion.CONTEO, Agregacion.SUMA)
        )
    if tipo is TipoGrafico.DISPERSION:
        return len(metricas) >= 2 and (nivel is Nivel.REGISTRO or n_dims >= 1)
    if tipo is TipoGrafico.MAPA_CALOR:
        return n_dims == 2 and len(metricas) == 1 and nivel is Nivel.AGREGADO
    return nivel is Nivel.REGISTRO  # histograma: una métrica medida registro a registro


def _sustituto(tipo: TipoGrafico, hay_tiempo: bool) -> TipoGrafico:
    """Tipo compatible más cercano (última columna de la Tabla 21)."""
    if tipo is TipoGrafico.TORTA and hay_tiempo:
        return TipoGrafico.LINEAS
    return TipoGrafico.BARRAS


def _recomendar(analisis, hay_tiempo: bool, nivel: Nivel, compatible) -> TipoGrafico:
    """Reglas fijas (Tabla 21): la misma spec siempre produce el mismo gráfico. La torta nunca se recomienda."""
    if analisis.metodo in _CORRELACIONES + ("segmentacion",) and compatible(TipoGrafico.DISPERSION):
        return TipoGrafico.DISPERSION
    if hay_tiempo:
        return TipoGrafico.LINEAS
    if analisis.metodo in _POR_REGISTRO and nivel is Nivel.REGISTRO:
        return TipoGrafico.HISTOGRAMA
    return TipoGrafico.BARRAS


def _paso_6_grafico(ctx: _Contexto, spec: Especificacion, analisis, metricas, dimensiones, nivel) -> GraficoResuelto:
    hay_tiempo = any(ctx.capa.dimension(d.id).es_temporal for d in dimensiones)
    agregaciones = [m.agregacion or metricas[i].agregacion_defecto for i, m in enumerate(spec.metricas)]

    def compatible(tipo: TipoGrafico) -> bool:
        return _compatible(tipo, ctx.capa, metricas, agregaciones, dimensiones, nivel, hay_tiempo)

    if spec.grafico is None:
        return GraficoResuelto(
            tipo=_recomendar(analisis, hay_tiempo, nivel, compatible), origen=OrigenGrafico.RECOMENDADO
        )
    pedido = spec.grafico.tipo
    if compatible(pedido):
        sectores = (spec.grafico.max_sectores or r.MAX_SECTORES_TORTA) if pedido is TipoGrafico.TORTA else None
        return GraficoResuelto(tipo=pedido, origen=spec.grafico.origen, max_sectores=sectores)
    final = _sustituto(pedido, hay_tiempo)
    ctx.aviso(
        r.GRAFICO_SUSTITUIDO,
        f"Se pidió un gráfico de {_NOMBRE_GRAFICO[pedido]}, que no es compatible con estos datos; se "
        f"entrega en {_NOMBRE_GRAFICO[final]}.",
    )
    return GraficoResuelto(tipo=final, origen=spec.grafico.origen, pedido=pedido)


# --- Después de los datos: parte de los pasos 5, 6 y 7 que depende del resultado ----------------------------------


@dataclass(frozen=True)
class RevisionDatos:
    """Salida de `revisar_datos`.

    datos: resultado sin los grupos suprimidos y sin las columnas auxiliares de personas.
    grafico: gráfico final (puede cambiar frente al de la spec si la forma real no lo admite).
    avisos: advertencias que deben ir al anexo y a `advertencias` del contrato.
    publicar_pronostico: False si la serie tiene menos de 12 puntos (RNF-13).
    grupos_suprimidos: cuántos grupos se retiraron por tener menos de cinco personas.
    """

    datos: pd.DataFrame
    grafico: GraficoResuelto
    avisos: tuple[Aviso, ...]
    publicar_pronostico: bool
    grupos_suprimidos: int


def revisar_datos(spec: SpecResuelta, datos: pd.DataFrame) -> RevisionDatos:
    """Revisa el resultado de la consulta principal de una spec válida (ver docstring del módulo).

    Entradas: `spec` resuelta y `datos` con las columnas de `spec.convenciones`.
    No modifica `datos`. El chi-cuadrado con esperados < 5 lo advierte `motor.inferencia` (CHI2_ESPERADO_BAJO).
    """
    avisos: list[Aviso] = []
    columnas_dim = [c for c in columnas_de_dimensiones(spec.dimensiones) if c in datos.columns]
    datos, suprimidos = _suprimir_grupos(datos, columnas_dim)
    if suprimidos:
        avisos.append(
            Aviso(
                codigo=r.GRUPOS_SUPRIMIDOS,
                mensaje=f"Se omiten {suprimidos} grupo(s) con menos de {r.MIN_PERSONAS_GRUPO} personas "
                "para proteger su identidad.",
            )
        )

    grafico = spec.grafico
    n = len(datos)

    publicar = True
    if spec.analisis.metodo == "pronostico" and n < r.MIN_PUNTOS_PRONOSTICO:
        publicar = False
        avisos.append(
            Aviso(
                codigo=r.PRONOSTICO_NO_PUBLICABLE,
                mensaje=f"La serie tiene {n} puntos; se necesitan al menos {r.MIN_PUNTOS_PRONOSTICO} "
                "para publicar un pronóstico.",
            )
        )

    def sustituir(final: TipoGrafico, razon: str) -> GraficoResuelto:
        avisos.append(
            Aviso(
                codigo=r.GRAFICO_SUSTITUIDO,
                mensaje=f"El gráfico de {_NOMBRE_GRAFICO[grafico.tipo]} no es adecuado ({razon}); se "
                f"entrega en {_NOMBRE_GRAFICO[final]}.",
            )
        )
        return GraficoResuelto(tipo=final, origen=grafico.origen, pedido=grafico.pedido or grafico.tipo)

    if grafico.tipo is TipoGrafico.TORTA:
        valores = datos[spec.metricas[0].id]
        if (valores < 0).any():
            grafico = sustituir(TipoGrafico.BARRAS, "hay valores negativos")
        elif n > (grafico.max_sectores or r.MAX_SECTORES_TORTA):
            tope = grafico.max_sectores or r.MAX_SECTORES_TORTA
            avisos.append(
                Aviso(
                    codigo=r.TORTA_OTROS,
                    mensaje=f"Hay {n} categorías; la torta muestra las {tope - 1} mayores y agrupa "
                    f"las {n - tope + 1} restantes en «Otros».",
                )
            )
    elif grafico.tipo is TipoGrafico.MAPA_CALOR:
        lados = _lados(datos, spec)
        if min(lados) < r.MIN_LADO_MAPA_CALOR:
            grafico = sustituir(TipoGrafico.BARRAS, f"el cruce tiene {lados[0]} x {lados[1]} celdas")
    elif grafico.tipo is TipoGrafico.HISTOGRAMA:
        if n < r.MIN_OBS_HISTOGRAMA:
            avisos.append(
                Aviso(
                    codigo=r.MUESTRA_PEQUENA,
                    mensaje=f"El histograma se construye con {n} observaciones (menos de "
                    f"{r.MIN_OBS_HISTOGRAMA}): interprételo con cautela.",
                )
            )
    elif (
        grafico.tipo is TipoGrafico.BARRAS
        and grafico.origen is OrigenGrafico.RECOMENDADO
        and grafico.pedido is None
        and len(spec.dimensiones) == 2
        and len(spec.metricas) == 1
        and spec.nivel is Nivel.AGREGADO
    ):
        lados = _lados(datos, spec)
        if min(lados) >= r.MIN_LADO_MAPA_CALOR and lados[0] * lados[1] > r.MAX_CATEGORIAS_BARRAS:
            grafico = GraficoResuelto(tipo=TipoGrafico.MAPA_CALOR, origen=OrigenGrafico.RECOMENDADO)

    return RevisionDatos(
        datos=datos, grafico=grafico, avisos=tuple(avisos), publicar_pronostico=publicar, grupos_suprimidos=suprimidos
    )


def _lados(datos: pd.DataFrame, spec: SpecResuelta) -> tuple[int, int]:
    """Número de categorías distintas de cada una de las dos dimensiones del cruce."""
    lados = []
    for d in spec.dimensiones[:2]:
        columnas = [c for c in columnas_de_dimensiones([d]) if c in datos.columns]
        lados.append(len(datos[columnas].drop_duplicates()) if columnas else 0)
    return lados[0], lados[1]


def _suprimir_grupos(datos: pd.DataFrame, columnas_dim: list[str]) -> tuple[pd.DataFrame, int]:
    """Paso 7: retira los grupos con menos de cinco personas (RNF-05, RNF-06) y las columnas auxiliares."""
    suprimidos = 0
    if COL_N_PERSONAS in datos.columns:
        pequenos = datos[COL_N_PERSONAS] < r.MIN_PERSONAS_GRUPO
        suprimidos = int(pequenos.sum())
        datos = datos.loc[~pequenos]
    elif COL_PERSONA in datos.columns:
        if columnas_dim:
            personas = datos.groupby(columnas_dim, dropna=False)[COL_PERSONA].transform("nunique")
            pequenos = personas < r.MIN_PERSONAS_GRUPO
            suprimidos = len(datos.loc[pequenos, columnas_dim].drop_duplicates())
            datos = datos.loc[~pequenos]
        elif datos[COL_PERSONA].nunique() < r.MIN_PERSONAS_GRUPO and len(datos):
            suprimidos, datos = 1, datos.iloc[0:0]
    auxiliares = [c for c in (COL_N_PERSONAS, COL_PERSONA) if c in datos.columns]
    return datos.drop(columns=auxiliares).reset_index(drop=True), suprimidos
