"""ETL nocturno: extracción incremental, seudonimización y carga del esquema `ana_` (sección 4.3.2, OE4).

Orden: dimensiones -> hechos -> agregados (los hechos necesitan las claves sustitutas). Programación con
APScheduler en horario de baja actividad (RNF-04). Cada ejecución se registra en `ana_.etl_ejecucion`.
Pruebas: `tests/etl/test_carga.py` (unitarias) y `tests/etl/test_integracion.py` (fuente sintética en SQLite).

Decisiones que la carga debe respetar (docs/decisiones.md):
  D-09  dim_tiempo se genera con `dw.tiempo.filas_dim_tiempo` (2015–2030).
  D-10  dim_macroproyecto es SCD tipo 2: si cambia `estado` o el coordinador, se cierra la fila vigente
        (`vigente_hasta`) y se inserta otra. La fila vigente tiene `vigente_hasta` nulo.
  D-11  hecho_proyecto: `n_hitos`, `n_hitos_atrasados` (hito no entregado con fecha planeada anterior al
        corte, o entregado después de lo planeado) y `dias_retraso_promedio` salen de `hito_entregable`.
  D-12  hecho_consultoria.sk_persona = consultor con rol 'lider'; `n_consultores` cuenta a todos.
  D-13  dim_linea_programa lleva una fila de nivel programa (línea 'No aplica') por programa;
        hecho_practica.sk_linea apunta a ella.
  D-14  hecho_practica.sk_persona = tutor académico.
  D-17  incremental por `fecha_modificacion` si la vista la tiene; si no, por huella de fila.
  D-18  instantáneas periódicas: un corte por fin de mes (`sk_fecha_corte` = último día del mes). Los
        agregados se recalculan desde los hechos cargados: `agg_proyecto_linea_mes` debe coincidir con
        `hecho_proyecto`; `agg_facturacion_mes` usa el primer día del mes de la factura.
  D-25  cómo se aplica D-17 a cada tipo de hecho y por qué `agg_facturacion_mes` se carga con los hechos.
  Tabla 13: ids de personas -> `seudonimo.seudonimizar`; NIT -> `seudonimo.hash_nit`; nunca en claro.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
from sqlalchemy import Connection, Table, delete, func, insert, select, update

from ciumb_analitica.dw import esquema as dw
from ciumb_analitica.dw.tiempo import (
    ANIO_FINAL,
    ANIO_INICIAL,
    filas_dim_tiempo,
    fin_de_mes,
    sk_fecha,
    ultimo_mes_cerrado,
)
from ciumb_analitica.etl import calidad
from ciumb_analitica.fuentes import vistas
from ciumb_analitica.seudonimo import hash_nit, seudonimizar

MODO_FECHA = "fecha_modificacion"
MODO_HUELLA = "huella_fila"
MODO_COMPLETA = "completa"

SIN_ESTADO = "sin_estado"
SIN_NOMBRE = "Sin nombre"
LINEA_NO_APLICA = "No aplica"
LOTE = 500
"""Tamaño de lote para `IN (...)` e inserciones (SQLite admite pocos parámetros por sentencia)."""

MODULOS: dict[str, str] = {
    "macroproyecto": "macroproyectos",
    "proyecto_investigacion": "investigacion",
    "hito_entregable": "hitos",
    "practica": "practicas",
    "convenio": "convenios",
    "consultoria": "consultorias",
    "usuario": "usuarios",
    "empresa": "empresas",
}
"""Entidad de la fuente -> `dim_estado.modulo` (catálogo unificado de estados de los módulos)."""

ESTADOS_FINALES: dict[str, frozenset[str]] = {
    "macroproyectos": frozenset({"cerrado"}),
    "investigacion": frozenset({"finalizado", "cancelado"}),
    "hitos": frozenset({"entregado"}),
    "practicas": frozenset({"finalizada", "cancelada"}),
    "convenios": frozenset({"vencido", "terminado"}),
    "consultorias": frozenset({"finalizada", "cancelada"}),
    "usuarios": frozenset({"inactivo"}),
    "empresas": frozenset({"inactiva"}),
}


@dataclass(frozen=True)
class ResumenCarga:
    """Fila de `ana_.etl_ejecucion`."""

    tabla_destino: str
    modo: str
    filas_leidas: int
    filas_cargadas: int
    filas_marcadas: int
    inicio: datetime
    fin: datetime
    error: str | None = None


# --- Huella de fila y detección de cambios (D-17) ------------------------------------------------------------


def _vacio(valor) -> bool:
    if valor is None or valor is pd.NaT or valor is pd.NA:
        return True
    return isinstance(valor, float | np.floating) and math.isnan(valor)


def _normalizar(valor) -> list:
    """Valor -> [tipo, texto] canónico. El tipo distingue nulo, texto, número, booleano y fecha."""
    if _vacio(valor):
        return ["n", None]
    if isinstance(valor, bool | np.bool_):
        return ["b", bool(valor)]
    if isinstance(valor, int | np.integer | float | np.floating | Decimal):
        decimal = Decimal(str(valor)) if not isinstance(valor, Decimal) else valor
        texto = format(decimal.normalize(), "f")
        return ["d", "0" if texto in ("-0", "0") else texto]
    if isinstance(valor, pd.Timestamp):
        valor = valor.to_pydatetime()
    if isinstance(valor, datetime):
        return ["t", valor.isoformat()]
    if isinstance(valor, date):
        return ["f", valor.isoformat()]
    return ["s", str(valor)]


def huella_fila(fila: dict) -> str:
    """SHA-256 (64 hex) del contenido de una fila de origen, independiente del orden de las claves.

    Fechas en ISO, decimales normalizados (1.50 y 1.5 dan la misma huella) y nulos distinguibles de la cadena
    vacía. Se usa para detectar cambios cuando la tabla no tiene fecha de modificación (D-17).
    """
    canonico = json.dumps(
        [[str(k), *_normalizar(v)] for k, v in sorted(fila.items(), key=lambda kv: str(kv[0]))],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def filas_cambiadas(filas: pd.DataFrame, columna_id: str, huellas_previas: dict[int, str]) -> pd.DataFrame:
    """Filas nuevas o modificadas respecto de la carga anterior.

    Entradas: filas extraídas; `huellas_previas`: id de origen -> huella guardada en `etl_huella_fila`.
    Salida: subconjunto de `filas` cuyo id no está en `huellas_previas` o cuya huella cambió, con una columna
    adicional `_huella`. No detecta borrados (la fuente no borra: cambia el estado).
    """
    columnas = [c for c in filas.columns if not str(c).startswith("_")]
    huellas = [huella_fila(dict(zip(columnas, fila, strict=True))) for fila in filas[columnas].itertuples(index=False)]
    salida = filas.assign(_huella=huellas)
    cambio = [huellas_previas.get(int(i)) != h for i, h in zip(salida[columna_id].tolist(), huellas, strict=True)]
    return salida[cambio]


# --- Utilidades de lectura y escritura ---------------------------------------------------------------------------


def _limpio(valor):
    """Valor de pandas/NumPy -> valor nativo para insertar (NaN -> None)."""
    if _vacio(valor):
        return None
    if isinstance(valor, np.bool_):
        return bool(valor)
    if isinstance(valor, np.integer):
        return int(valor)
    if isinstance(valor, np.floating):
        return float(valor)
    if isinstance(valor, pd.Timestamp):
        return valor.to_pydatetime()
    return valor


def _registros(filas: Iterable[dict]) -> list[dict]:
    return [{k: _limpio(v) for k, v in f.items()} for f in filas]


def _leer(origen: Connection, entidad: str, condicion=None) -> pd.DataFrame:
    """Lee una vista de extracción. Columnas como `object` para no convertir enteros con nulos en flotantes."""
    consulta = vistas.vista(entidad)
    if condicion is not None:
        consulta = consulta.where(condicion)
    filas = [dict(f) for f in origen.execute(consulta).mappings()]
    return pd.DataFrame(filas, columns=list(vistas.columnas(entidad)), dtype=object)


def _fecha(valor) -> date | None:
    if _vacio(valor):
        return None
    if isinstance(valor, pd.Timestamp):
        valor = valor.to_pydatetime()
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return date.fromisoformat(str(valor)[:10])


def _sk(valor) -> int | None:
    """Clave de `dim_tiempo` de una fecha; None si no hay fecha o cae fuera de 2015–2030 (D-09)."""
    d = _fecha(valor)
    if d is None or not ANIO_INICIAL <= d.year <= ANIO_FINAL:
        return None
    return sk_fecha(d)


def _entero(valor) -> int | None:
    return None if _vacio(valor) else int(valor)


def _numero(valor) -> float | None:
    return None if _vacio(valor) else float(valor)


def _dias(desde, hasta) -> int | None:
    a, b = _fecha(desde), _fecha(hasta)
    return None if a is None or b is None else (b - a).days


def _lotes(valores: list, tamano: int = LOTE) -> Iterable[list]:
    for i in range(0, len(valores), tamano):
        yield valores[i : i + tamano]


def _insertar(destino: Connection, tabla: Table, filas: list[dict]) -> int:
    for lote in _lotes(filas):
        destino.execute(insert(tabla), lote)
    return len(filas)


def _borrar_ids(destino: Connection, tabla: Table, columna: str, ids: list[int]) -> None:
    for lote in _lotes(ids):
        destino.execute(delete(tabla).where(tabla.c[columna].in_(lote)))


# --- Registro de cada ejecución en `etl_ejecucion` y `etl_marca_calidad` -------------------------------------------


@dataclass
class _Salida:
    """Lo que devuelve la carga de una tabla antes de registrarla."""

    modo: str
    leidas: int = 0
    cargadas: int = 0
    marcas: list[tuple[str, int, str]] = field(default_factory=list)  # (entidad, id_origen, regla)

    def marcadas(self) -> int:
        return len({(e, i) for e, i, _ in self.marcas})


def _ejecutar_tabla(destino: Connection, tabla: str, carga: Callable[[], _Salida]) -> ResumenCarga:
    """Carga una tabla en su propio punto de guardado: si falla, se deshace solo esa tabla y el error queda
    registrado en `etl_ejecucion`."""
    inicio = datetime.now()
    try:
        with destino.begin_nested():
            salida = carga()
            fin = datetime.now()
            resultado = destino.execute(
                insert(dw.etl_ejecucion).values(
                    tabla_destino=tabla,
                    inicio=inicio,
                    fin=fin,
                    modo=salida.modo,
                    filas_leidas=salida.leidas,
                    filas_cargadas=salida.cargadas,
                    filas_marcadas=salida.marcadas(),
                )
            )
            id_ejecucion = resultado.inserted_primary_key[0]
            _insertar(
                destino,
                dw.etl_marca_calidad,
                [{"id_ejecucion": id_ejecucion, "entidad": e, "id_origen": i, "regla": r} for e, i, r in salida.marcas],
            )
        return ResumenCarga(tabla, salida.modo, salida.leidas, salida.cargadas, salida.marcadas(), inicio, fin)
    except Exception as exc:  # noqa: BLE001 - se registra y la ejecución sigue con las tablas independientes
        return _registrar_error(destino, tabla, inicio, f"{type(exc).__name__}: {exc}")


def _registrar_error(destino: Connection, tabla: str, inicio: datetime, error: str) -> ResumenCarga:
    fin = datetime.now()
    error = error[:500]
    destino.execute(
        insert(dw.etl_ejecucion).values(tabla_destino=tabla, inicio=inicio, fin=fin, modo=MODO_COMPLETA, error=error)
    )
    return ResumenCarga(tabla, MODO_COMPLETA, 0, 0, 0, inicio, fin, error)


def _marcas(entidad: str, filas: pd.DataFrame, columna_id: str, catalogo: dict[str, list[str]]):
    """(marca_calidad por fila, lista de marcas para `etl_marca_calidad`)."""
    evaluacion = calidad.evaluar(entidad, filas, catalogo_estados=catalogo)
    marcas_fila = calidad.marca(evaluacion)
    detalle = [
        (entidad, int(filas.at[i, columna_id]), regla)
        for regla in evaluacion.columns
        for i in evaluacion.index[evaluacion[regla].to_numpy(dtype=bool)]
    ]
    return marcas_fila, detalle


# --- Dimensiones ---------------------------------------------------------------------------------------------------


def _cargar_dim_tiempo(destino: Connection) -> _Salida:
    existentes = set(destino.execute(select(dw.dim_tiempo.c.sk_fecha)).scalars())
    todas = filas_dim_tiempo()
    nuevas = [f for f in todas if f["sk_fecha"] not in existentes]
    return _Salida(MODO_COMPLETA, len(todas), _insertar(destino, dw.dim_tiempo, nuevas))


def _cargar_dim_estado(origen: Connection, destino: Connection) -> _Salida:
    observados: set[tuple[str, str]] = set()
    leidas = 0
    for entidad, modulo in MODULOS.items():
        estados = _leer(origen, entidad)["estado"]
        leidas += len(estados)
        observados |= {(modulo, SIN_ESTADO if _vacio(e) else str(e)) for e in estados}
    existentes = {(m, e) for m, e in destino.execute(select(dw.dim_estado.c.modulo, dw.dim_estado.c.estado))}
    nuevas = [
        {"modulo": m, "estado": e, "es_final": int(e in ESTADOS_FINALES.get(m, ()))}
        for m, e in sorted(observados - existentes)
    ]
    return _Salida(MODO_COMPLETA, leidas, _insertar(destino, dw.dim_estado, nuevas))


def _personas(origen: Connection, sal: str) -> list[tuple[str, str, str]]:
    """(seudónimo, rol, tipo de participación) de todas las personas que usan los hechos."""
    personas: set[tuple[str, str, str]] = set()
    practicas = _leer(origen, "practica")
    for id_tutor in practicas["id_tutor_academico"].dropna().unique():
        personas.add((seudonimizar(int(id_tutor), sal), "tutor", "tutor_academico"))
    for fila in _leer(origen, "consultor_consultoria").itertuples(index=False):
        tipo = "lider" if fila.rol == "lider" else "consultor"
        personas.add((seudonimizar(int(fila.id_usuario), sal), "consultor", tipo))
    for id_coordinador in _leer(origen, "macroproyecto")["id_coordinador"].dropna().unique():
        personas.add((seudonimizar(int(id_coordinador), sal), "coordinador", "coordinador"))
    roles = dict(_leer(origen, "rol")[["id_rol", "nombre_rol"]].itertuples(index=False))
    for fila in _leer(origen, "usuario")[["id_usuario", "id_rol"]].itertuples(index=False):
        personas.add((seudonimizar(int(fila.id_usuario), sal), str(roles.get(fila.id_rol, "sin_rol")), "usuario"))
    return sorted(personas)


def _cargar_dim_persona_rol(origen: Connection, destino: Connection, sal: str) -> _Salida:
    personas = _personas(origen, sal)
    t = dw.dim_persona_rol
    existentes = set(destino.execute(select(t.c.seudonimo, t.c.rol, t.c.tipo_participacion)))
    nuevas = [
        {"seudonimo": s, "rol": r, "tipo_participacion": p} for s, r, p in personas if (s, r, p) not in existentes
    ]
    return _Salida(MODO_COMPLETA, len(personas), _insertar(destino, t, nuevas))


def _cargar_dim_linea_programa(origen: Connection, destino: Connection) -> _Salida:
    programas = _leer(origen, "facultad_programa").set_index("id_programa")
    lineas = _leer(origen, "linea_investigacion")
    deseadas: dict[tuple[int | None, int], dict] = {}
    for p, prog in programas.iterrows():
        deseadas[(None, int(p))] = {
            "id_linea_origen": None,
            "id_programa_origen": int(p),
            "linea_investigacion": LINEA_NO_APLICA,
            "programa": prog["nombre_programa"],
            "facultad": prog["facultad"],
        }
    for fila in lineas.itertuples(index=False):
        if _vacio(fila.id_programa) or fila.id_programa not in programas.index:
            continue
        prog = programas.loc[fila.id_programa]
        deseadas[(int(fila.id_linea), int(fila.id_programa))] = {
            "id_linea_origen": int(fila.id_linea),
            "id_programa_origen": int(fila.id_programa),
            "linea_investigacion": fila.nombre,
            "programa": prog["nombre_programa"],
            "facultad": prog["facultad"],
        }
    t = dw.dim_linea_programa
    actuales = {(f.id_linea_origen, f.id_programa_origen): f for f in destino.execute(select(t)).mappings()}
    cargadas = 0
    nuevas = []
    for clave, fila in deseadas.items():
        actual = actuales.get(clave)
        if actual is None:
            nuevas.append(fila)
        elif any(actual[c] != fila[c] for c in ("linea_investigacion", "programa", "facultad")):  # SCD tipo 1
            destino.execute(update(t).where(t.c.sk_linea == actual["sk_linea"]).values(**fila))
            cargadas += 1
    return _Salida(MODO_COMPLETA, len(deseadas), cargadas + _insertar(destino, t, nuevas))


def _mapa_personas(destino: Connection) -> dict[tuple[str, str, str], int]:
    t = dw.dim_persona_rol
    return {(s, r, p): sk for sk, s, r, p in destino.execute(select(t.c.sk_persona, t.c.seudonimo, t.c.rol,
                                                                     t.c.tipo_participacion))}  # fmt: skip


def _cargar_dim_macroproyecto(origen: Connection, destino: Connection, sal: str, hoy: date) -> _Salida:
    """SCD tipo 2 (D-10): un cambio de estado o de coordinador cierra la versión vigente y abre otra. Repetir la
    carga el mismo día corrige la versión abierta hoy en lugar de abrir otra (idempotencia)."""
    t = dw.dim_macroproyecto
    personas = _mapa_personas(destino)
    vigentes = {f.id_origen: f for f in destino.execute(select(t).where(t.c.vigente_hasta.is_(None))).mappings()}
    fuente = _leer(origen, "macroproyecto")
    cargadas = 0
    for fila in fuente.itertuples(index=False):
        coordinador = None
        if not _vacio(fila.id_coordinador):
            coordinador = personas.get((seudonimizar(int(fila.id_coordinador), sal), "coordinador", "coordinador"))
        deseada = {
            "id_origen": int(fila.id_macroproyecto),
            "nombre": fila.nombre if not _vacio(fila.nombre) else SIN_NOMBRE,
            "estado_actual": fila.estado if not _vacio(fila.estado) else SIN_ESTADO,
            "sk_coordinador": coordinador,
        }
        actual = vigentes.get(deseada["id_origen"])
        if actual is None:
            inicio = _fecha(fila.fecha_inicio)
            desde = inicio if inicio is not None and inicio <= hoy else hoy
            destino.execute(insert(t).values(**deseada, vigente_desde=desde, vigente_hasta=None))
            cargadas += 1
            continue
        cambio_scd2 = (actual["estado_actual"], actual["sk_coordinador"]) != (
            deseada["estado_actual"],
            deseada["sk_coordinador"],
        )
        if cambio_scd2 and actual["vigente_desde"] < hoy:
            destino.execute(
                update(t)
                .where(t.c.sk_macroproyecto == actual["sk_macroproyecto"])
                .values(vigente_hasta=hoy - timedelta(days=1))
            )
            destino.execute(insert(t).values(**deseada, vigente_desde=hoy, vigente_hasta=None))
            cargadas += 1
        elif cambio_scd2 or actual["nombre"] != deseada["nombre"]:  # mismo día o solo el nombre: se corrige
            destino.execute(update(t).where(t.c.sk_macroproyecto == actual["sk_macroproyecto"]).values(**deseada))
            cargadas += 1
    return _Salida(MODO_COMPLETA, len(fuente), cargadas)


def _cargar_dim_empresa(origen: Connection, destino: Connection, sal: str) -> _Salida:
    t = dw.dim_empresa
    fuente = _leer(origen, "empresa")
    _, detalle = _marcas("empresa", fuente, "id_empresa", {})
    actuales = {f.id_origen: f for f in destino.execute(select(t)).mappings()}
    cargadas, nuevas = 0, []
    for fila in fuente.itertuples(index=False):
        deseada = {
            "id_origen": int(fila.id_empresa),
            "sector": None if _vacio(fila.sector) else fila.sector,
            "ciudad": None if _vacio(fila.ciudad) else fila.ciudad,
            "tipo": None if _vacio(fila.tipo) else fila.tipo,
            "nit_hash": None if _vacio(fila.nit) else hash_nit(str(fila.nit), sal),
        }
        actual = actuales.get(deseada["id_origen"])
        if actual is None:
            nuevas.append(deseada)
        elif any(actual[c] != deseada[c] for c in ("sector", "ciudad", "tipo", "nit_hash")):  # SCD 1
            destino.execute(update(t).where(t.c.sk_empresa == actual["sk_empresa"]).values(**deseada))
            cargadas += 1
    salida = _Salida(MODO_COMPLETA, len(fuente), cargadas + _insertar(destino, t, nuevas))
    salida.marcas = detalle
    return salida


def _cargar_dim_tipo_convenio(origen: Connection, destino: Connection) -> _Salida:
    t = dw.dim_tipo_convenio
    tipos = {str(x) for x in _leer(origen, "convenio")["tipo"] if not _vacio(x)}
    existentes = set(destino.execute(select(t.c.tipo_convenio)).scalars())
    nuevas = [{"tipo_convenio": x} for x in sorted(tipos - existentes)]
    return _Salida(MODO_COMPLETA, len(tipos), _insertar(destino, t, nuevas))


def cargar_dimensiones(origen: Connection, destino: Connection, *, sal: str, hoy: date) -> list[ResumenCarga]:
    """Carga las siete dimensiones de `ana_` desde las vistas de `fuentes`.

    Entradas: conexión de SOLO LECTURA a la fuente, conexión de escritura a `ana_`, la sal de seudonimización
    y la fecha de ejecución. Idempotente: repetirla el mismo día no duplica filas ni abre versiones SCD nuevas.
    Salida: un `ResumenCarga` por dimensión.
    """
    pasos: list[tuple[str, Callable[[], _Salida]]] = [
        ("dim_tiempo", lambda: _cargar_dim_tiempo(destino)),
        ("dim_estado", lambda: _cargar_dim_estado(origen, destino)),
        ("dim_persona_rol", lambda: _cargar_dim_persona_rol(origen, destino, sal)),
        ("dim_linea_programa", lambda: _cargar_dim_linea_programa(origen, destino)),
        ("dim_macroproyecto", lambda: _cargar_dim_macroproyecto(origen, destino, sal, hoy)),
        ("dim_empresa", lambda: _cargar_dim_empresa(origen, destino, sal)),
        ("dim_tipo_convenio", lambda: _cargar_dim_tipo_convenio(origen, destino)),
    ]
    return [_ejecutar_tabla(destino, nombre, paso) for nombre, paso in pasos]


# --- Hechos --------------------------------------------------------------------------------------------------------


class _Claves:
    """Claves sustitutas ya cargadas, para traducir ids de origen en los hechos."""

    def __init__(self, destino: Connection, sal: str):
        self.sal = sal
        e = dw.dim_estado
        self.estados = {(m, s): sk for sk, m, s in destino.execute(select(e.c.sk_estado, e.c.modulo, e.c.estado))}
        lp = dw.dim_linea_programa
        self.lineas: dict[int, int] = {}
        self.programas: dict[int, int] = {}
        for sk, id_linea, id_programa in destino.execute(
            select(lp.c.sk_linea, lp.c.id_linea_origen, lp.c.id_programa_origen)
        ):
            if id_linea is None:
                self.programas[id_programa] = sk
            else:
                self.lineas[id_linea] = sk
        m = dw.dim_macroproyecto
        self.macros: dict[int, list[tuple[date, date | None, int]]] = {}
        for sk, id_origen, desde, hasta in destino.execute(
            select(m.c.sk_macroproyecto, m.c.id_origen, m.c.vigente_desde, m.c.vigente_hasta)
        ):
            self.macros.setdefault(id_origen, []).append((desde, hasta, sk))
        self.personas = _mapa_personas(destino)
        em = dw.dim_empresa
        self.empresas = dict(destino.execute(select(em.c.id_origen, em.c.sk_empresa)).all())
        tc = dw.dim_tipo_convenio
        self.tipos_convenio = dict(destino.execute(select(tc.c.tipo_convenio, tc.c.sk_tipo_convenio)).all())

    def estado(self, entidad: str, valor) -> int:
        clave = (MODULOS[entidad], SIN_ESTADO if _vacio(valor) else str(valor))
        if clave not in self.estados:
            raise KeyError(f"estado {clave} sin fila en dim_estado: cargue antes las dimensiones")
        return self.estados[clave]

    def macroproyecto(self, id_origen, en: date) -> int | None:
        """Versión de la dimensión vigente en la fecha `en`; si no hay, la más reciente."""
        if _vacio(id_origen):
            return None
        versiones = sorted(self.macros.get(int(id_origen), []))
        for desde, hasta, sk in versiones:
            if desde <= en and (hasta is None or en <= hasta):
                return sk
        return versiones[-1][2] if versiones else None

    def persona(self, id_origen, rol: str, tipo: str) -> int | None:
        if _vacio(id_origen):
            return None
        return self.personas.get((seudonimizar(int(id_origen), self.sal), rol, tipo))

    def empresa(self, id_origen) -> int | None:
        return None if _vacio(id_origen) else self.empresas.get(int(id_origen))


def _reemplazar_corte(destino: Connection, tabla: Table, corte: date, filas: list[dict]) -> int:
    """Instantánea periódica: borra las filas del corte y las vuelve a insertar (idempotente)."""
    destino.execute(delete(tabla).where(tabla.c.sk_fecha_corte == sk_fecha(corte)))
    return _insertar(destino, tabla, filas)


def _hitos_por_proyecto(hitos: pd.DataFrame, corte: date) -> dict[int, dict]:
    """n_hitos, n_hitos_atrasados y dias_retraso_promedio por proyecto al corte (D-11).

    Cuentan los hitos con fecha planeada hasta el corte. Atrasado: planeado antes del corte y no entregado a la
    fecha del corte, o entregado después de lo planeado. Retraso: días entre lo planeado y la entrega (o el corte).
    """
    resumen: dict[int, dict] = {}
    for fila in hitos.itertuples(index=False):
        planeada = _fecha(fila.fecha_planeada)
        if planeada is None or planeada > corte:
            continue
        real = _fecha(fila.fecha_real)
        entregado_al_corte = real is not None and real <= corte
        atrasado = (planeada < corte and not entregado_al_corte) or (entregado_al_corte and real > planeada)
        r = resumen.setdefault(int(fila.id_proyecto), {"n_hitos": 0, "n_hitos_atrasados": 0, "_retrasos": []})
        r["n_hitos"] += 1
        if atrasado:
            r["n_hitos_atrasados"] += 1
            r["_retrasos"].append(((real if entregado_al_corte else corte) - planeada).days)
    for r in resumen.values():
        retrasos = r.pop("_retrasos")
        r["dias_retraso_promedio"] = round(sum(retrasos) / len(retrasos), 2) if retrasos else None
    return resumen


def _hecho_proyecto(origen, destino, claves: _Claves, corte: date, catalogo) -> _Salida:
    proyectos = _leer(origen, "proyecto_investigacion")
    proyectos = proyectos[[(_fecha(f) is None or _fecha(f) <= corte) for f in proyectos["fecha_creacion"]]]
    proyectos = proyectos.reset_index(drop=True)
    marcas, detalle = _marcas("proyecto_investigacion", proyectos, "id_proyecto", catalogo)
    hitos = _hitos_por_proyecto(_leer(origen, "hito_entregable"), corte)
    integrantes = _leer(origen, "integrante_proyecto")["id_proyecto"].value_counts().to_dict()
    filas = []
    for i, p in proyectos.iterrows():
        asignado, ejecutado = _numero(p["presupuesto_asignado"]), _numero(p["presupuesto_ejecutado"])
        h = hitos.get(int(p["id_proyecto"]), {"n_hitos": 0, "n_hitos_atrasados": 0, "dias_retraso_promedio": None})
        filas.append(
            {
                "sk_fecha_corte": sk_fecha(corte),
                "id_proyecto": int(p["id_proyecto"]),
                "sk_macroproyecto": claves.macroproyecto(p["id_macroproyecto"], corte),
                "sk_linea": None if _vacio(p["id_linea"]) else claves.lineas.get(int(p["id_linea"])),
                "sk_estado": claves.estado("proyecto_investigacion", p["estado"]),
                "presupuesto_asignado": asignado,
                "presupuesto_ejecutado": ejecutado,
                "pct_ejecucion": round(100 * ejecutado / asignado, 2) if asignado and ejecutado is not None else None,
                "n_integrantes": int(integrantes.get(p["id_proyecto"], 0)),
                **h,
                "dias_creacion_aprobacion": _dias(p["fecha_creacion"], p["fecha_aprobacion"]),
                "marca_calidad": marcas.at[i],
            }
        )
    salida = _Salida(MODO_COMPLETA, len(proyectos), _reemplazar_corte(destino, dw.hecho_proyecto, corte, filas))
    salida.marcas = detalle
    return salida


def _hecho_macroproyecto(origen, destino, claves: _Claves, corte: date) -> _Salida:
    macros = _leer(origen, "macroproyecto")
    proyectos = _leer(origen, "proyecto_investigacion")
    practicas = _leer(origen, "practica")
    n_proyectos = proyectos[[(_fecha(f) is None or _fecha(f) <= corte) for f in proyectos["fecha_creacion"]]]
    n_proyectos = n_proyectos["id_macroproyecto"].dropna().map(int).value_counts().to_dict()
    n_practicas = practicas[[(_fecha(f) is not None and _fecha(f) <= corte) for f in practicas["fecha_inicio"]]]
    n_practicas = n_practicas["id_macroproyecto"].dropna().map(int).value_counts().to_dict()
    filas = []
    for m in macros.itertuples(index=False):
        inicio = _fecha(m.fecha_inicio)
        if inicio is not None and inicio > corte:
            continue
        sk_macro = claves.macroproyecto(m.id_macroproyecto, corte)
        if sk_macro is None:
            continue
        planeada, real = _fecha(m.fecha_fin_planeada), _fecha(m.fecha_fin_real)
        if planeada is None:
            desviacion = None
        elif real is not None and real <= corte:
            desviacion = (real - planeada).days
        else:
            desviacion = max(0, (corte - planeada).days)
        filas.append(
            {
                "sk_fecha_corte": sk_fecha(corte),
                "sk_macroproyecto": sk_macro,
                "sk_estado": claves.estado("macroproyecto", m.estado),
                "pct_avance": _numero(m.porcentaje_avance),
                "desviacion_dias": desviacion,
                "n_proyectos": int(n_proyectos.get(int(m.id_macroproyecto), 0)),
                "n_practicas": int(n_practicas.get(int(m.id_macroproyecto), 0)),
                "marca_calidad": None,
            }
        )
    return _Salida(MODO_COMPLETA, len(macros), _reemplazar_corte(destino, dw.hecho_macroproyecto, corte, filas))


def _hecho_convenio(origen, destino, claves: _Claves, corte: date, catalogo) -> _Salida:
    convenios = _leer(origen, "convenio")
    vigentes_al_corte = [
        (_fecha(f) or _fecha(i)) is None or (_fecha(f) or _fecha(i)) <= corte
        for f, i in zip(convenios["fecha_firma"], convenios["fecha_inicio"], strict=True)
    ]
    convenios = convenios[vigentes_al_corte].reset_index(drop=True)
    marcas, detalle = _marcas("convenio", convenios, "id_convenio", catalogo)
    renovados = {int(x) for x in convenios["id_convenio_anterior"].dropna()}
    documentos = _leer(origen, "documento_convenio")
    completos = {
        int(k): int(len(g) > 0 and all(bool(x) for x in g["cargado"])) for k, g in documentos.groupby("id_convenio")
    }
    practicas = _leer(origen, "practica")
    consultorias = _leer(origen, "consultoria")
    actividades: dict[int, int] = {}
    for tabla in (practicas, consultorias):
        al_corte = tabla[[(_fecha(f) is not None and _fecha(f) <= corte) for f in tabla["fecha_inicio"]]]
        for k, n in al_corte["id_convenio"].dropna().map(int).value_counts().items():
            actividades[k] = actividades.get(k, 0) + int(n)
    filas = []
    for i, c in convenios.iterrows():
        sk_empresa = claves.empresa(c["id_empresa"])
        sk_tipo = claves.tipos_convenio.get(c["tipo"]) if not _vacio(c["tipo"]) else None
        if sk_empresa is None or sk_tipo is None:
            continue  # claves obligatorias del hecho; el convenio queda fuera y se ve en filas_leidas - cargadas
        fin = _fecha(c["fecha_fin"])
        filas.append(
            {
                "sk_fecha_corte": sk_fecha(corte),
                "id_convenio": int(c["id_convenio"]),
                "sk_estado": claves.estado("convenio", c["estado"]),
                "sk_empresa": sk_empresa,
                "sk_tipo_convenio": sk_tipo,
                "duracion_dias": _dias(c["fecha_inicio"], c["fecha_fin"]),
                "dias_para_vencer": None if fin is None else (fin - corte).days,
                "renovado": int(int(c["id_convenio"]) in renovados),
                "docs_completos": completos.get(int(c["id_convenio"]), 0),
                "n_actividades": actividades.get(int(c["id_convenio"]), 0),
                "marca_calidad": marcas.at[i],
            }
        )
    salida = _Salida(MODO_COMPLETA, len(convenios), _reemplazar_corte(destino, dw.hecho_convenio, corte, filas))
    salida.marcas = detalle
    return salida


def _huellas_previas(destino: Connection, entidad: str) -> dict[int, str]:
    h = dw.etl_huella_fila
    return dict(destino.execute(select(h.c.id_origen, h.c.huella).where(h.c.entidad == entidad)).all())


def _upsert_por_huella(destino: Connection, tabla: Table, columna_id: str, entidad: str, filas: list[dict]) -> int:
    """Carga incremental por huella (D-17): solo inserta las filas nuevas o cambiadas y guarda su huella."""
    if not filas:
        return 0
    marco = pd.DataFrame(filas, dtype=object)
    cambiadas = filas_cambiadas(marco, columna_id, _huellas_previas(destino, entidad))
    if cambiadas.empty:
        return 0
    ids = [int(x) for x in cambiadas[columna_id]]
    _borrar_ids(destino, tabla, columna_id, ids)
    _insertar(destino, tabla, _registros(cambiadas.drop(columns="_huella").to_dict("records")))
    h = dw.etl_huella_fila
    for lote in _lotes(ids):
        destino.execute(delete(h).where(h.c.entidad == entidad, h.c.id_origen.in_(lote)))
    _insertar(
        destino,
        h,
        [{"entidad": entidad, "id_origen": i, "huella": x} for i, x in zip(ids, cambiadas["_huella"], strict=True)],
    )
    return len(ids)


def _hecho_hito(origen, destino, claves: _Claves, corte: date) -> _Salida:
    hitos = _leer(origen, "hito_entregable")
    filas = []
    for h in hitos.itertuples(index=False):
        planeada = _fecha(h.fecha_planeada)
        if _sk(planeada) is None:
            continue  # sin fecha planeada no hay clave de tiempo (columna obligatoria)
        real = _fecha(h.fecha_real)
        if real is not None and real <= corte:
            retraso = max(0, (real - planeada).days)
        else:
            retraso = max(0, (corte - planeada).days)
        filas.append(
            {
                "id_hito": int(h.id_hito),
                "id_proyecto": int(h.id_proyecto),
                "sk_fecha_planeada": _sk(planeada),
                "sk_estado": claves.estado("hito_entregable", h.estado),
                "dias_retraso": retraso,
                "a_tiempo": int(real is not None and real <= corte and real <= planeada),
                "marca_calidad": None,
            }
        )
    return _Salida(
        MODO_HUELLA, len(hitos), _upsert_por_huella(destino, dw.hecho_hito, "id_hito", "hito_entregable", filas)
    )


def _ultima_carga_exitosa(destino: Connection, tabla: str) -> datetime | None:
    e = dw.etl_ejecucion
    return destino.execute(select(func.max(e.c.inicio)).where(e.c.tabla_destino == tabla, e.c.error.is_(None))).scalar()


def _hecho_practica(origen, destino, claves: _Claves, corte: date, catalogo) -> _Salida:
    """Instantánea acumulativa con carga incremental por `fecha_modificacion` (D-17)."""
    ultima = _ultima_carga_exitosa(destino, "hecho_practica")
    condicion = None
    if ultima is not None:
        condicion = vistas.tabla_fuente("practica").c.fecha_modificacion > ultima
    practicas = _leer(origen, "practica", condicion).reset_index(drop=True)
    marcas, detalle = _marcas("practica", practicas, "id_practica", catalogo)
    filas = []
    for i, p in practicas.iterrows():
        sk_inicio = _sk(p["fecha_inicio"])
        if sk_inicio is None:
            continue
        inicio = _fecha(p["fecha_inicio"])
        filas.append(
            {
                "id_practica": int(p["id_practica"]),
                "sk_fecha": sk_inicio,
                "sk_macroproyecto": claves.macroproyecto(p["id_macroproyecto"], inicio),
                "sk_linea": None if _vacio(p["id_programa"]) else claves.programas.get(int(p["id_programa"])),
                "sk_estado": claves.estado("practica", p["estado"]),
                "sk_persona": claves.persona(p["id_tutor_academico"], "tutor", "tutor_academico"),
                "sk_empresa": claves.empresa(p["id_empresa"]),
                "seudonimo_estudiante": None
                if _vacio(p["id_estudiante"])
                else seudonimizar(int(p["id_estudiante"]), claves.sal),
                "duracion_dias": _dias(p["fecha_inicio"], p["fecha_fin"]),
                "tareas_asignadas": _entero(p["tareas_asignadas"]),
                "tareas_cumplidas": _entero(p["tareas_cumplidas"]),
                "finalizada": int(p["estado"] == "finalizada"),
                "marca_calidad": marcas.at[i],
            }
        )
    _borrar_ids(destino, dw.hecho_practica, "id_practica", [f["id_practica"] for f in filas])
    salida = _Salida(MODO_FECHA, len(practicas), _insertar(destino, dw.hecho_practica, filas))
    salida.marcas = detalle
    return salida


def _hecho_consultoria(origen, destino, claves: _Claves, corte: date) -> _Salida:
    consultorias = _leer(origen, "consultoria")
    facturas = _leer(origen, "factura_consultoria")
    facturas = facturas[[(_fecha(f) is not None and _fecha(f) <= corte) for f in facturas["fecha_factura"]]]
    facturado = facturas.groupby("id_consultoria")["valor"].apply(lambda v: float(sum(Decimal(str(x)) for x in v)))
    equipo = _leer(origen, "consultor_consultoria")
    n_consultores = equipo["id_consultoria"].value_counts().to_dict()
    lideres = {int(f.id_consultoria): f.id_usuario for f in equipo.itertuples(index=False) if f.rol == "lider"}
    filas = []
    for c in consultorias.itertuples(index=False):
        sk_inicio, sk_empresa = _sk(c.fecha_inicio), claves.empresa(c.id_empresa)
        if sk_inicio is None or sk_empresa is None:
            continue
        filas.append(
            {
                "id_consultoria": int(c.id_consultoria),
                "sk_fecha": sk_inicio,
                "sk_estado": claves.estado("consultoria", c.estado),
                "sk_persona": claves.persona(lideres.get(int(c.id_consultoria)), "consultor", "lider"),
                "sk_empresa": sk_empresa,
                "valor_facturado": round(float(facturado.get(c.id_consultoria, 0.0)), 2),
                "satisfaccion": _numero(c.calificacion_satisfaccion),
                "n_consultores": int(n_consultores.get(c.id_consultoria, 0)),
                "duracion_dias": _dias(c.fecha_inicio, c.fecha_fin),
                "marca_calidad": None,
            }
        )
    cargadas = _upsert_por_huella(destino, dw.hecho_consultoria, "id_consultoria", "consultoria", filas)
    return _Salida(MODO_HUELLA, len(consultorias), cargadas)


def _hecho_acceso_diario(origen, destino, claves: _Claves, corte: date) -> _Salida:
    """Transacción agregada por día y usuario. Se recalcula completa hasta el corte (los accesos no cambian)."""
    accesos = _leer(origen, "registro_acceso")
    usuarios = _leer(origen, "usuario")
    roles = dict(_leer(origen, "rol")[["id_rol", "nombre_rol"]].itertuples(index=False))
    rol_usuario = {int(u.id_usuario): str(roles.get(u.id_rol, "sin_rol")) for u in usuarios.itertuples(index=False)}
    conteos: dict[tuple[int, int], list[int]] = {}
    for a in accesos.itertuples(index=False):
        dia = _fecha(a.fecha_hora)
        sk_dia = _sk(dia)
        if sk_dia is None or dia > corte:
            continue
        sk_persona = claves.persona(a.id_usuario, rol_usuario.get(int(a.id_usuario), "sin_rol"), "usuario")
        if sk_persona is None:
            continue
        c = conteos.setdefault((sk_dia, sk_persona), [0, 0, 0])
        c[0] += 1
        c[1] += int(not bool(a.exitoso))
        c[2] += int(bool(a.bloqueo_generado))
    filas = [
        {"sk_fecha": d, "sk_persona": p, "n_accesos": n, "n_fallidos": f, "bloqueos": b}
        for (d, p), (n, f, b) in sorted(conteos.items())
    ]
    destino.execute(delete(dw.hecho_acceso_diario).where(dw.hecho_acceso_diario.c.sk_fecha <= sk_fecha(corte)))
    return _Salida(MODO_COMPLETA, len(accesos), _insertar(destino, dw.hecho_acceso_diario, filas))


def _agg_facturacion_mes(origen, destino, claves: _Claves, corte: date) -> _Salida:
    """Facturación por mes de la factura (primer día del mes) y empresa, completa hasta el corte (D-18, D-25).

    Se carga con los hechos porque sale de `factura_consultoria`, que no tiene hecho propio en `ana_`."""
    facturas = _leer(origen, "factura_consultoria")
    empresa_de = {int(c.id_consultoria): c.id_empresa for c in _leer(origen, "consultoria").itertuples(index=False)}
    grupos: dict[tuple[int, int], list] = {}
    for f in facturas.itertuples(index=False):
        dia = _fecha(f.fecha_factura)
        if dia is None or dia > corte:
            continue
        sk_mes = _sk(dia.replace(day=1))
        sk_empresa = claves.empresa(empresa_de.get(int(f.id_consultoria)))
        if sk_mes is None or sk_empresa is None:
            continue
        g = grupos.setdefault((sk_mes, sk_empresa), [Decimal(0), 0])
        g[0] += Decimal(str(f.valor or 0))
        g[1] += 1
    filas = [
        {"sk_fecha": m, "sk_empresa": e, "valor_facturado": float(v), "n_facturas": n}
        for (m, e), (v, n) in sorted(grupos.items())
    ]
    destino.execute(delete(dw.agg_facturacion_mes))
    return _Salida(MODO_COMPLETA, len(facturas), _insertar(destino, dw.agg_facturacion_mes, filas))


def _pasos_hechos(origen, destino, sal, corte, catalogo) -> list[tuple[str, Callable[[], _Salida]]]:
    claves: list[_Claves] = []

    def c() -> _Claves:  # se leen una vez, después de las dimensiones
        if not claves:
            claves.append(_Claves(destino, sal))
        return claves[0]

    return [
        ("hecho_macroproyecto", lambda: _hecho_macroproyecto(origen, destino, c(), corte)),
        ("hecho_proyecto", lambda: _hecho_proyecto(origen, destino, c(), corte, catalogo)),
        ("hecho_hito", lambda: _hecho_hito(origen, destino, c(), corte)),
        ("hecho_practica", lambda: _hecho_practica(origen, destino, c(), corte, catalogo)),
        ("hecho_convenio", lambda: _hecho_convenio(origen, destino, c(), corte, catalogo)),
        ("hecho_consultoria", lambda: _hecho_consultoria(origen, destino, c(), corte)),
        ("hecho_acceso_diario", lambda: _hecho_acceso_diario(origen, destino, c(), corte)),
        ("agg_facturacion_mes", lambda: _agg_facturacion_mes(origen, destino, c(), corte)),
    ]


def cargar_hechos(
    origen: Connection, destino: Connection, *, sal: str, corte: date, catalogo_estados: dict[str, list[str]]
) -> list[ResumenCarga]:
    """Carga los siete hechos para la fecha de corte y registra las marcas de calidad.

    `corte`: último día del mes que se cierra. Las instantáneas periódicas insertan (o reemplazan) las filas
    de ese corte; las acumulativas y de transacción hacen upsert por su id de origen.
    Los registros que fallan una regla se cargan con `marca_calidad` y se cuentan en `filas_marcadas`.
    Un registro cuya dimensión no se encuentra (p. ej. práctica sin empresa) se carga con la clave nula.
    También carga `agg_facturacion_mes`, que sale de las facturas de la fuente (D-25).
    """
    return [
        _ejecutar_tabla(destino, nombre, paso)
        for nombre, paso in _pasos_hechos(origen, destino, sal, corte, catalogo_estados)
    ]


def _agg_proyecto_linea_mes(destino: Connection, corte: date) -> _Salida:
    h, a = dw.hecho_proyecto, dw.agg_proyecto_linea_mes
    consulta = (
        select(
            h.c.sk_linea,
            h.c.sk_estado,
            func.count().label("n_proyectos"),
            func.sum(h.c.presupuesto_asignado).label("presupuesto_asignado"),
            func.sum(h.c.presupuesto_ejecutado).label("presupuesto_ejecutado"),
            func.sum(h.c.n_hitos).label("n_hitos"),
            func.sum(h.c.n_hitos_atrasados).label("n_hitos_atrasados"),
        )
        .where(h.c.sk_fecha_corte == sk_fecha(corte), h.c.sk_linea.is_not(None))
        .group_by(h.c.sk_linea, h.c.sk_estado)
        .order_by(h.c.sk_linea, h.c.sk_estado)
    )
    filas = [dict(f) | {"sk_fecha_corte": sk_fecha(corte)} for f in destino.execute(consulta).mappings()]
    filas = _registros({k: (float(v) if isinstance(v, Decimal) else v) for k, v in f.items()} for f in filas)
    leidas = destino.execute(select(func.count()).select_from(h).where(h.c.sk_fecha_corte == sk_fecha(corte))).scalar()
    return _Salida(MODO_COMPLETA, int(leidas or 0), _reemplazar_corte(destino, a, corte, filas))


def recalcular_agregados(destino: Connection, *, corte: date) -> list[ResumenCarga]:
    """Recalcula `agg_proyecto_linea_mes` para el corte desde `hecho_proyecto` ya cargado.

    `agg_facturacion_mes` se carga en `cargar_hechos` porque sale de las facturas de la fuente, que no tienen
    hecho propio en `ana_` (D-25).
    """
    return [_ejecutar_tabla(destino, "agg_proyecto_linea_mes", lambda: _agg_proyecto_linea_mes(destino, corte))]


def _dependencias(nombre: str) -> set[str]:
    tabla = dw.tabla(nombre)
    return {fk.column.table.name for col in tabla.columns for fk in col.foreign_keys}


def ejecutar_etl(
    origen: Connection, destino: Connection, *, sal: str, hoy: date, catalogo_estados: dict[str, list[str]]
) -> list[ResumenCarga]:
    """Ejecución completa: dimensiones, hechos del último mes cerrado (`dw.tiempo.ultimo_mes_cerrado(hoy)`) y
    agregados, en una transacción por tabla. Si una tabla falla, registra el error en su `ResumenCarga` y
    continúa con las que no dependen de ella. Es la función que programa APScheduler.

    Las tablas se escriben en puntos de guardado dentro de la transacción de `destino`: quien llama confirma
    (p. ej. `with motor.begin() as destino: ejecutar_etl(...)`).
    """
    corte = ultimo_mes_cerrado(hoy)
    resumenes = cargar_dimensiones(origen, destino, sal=sal, hoy=hoy)
    fallidas = {r.tabla_destino for r in resumenes if r.error}
    for nombre, paso in _pasos_hechos(origen, destino, sal, corte, catalogo_estados):
        bloqueo = _dependencias(nombre) & fallidas
        if bloqueo:
            resumenes.append(
                _registrar_error(destino, nombre, datetime.now(), f"omitida: falló {', '.join(sorted(bloqueo))}")
            )
            fallidas.add(nombre)
            continue
        resumen = _ejecutar_tabla(destino, nombre, paso)
        resumenes.append(resumen)
        if resumen.error:
            fallidas.add(nombre)
    if "hecho_proyecto" in fallidas:
        resumenes.append(
            _registrar_error(destino, "agg_proyecto_linea_mes", datetime.now(), "omitida: falló hecho_proyecto")
        )
    else:
        resumenes += recalcular_agregados(destino, corte=corte)
    return resumenes


def cargar_cortes_historicos(
    origen: Connection,
    destino: Connection,
    *,
    sal: str,
    desde: date,
    hasta: date,
    catalogo_estados: dict[str, list[str]],
) -> list[ResumenCarga]:
    """Carga inicial de las instantáneas periódicas: un corte por fin de mes entre `desde` y `hasta` (D-29).

    Las dimensiones deben estar cargadas. Para cada corte reconstruye `hecho_macroproyecto`, `hecho_proyecto`,
    `hecho_convenio` y `agg_proyecto_linea_mes` con los registros que existían en esa fecha (creación, inicio o
    firma anteriores al corte) y las medidas que dependen del corte (hitos atrasados, días para vencer). El
    estado es el ACTUAL de la fuente: la fuente no guarda la historia de estados, así que un corte pasado puede
    mostrar como finalizado un proyecto que entonces estaba en ejecución. Repetirla reemplaza esos cortes.
    No registra marcas en `etl_marca_calidad` (los hechos sí llevan `marca_calidad`): el conteo de INF-TRA-08
    sale de la ejecución nocturna.
    """
    claves = _Claves(destino, sal)
    resumenes: list[ResumenCarga] = []

    def sin_marcas(paso: Callable[[], _Salida]) -> Callable[[], _Salida]:
        # Los registros defectuosos se repiten en cada corte: registrarlos en cada uno inflaría INF-TRA-08.
        # Los hechos conservan `marca_calidad`; `etl_marca_calidad` solo la llena la ejecución nocturna.
        def envuelto() -> _Salida:
            salida = paso()
            salida.marcas = []
            return salida

        return envuelto

    corte = fin_de_mes(desde)
    while corte <= hasta:
        for nombre, paso in (
            ("hecho_macroproyecto", lambda c=corte: _hecho_macroproyecto(origen, destino, claves, c)),
            ("hecho_proyecto", lambda c=corte: _hecho_proyecto(origen, destino, claves, c, catalogo_estados)),
            ("hecho_convenio", lambda c=corte: _hecho_convenio(origen, destino, claves, c, catalogo_estados)),
            ("agg_proyecto_linea_mes", lambda c=corte: _agg_proyecto_linea_mes(destino, c)),
        ):
            resumenes.append(_ejecutar_tabla(destino, nombre, sin_marcas(paso)))
        corte = fin_de_mes(corte + timedelta(days=1))
    return resumenes
