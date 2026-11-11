"""Compilador de consultas: `SpecResuelta` -> SQL parametrizado con SQLAlchemy Core (sección 4.4.2, RF-12).

INTERFAZ CERRADA.

Garantías (invariantes 2, 3 y 6):
- Identificadores: solo tablas y columnas de `dw.esquema` alcanzadas a través de la capa semántica. Ningún
  texto de la spec se interpola en el SQL.
- Valores: todos viajan como parámetros con nombre (`p1`, `p2`…), incluidos los del alcance.
- Solo SELECT sobre el esquema `ana_`, con límite de filas.
- Determinismo: misma spec resuelta -> mismo SQL y mismos parámetros -> misma huella (caché RF-13,
  reproducción RNF-11).

Reglas de cálculo:
- Una razón nunca se suma ni se promedia: se calcula SUM(num) / SUM(den) en el grano pedido y sus componentes
  viajan en `<metrica>__num` y `<metrica>__den` para recalcular cualquier total.
- Instantáneas periódicas (Tabla 17): las medidas no se suman entre fechas de corte. Se toma el último corte
  de cada periodo de la agrupación temporal (o del periodo completo si no se agrupa por tiempo).
- Agregados precalculados: se prefieren al hecho base cuando cubren todas las dimensiones que la consulta
  necesita (agrupación, filtros y alcance) y la agregación es conteo, suma o razón.
- Alcance del rol (RF-21, D-20): se agrega siempre al WHERE; el compilador falla si no puede aplicarlo.

Un plan tiene una consulta `principal` por cada hecho o agregado que aportan las métricas (P8 usa tres) y,
si el análisis es chi-cuadrado, una consulta `prueba` con la tabla de contingencia (D-06).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date

import pandas as pd
from sqlalchemy import Column, Connection, Float, Select, Table, and_, bindparam, cast, func, select
from sqlalchemy.engine.default import DefaultDialect

from ciumb_analitica.dw import esquema as dw
from ciumb_analitica.dw.tiempo import sk_fecha
from ciumb_analitica.semantica.expresion import Expresion
from ciumb_analitica.semantica.modelos import CapaSemantica, Dimension, Metrica, alcanzable
from ciumb_analitica.seudonimo import seudonimizar
from ciumb_analitica.spec.convenciones import (
    COL_N_PERSONAS,
    COL_PERSONA,
    COLUMNAS_GRANULARIDAD,
    DIMENSION_ALCANCE_COORDINADOR,
    DIMENSION_TIEMPO,
    HECHOS_POR_ROL,
    SUFIJO_DEN,
    SUFIJO_NUM,
)
from ciumb_analitica.spec.modelos import Agregacion, DimensionSpec, Filtro, Granularidad, Operador, Rol
from ciumb_analitica.spec.resultado import MetricaResuelta, Nivel, SpecResuelta

LIMITE_FILAS_DEFECTO = 100_000
COL_REGISTRO = "_registro"
"""Identificador del registro en nivel `registro` (dimensión degenerada del hecho). Nunca viaja a la IA."""

CONSULTA_PRINCIPAL = "principal"
CONSULTA_PRUEBA = "prueba"

_AGREGACIONES_CON_AGREGADO = (Agregacion.CONTEO, Agregacion.SUMA, Agregacion.RAZON)


class ErrorCompilacion(Exception):  # noqa: N818 - nombre de dominio en español
    """La spec resuelta no se puede compilar. Con una spec que pasó el validador no debería ocurrir."""


class LimiteFilasExcedido(Exception):  # noqa: N818
    pass


@dataclass(frozen=True)
class Consulta:
    """Una sentencia SELECT compilada.

    nombre: `principal` o `prueba`; con varias tablas, `principal:<tabla>`.
    tabla: hecho o agregado de `ana_` que se lee.
    sentencia: objeto SQLAlchemy Core listo para ejecutar.
    sql / parametros: texto con parámetros con nombre y sus valores (para la huella y `rpt_resultado`).
    columnas: nombres de las columnas del resultado, según `spec.convenciones`.
    metricas: códigos de las métricas que trae.
    """

    nombre: str
    tabla: str
    sentencia: Select
    sql: str
    parametros: dict
    columnas: tuple[str, ...]
    metricas: tuple[str, ...]
    usa_agregado: bool


@dataclass(frozen=True)
class PlanConsulta:
    consultas: tuple[Consulta, ...]
    limite_filas: int
    huella: str
    """SHA-256 (64 hex) del SQL y los parámetros de todas las consultas."""

    def consulta(self, nombre: str) -> Consulta:
        return next(c for c in self.consultas if c.nombre == nombre)

    @property
    def principales(self) -> tuple[Consulta, ...]:
        return tuple(c for c in self.consultas if c.nombre.startswith(CONSULTA_PRINCIPAL))

    def sql_texto(self) -> str:
        """SQL de todas las consultas con sus parámetros, para `rpt_resultado.sql_compilado`."""
        return "\n\n".join(
            f"-- {c.nombre}\n{c.sql}\n-- parametros: {json.dumps(_serializable(c.parametros), ensure_ascii=False)}"
            for c in self.consultas
        )


def _serializable(parametros: dict) -> dict:
    return {k: (v.isoformat() if isinstance(v, date) else v) for k, v in sorted(parametros.items())}


class _Parametros:
    """Parámetros con nombres secuenciales y estables (`p1`, `p2`…) en orden de construcción."""

    def __init__(self) -> None:
        self._n = 0

    def nuevo(self, valor, *, expandir: bool = False):
        self._n += 1
        return bindparam(f"p{self._n}", valor, expanding=expandir)


# --- API -----------------------------------------------------------------------------------------------------


def compilar(
    spec: SpecResuelta,
    capa: CapaSemantica,
    *,
    sal: str | None = None,
    limite_filas: int = LIMITE_FILAS_DEFECTO,
) -> PlanConsulta:
    """Compila una spec resuelta (salida de `spec.validador.validar`).

    Entradas: `spec` válida; `capa` semántica (lista blanca); `sal` de seudonimización, obligatoria solo si el
    rol es tutor o consultor; `limite_filas`, tope de filas por consulta (invariante 3).
    Salida: `PlanConsulta`. Lanza `ErrorCompilacion` si la spec nombra algo que la capa no tiene o si el
    alcance no se puede aplicar.
    """
    metricas = [(_metrica(capa, m.id), m) for m in spec.metricas]
    dimensiones = list(spec.dimensiones)
    variables = list(getattr(spec.analisis, "variables", []) or [])
    metodo = spec.analisis.metodo

    if metodo in ("t_student", "mann_whitney") and variables[1] not in [d.id for d in dimensiones]:
        dimensiones.append(DimensionSpec(id=variables[1]))  # la variable de agrupación acompaña a cada registro

    params = _Parametros()
    consultas: list[Consulta] = []

    grupos: dict[str, list[tuple[Metrica, MetricaResuelta, Expresion]]] = {}
    for metrica, resuelta in metricas:
        tabla, expresion = _elegir_tabla(capa, spec, metrica, resuelta, dimensiones)
        grupos.setdefault(tabla.name, []).append((metrica, resuelta, expresion))
    for nombre_tabla, grupo in grupos.items():
        nombre = CONSULTA_PRINCIPAL if len(grupos) == 1 else f"{CONSULTA_PRINCIPAL}:{nombre_tabla}"
        consultas.append(
            _consulta(
                capa, spec, nombre, dw.tabla(nombre_tabla), grupo, dimensiones, spec.nivel, params, sal, limite_filas
            )
        )

    if metodo == "chi_cuadrado":
        consultas.append(_consulta_prueba(capa, spec, metricas, variables, params, sal, limite_filas))

    canonico = json.dumps(
        [{"nombre": c.nombre, "sql": c.sql, "parametros": _serializable(c.parametros)} for c in consultas],
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    huella = hashlib.sha256(canonico.encode("utf-8")).hexdigest()
    return PlanConsulta(consultas=tuple(consultas), limite_filas=limite_filas, huella=huella)


def ejecutar(conexion: Connection, plan: PlanConsulta) -> dict[str, pd.DataFrame]:
    """Ejecuta el plan con la conexión de solo lectura y devuelve un DataFrame por consulta.

    Lanza `LimiteFilasExcedido` si una consulta supera `plan.limite_filas`. El tiempo máximo de ejecución lo
    impone el rol de base de datos (`statement_timeout` en `sql/ana_rpt_postgresql.sql`).
    """
    resultados = {}
    for c in plan.consultas:
        filas = conexion.execute(c.sentencia).fetchall()
        if len(filas) > plan.limite_filas:
            raise LimiteFilasExcedido(f"La consulta '{c.nombre}' supera el límite de {plan.limite_filas} filas.")
        resultados[c.nombre] = pd.DataFrame([tuple(f) for f in filas], columns=list(c.columnas))
    return resultados


def huella_datos(resultados: dict[str, pd.DataFrame]) -> str:
    """SHA-256 (64 hex) de los datos devueltos, independiente del orden de las consultas (contrato: D-15)."""
    h = hashlib.sha256()
    for nombre in sorted(resultados):
        h.update(nombre.encode())
        h.update(resultados[nombre].to_json(orient="split", date_format="iso", double_precision=10).encode())
    return h.hexdigest()


# --- Resolución contra la lista blanca ---------------------------------------------------------------------------


def _metrica(capa: CapaSemantica, codigo: str) -> Metrica:
    m = capa.metrica(codigo)
    if m is None:
        raise ErrorCompilacion(f"métrica fuera de la capa semántica: {codigo!r}")
    return m


def _dimension(capa: CapaSemantica, codigo: str) -> Dimension:
    d = capa.dimension(codigo)
    if d is None:
        raise ErrorCompilacion(f"dimensión fuera de la capa semántica: {codigo!r}")
    if d.identifica_persona:
        raise ErrorCompilacion(f"la dimensión {codigo!r} identifica personas y no se compila")
    return d


def _dimensiones_necesarias(
    capa: CapaSemantica, spec: SpecResuelta, dimensiones: list[DimensionSpec]
) -> list[Dimension]:
    """Dimensiones físicas que la consulta toca: agrupación, filtros y alcance."""
    codigos = [d.id for d in dimensiones] + [f.campo for f in spec.filtros]
    if spec.alcance.rol is Rol.COORDINADOR:
        codigos.append(DIMENSION_ALCANCE_COORDINADOR)
    necesarias = [_dimension(capa, c) for c in dict.fromkeys(codigos)]
    return [d for d in necesarias if d.binaria_de_metrica is None]


def _elegir_tabla(
    capa: CapaSemantica,
    spec: SpecResuelta,
    metrica: Metrica,
    resuelta: MetricaResuelta,
    dimensiones: list[DimensionSpec],
) -> tuple[Table, Expresion]:
    """Hecho base o agregado precalculado. El primer agregado que cubre todo lo que la consulta necesita gana."""
    puede_agregado = (
        spec.nivel is Nivel.AGREGADO
        and resuelta.agregacion in _AGREGACIONES_CON_AGREGADO
        and metrica.columna_personas is None
        and spec.alcance.rol not in HECHOS_POR_ROL
    )
    if puede_agregado:
        necesarias = _dimensiones_necesarias(capa, spec, dimensiones)
        for alterno in metrica.agregados:
            tabla = dw.tabla(alterno.tabla)
            if all(alcanzable(metrica, d, tabla=tabla) for d in necesarias):
                return tabla, alterno.expresion
    return metrica.tabla, metrica.expresion


# --- Construcción del SELECT -------------------------------------------------------------------------------------


class _Constructor:
    """Arma un SELECT sobre un hecho o agregado: une dimensiones bajo demanda y acumula condiciones."""

    def __init__(self, tabla: Table, params: _Parametros) -> None:
        self.tabla = tabla
        self.params = params
        self.origen = tabla
        self.unidas: dict[str, Table] = {}
        self.condiciones: list = []

    def columna_tiempo(self) -> Column:
        return self.tabla.c[self.tabla.info["col_tiempo"]]

    def unir(self, dimension: Table) -> Table:
        if dimension is self.tabla:
            return dimension
        if dimension.name not in self.unidas:
            fk = dw.columna_fk_hacia(self.tabla, dimension)
            if fk is None:
                raise ErrorCompilacion(f"{self.tabla.name} no tiene la dimensión {dimension.name} (matriz de bus)")
            pk = next(iter(dimension.primary_key.columns))
            self.origen = self.origen.outerjoin(dimension, fk == pk)
            self.unidas[dimension.name] = dimension
        return dimension

    def columna_de(self, dimension: Dimension) -> Column:
        return self.unir(dimension.tabla).c[dimension.columna.name]

    def columnas_de_agrupacion(self, capa: CapaSemantica, d: DimensionSpec) -> list[tuple[str, Column]]:
        if d.id == DIMENSION_TIEMPO:
            tiempo = self.unir(dw.dim_tiempo)
            granularidad = d.granularidad or Granularidad.MES
            return [(f"tiempo_{c}", tiempo.c[c]) for c in COLUMNAS_GRANULARIDAD[granularidad]]
        return [(d.id, self.columna_de(_dimension(capa, d.id)))]


def _condicion_filtro(columna: Column, f: Filtro, params: _Parametros, *, es_fecha: bool):
    def valor(v):
        return date.fromisoformat(v) if es_fecha else v

    if f.op is Operador.EN:
        return columna.in_(params.nuevo([valor(v) for v in f.valor], expandir=True))
    if f.op is Operador.ENTRE:
        return columna.between(params.nuevo(valor(f.valor[0])), params.nuevo(valor(f.valor[1])))
    p = params.nuevo(valor(f.valor))
    return {
        Operador.IGUAL: columna == p,
        Operador.DISTINTO: columna != p,
        Operador.MAYOR: columna > p,
        Operador.MAYOR_IGUAL: columna >= p,
        Operador.MENOR: columna < p,
        Operador.MENOR_IGUAL: columna <= p,
    }[f.op]


def _condiciones_de_tiempo(spec: SpecResuelta, columna_tiempo: Column, params: _Parametros) -> list:
    if spec.periodo is not None:
        return [
            columna_tiempo.between(
                params.nuevo(sk_fecha(spec.periodo.desde)), params.nuevo(sk_fecha(spec.periodo.hasta))
            )
        ]
    return [columna_tiempo <= params.nuevo(sk_fecha(spec.corte))]


def _aplicar_filtros_y_alcance(c: _Constructor, capa: CapaSemantica, spec: SpecResuelta, sal: str | None) -> None:
    c.condiciones += _condiciones_de_tiempo(spec, c.columna_tiempo(), c.params)
    for f in spec.filtros:
        dimension = _dimension(capa, f.campo)
        if dimension.binaria_de_metrica:
            raise ErrorCompilacion(f"la dimensión {f.campo!r} no se puede filtrar")
        columna = c.columna_de(dimension)
        c.condiciones.append(_condicion_filtro(columna, f, c.params, es_fecha=dimension.codigo == DIMENSION_TIEMPO))

    alcance = spec.alcance
    if alcance.rol is Rol.COORDINADOR:
        facultad = _dimension(capa, DIMENSION_ALCANCE_COORDINADOR)
        c.condiciones.append(c.columna_de(facultad) == c.params.nuevo(alcance.facultad))
    elif alcance.rol in HECHOS_POR_ROL:
        if c.tabla.name not in HECHOS_POR_ROL[alcance.rol]:
            raise ErrorCompilacion(f"el rol {alcance.rol.value} no puede consultar {c.tabla.name}")
        if not sal:
            raise ErrorCompilacion("falta la sal de seudonimización para aplicar el alcance del usuario")
        persona = c.unir(dw.dim_persona_rol)
        c.condiciones.append(persona.c.seudonimo == c.params.nuevo(seudonimizar(alcance.id_usuario, sal)))


def _ultimo_corte(c: _Constructor, capa: CapaSemantica, spec: SpecResuelta, dimensiones: list[DimensionSpec]):
    """Instantánea periódica: condición que deja solo el último corte de cada periodo de la agrupación temporal."""
    hecho = c.tabla.alias("cortes")
    tiempo = dw.dim_tiempo.alias("cortes_tiempo")
    col = hecho.c[c.tabla.info["col_tiempo"]]
    condiciones = _condiciones_de_tiempo(spec, col, c.params)
    for f in spec.filtros:
        dimension = _dimension(capa, f.campo)
        if dimension.es_temporal:
            condiciones.append(
                _condicion_filtro(
                    tiempo.c[dimension.columna.name], f, c.params, es_fecha=dimension.codigo == DIMENSION_TIEMPO
                )
            )
    periodos: list[Column] = []
    for d in dimensiones:
        if d.id == DIMENSION_TIEMPO:
            periodos += [tiempo.c[x] for x in COLUMNAS_GRANULARIDAD[d.granularidad or Granularidad.MES]]
        elif _dimension(capa, d.id).es_temporal:
            periodos.append(tiempo.c[_dimension(capa, d.id).columna.name])
    sub = select(func.max(col)).select_from(hecho.join(tiempo, col == tiempo.c.sk_fecha)).where(and_(*condiciones))
    if periodos:
        return c.columna_tiempo().in_(sub.group_by(*periodos))
    return c.columna_tiempo() == sub.scalar_subquery()


def _a_decimal(expresion):
    return cast(expresion, Float)


def _columnas_de_metrica(c: _Constructor, metrica: Metrica, resuelta: MetricaResuelta, e: Expresion, nivel: Nivel):
    """Lista de (etiqueta, expresión SQL) de una métrica."""
    t = c.tabla.c
    codigo = metrica.codigo
    if nivel is Nivel.REGISTRO:
        if e.tipo == "conteo":
            raise ErrorCompilacion(f"la métrica {codigo!r} es un conteo y no se lee registro a registro")
        if e.tipo == "columna":
            return [(codigo, _a_decimal(t[e.columna]))]
        num = _a_decimal(t[e.numerador])
        if e.denominador is None:
            return [(codigo, num * c.params.nuevo(e.factor))]
        den = _a_decimal(t[e.denominador])
        return [
            (codigo, num * c.params.nuevo(e.factor) / func.nullif(den, c.params.nuevo(0), type_=Float)),
            (codigo + SUFIJO_NUM, num),
            (codigo + SUFIJO_DEN, den),
        ]

    usa_agregado = c.tabla is not metrica.tabla
    if e.tipo == "conteo":
        return [(codigo, func.count())]
    if e.tipo == "columna":
        if resuelta.agregacion is Agregacion.PROMEDIO:
            return [(codigo, _a_decimal(func.avg(t[e.columna])))]
        if resuelta.agregacion in (Agregacion.SUMA, Agregacion.CONTEO) and (
            resuelta.agregacion is Agregacion.SUMA or usa_agregado
        ):
            # En un agregado precalculado, el conteo del hecho base es la suma de su columna de conteo.
            return [(codigo, _a_decimal(func.sum(t[e.columna])))]
        raise ErrorCompilacion(f"agregación {resuelta.agregacion!r} no compilable para {codigo!r} en nivel agregado")
    num = _a_decimal(func.sum(t[e.numerador]))
    den = _a_decimal(func.count()) if e.denominador is None else _a_decimal(func.sum(t[e.denominador]))
    return [
        (codigo, num * c.params.nuevo(e.factor) / func.nullif(den, c.params.nuevo(0), type_=Float)),
        (codigo + SUFIJO_NUM, num),
        (codigo + SUFIJO_DEN, den),
    ]


def _consulta(
    capa: CapaSemantica,
    spec: SpecResuelta,
    nombre: str,
    tabla: Table,
    grupo: list[tuple[Metrica, MetricaResuelta, Expresion]],
    dimensiones: list[DimensionSpec],
    nivel: Nivel,
    params: _Parametros,
    sal: str | None,
    limite_filas: int,
) -> Consulta:
    c = _Constructor(tabla, params)

    seleccion: list[tuple[str, object]] = []
    agrupacion: list[Column] = []
    for d in dimensiones:
        for etiqueta, columna in c.columnas_de_agrupacion(capa, d):
            seleccion.append((etiqueta, columna))
            agrupacion.append(columna)

    for metrica, resuelta, expresion in grupo:
        seleccion += _columnas_de_metrica(c, metrica, resuelta, expresion, nivel)

    con_personas = next((m.columna_personas for m, _, _ in grupo if m.columna_personas and m.tabla is tabla), None)
    orden: list = list(agrupacion)
    if nivel is Nivel.REGISTRO:
        grano = [tabla.c[g] for g in tabla.info["grano"]]
        if len(grano) == 1:
            seleccion.append((COL_REGISTRO, grano[0]))
        if con_personas:
            seleccion.append((COL_PERSONA, tabla.c[con_personas]))
        orden += [tabla.c[tabla.info["col_tiempo"]], *grano]
    elif con_personas:
        seleccion.append((COL_N_PERSONAS, func.count(tabla.c[con_personas].distinct())))

    _aplicar_filtros_y_alcance(c, capa, spec, sal)
    if tabla.info["tipo"] == dw.INSTANTANEA_PERIODICA:
        c.condiciones.append(_ultimo_corte(c, capa, spec, dimensiones))

    sentencia = select(*[expresion.label(etiqueta) for etiqueta, expresion in seleccion]).select_from(c.origen)
    sentencia = sentencia.where(and_(*c.condiciones))
    if nivel is Nivel.AGREGADO and agrupacion:
        sentencia = sentencia.group_by(*agrupacion)
    sentencia = sentencia.order_by(*orden).limit(params.nuevo(limite_filas + 1))

    compilada = sentencia.compile(dialect=DefaultDialect(), compile_kwargs={"render_postcompile": True})
    return Consulta(
        nombre=nombre,
        tabla=tabla.name,
        sentencia=sentencia,
        sql=str(compilada),
        parametros=dict(compilada.params),
        columnas=tuple(etiqueta for etiqueta, _ in seleccion),
        metricas=tuple(m.codigo for m, _, _ in grupo),
        usa_agregado=tabla.info["tipo"] == dw.AGREGADO or "agregado_de" in tabla.info,
    )


def _consulta_prueba(
    capa: CapaSemantica,
    spec: SpecResuelta,
    metricas: list[tuple[Metrica, MetricaResuelta]],
    variables: list[str],
    params: _Parametros,
    sal: str | None,
    limite_filas: int,
) -> Consulta:
    """Tabla de contingencia del chi-cuadrado (D-06): agrupa por `analisis.variables`, no por `dimensiones`.

    Con una dimensión binaria derivada de una razón (D-19), se agrupa por la otra variable y la tabla se arma
    con los componentes de la razón: (num, den - num).
    """
    dims = [capa.dimension(v) for v in variables]
    if any(d is None for d in dims):
        raise ErrorCompilacion("el chi-cuadrado necesita dos dimensiones de la capa semántica")
    binaria = next((d for d in dims if d.binaria_de_metrica), None)
    if binaria is not None:
        metrica, resuelta = next(((m, r) for m, r in metricas if m.codigo == binaria.binaria_de_metrica), (None, None))
        if metrica is None:
            raise ErrorCompilacion(f"la dimensión {binaria.codigo!r} exige la métrica {binaria.binaria_de_metrica!r}")
        agrupar = [DimensionSpec(id=d.codigo) for d in dims if d is not binaria]
    else:
        metrica, resuelta = metricas[0]
        agrupar = [DimensionSpec(id=d.codigo) for d in dims]
    tabla, expresion = _elegir_tabla(capa, spec, metrica, resuelta, agrupar)
    grupo = [(metrica, resuelta, expresion)]
    return _consulta(capa, spec, CONSULTA_PRUEBA, tabla, grupo, agrupar, Nivel.AGREGADO, params, sal, limite_filas)
