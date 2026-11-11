"""Semilla de la capa semántica: métricas, dimensiones, compatibilidad y plantillas base.

Cubre los prompts P1–P10 (Tabla 22) y las plantillas base que el diseño describe con detalle. La compatibilidad
se DERIVA de las claves foráneas del esquema `ana_` (matriz de bus, Tabla 15) menos las exclusiones declaradas
en `EXCLUSIONES`; no se escribe a mano.

Ampliar el alcance es agregar un registro aquí (o en `rpt_metrica` / `rpt_dimension`, RF-22), no programar
un informe.
"""

from __future__ import annotations

from ciumb_analitica.semantica.modelos import (
    Aditividad,
    AgregadoAlterno,
    CapaSemantica,
    Dimension,
    Metrica,
    TipoDimension,
    alcanzable,
)
from ciumb_analitica.spec.modelos import Agregacion

_A = Agregacion
_MEDIDA = (_A.SUMA, _A.PROMEDIO, _A.MEDIANA)
_PROMEDIABLE = (_A.PROMEDIO, _A.MEDIANA)


def _conteo(codigo, nombre, descripcion, hecho, sinonimos, *, aditividad=Aditividad.ADITIVA, unidad, **kw) -> Metrica:
    return Metrica(
        codigo=codigo, nombre=nombre, descripcion=descripcion, sinonimos=sinonimos, hecho_o_agregado=hecho,
        expresion_sql="*", agregaciones=(_A.CONTEO,), agregacion_defecto=_A.CONTEO, aditividad=aditividad,
        unidad=unidad, **kw,
    )  # fmt: skip


def _medida(
    codigo,
    nombre,
    descripcion,
    hecho,
    columna,
    sinonimos,
    *,
    agregaciones=_MEDIDA,
    defecto=None,
    aditividad=Aditividad.ADITIVA,
    unidad,
    **kw,
) -> Metrica:
    return Metrica(
        codigo=codigo, nombre=nombre, descripcion=descripcion, sinonimos=sinonimos, hecho_o_agregado=hecho,
        expresion_sql=columna, agregaciones=agregaciones, agregacion_defecto=defecto or agregaciones[0],
        aditividad=aditividad, unidad=unidad, **kw,
    )  # fmt: skip


def _razon(codigo, nombre, descripcion, hecho, expresion, sinonimos, *, unidad="%", **kw) -> Metrica:
    return Metrica(
        codigo=codigo, nombre=nombre, descripcion=descripcion, sinonimos=sinonimos, hecho_o_agregado=hecho,
        expresion_sql=expresion, agregaciones=(_A.RAZON,), agregacion_defecto=_A.RAZON,
        aditividad=Aditividad.NO_ADITIVA, unidad=unidad, **kw,
    )  # fmt: skip


_SEMI = Aditividad.SEMIADITIVA
_NO = Aditividad.NO_ADITIVA

METRICAS: tuple[Metrica, ...] = (
    # --- hecho_proyecto (instantánea mensual) ---------------------------------------------------------------
    _conteo("proyectos", "Proyectos de investigación", "Número de proyectos de investigación en la fecha de corte.",
            "hecho_proyecto", ("proyectos de investigación", "número de proyectos", "cuántos proyectos"),
            aditividad=_SEMI, unidad="proyectos",
            agregados=(AgregadoAlterno(tabla="agg_proyecto_linea_mes", expresion_sql="n_proyectos"),)),
    _medida("presupuesto_asignado", "Presupuesto asignado", "Presupuesto asignado a los proyectos.",
            "hecho_proyecto", "presupuesto_asignado", ("presupuesto aprobado", "recursos asignados"),
            aditividad=_SEMI, unidad="COP",
            agregados=(AgregadoAlterno(tabla="agg_proyecto_linea_mes", expresion_sql="presupuesto_asignado"),)),
    _medida("presupuesto_ejecutado", "Presupuesto ejecutado", "Presupuesto ejecutado acumulado a la fecha de corte.",
            "hecho_proyecto", "presupuesto_ejecutado", ("ejecución presupuestal en pesos", "plata ejecutada", "gasto"),
            aditividad=_SEMI, unidad="COP",
            agregados=(AgregadoAlterno(tabla="agg_proyecto_linea_mes", expresion_sql="presupuesto_ejecutado"),)),
    _razon("pct_ejecucion", "Porcentaje de ejecución presupuestal",
           "Presupuesto ejecutado sobre presupuesto asignado. Se recalcula desde sus componentes.",
           "hecho_proyecto", "100 * presupuesto_ejecutado / presupuesto_asignado",
           ("ejecución presupuestal", "porcentaje ejecutado", "avance del presupuesto"),
           agregados=(AgregadoAlterno(tabla="agg_proyecto_linea_mes",
                                      expresion_sql="100 * presupuesto_ejecutado / presupuesto_asignado"),)),
    _medida("hitos_atrasados", "Hitos atrasados", "Número de hitos o entregables atrasados en la fecha de corte.",
            "hecho_proyecto", "n_hitos_atrasados", ("entregables atrasados", "hitos vencidos"),
            agregaciones=(_A.SUMA, _A.PROMEDIO, _A.MEDIANA), aditividad=_SEMI, unidad="hitos",
            agregados=(AgregadoAlterno(tabla="agg_proyecto_linea_mes", expresion_sql="n_hitos_atrasados"),)),
    _razon("pct_hitos_atrasados", "Porcentaje de hitos atrasados",
           "Hitos atrasados sobre el total de hitos. Se recalcula desde sus componentes.",
           "hecho_proyecto", "100 * n_hitos_atrasados / n_hitos",
           ("hitos atrasados en porcentaje", "retraso de entregables", "proporción de hitos atrasados"),
           agregados=(AgregadoAlterno(tabla="agg_proyecto_linea_mes",
                                      expresion_sql="100 * n_hitos_atrasados / n_hitos"),)),
    _medida("n_integrantes", "Integrantes por proyecto", "Número de integrantes de cada proyecto.",
            "hecho_proyecto", "n_integrantes", ("investigadores por proyecto", "tamaño del equipo"),
            agregaciones=(_A.PROMEDIO, _A.MEDIANA, _A.SUMA), aditividad=_SEMI, unidad="personas"),
    _medida("dias_aprobacion", "Días de aprobación", "Días entre la creación y la aprobación del proyecto.",
            "hecho_proyecto", "dias_creacion_aprobacion", ("tiempo de aprobación", "demora en aprobar"),
            agregaciones=_PROMEDIABLE, aditividad=_NO, unidad="dias"),
    # --- hecho_macroproyecto (instantánea mensual) ----------------------------------------------------------
    _conteo("macroproyectos", "Macroproyectos", "Número de macroproyectos en la fecha de corte.",
            "hecho_macroproyecto", ("macro proyectos", "cuántos macroproyectos"), aditividad=_SEMI,
            unidad="macroproyectos"),
    _medida("pct_avance", "Porcentaje de avance del macroproyecto", "Avance registrado de cada macroproyecto.",
            "hecho_macroproyecto", "pct_avance", ("avance", "progreso del macroproyecto"),
            agregaciones=_PROMEDIABLE, aditividad=_NO, unidad="%"),
    _medida("desviacion_dias", "Desviación en días", "Días de desviación frente a la fecha de fin planeada.",
            "hecho_macroproyecto", "desviacion_dias", ("retraso del macroproyecto", "desviación del cronograma"),
            agregaciones=_PROMEDIABLE, aditividad=_NO, unidad="dias"),
    # --- hecho_hito (transacción) ----------------------------------------------------------------------------
    _conteo("hitos", "Hitos y entregables", "Número de hitos o entregables planeados.",
            "hecho_hito", ("entregables", "cuántos hitos"), unidad="hitos"),
    _medida("dias_retraso_hito", "Días de retraso de los hitos", "Días de retraso de cada hito frente a lo planeado.",
            "hecho_hito", "dias_retraso", ("retraso de hitos", "demora de entregables"),
            agregaciones=_PROMEDIABLE, aditividad=_NO, unidad="dias"),
    _razon("pct_hitos_a_tiempo", "Porcentaje de hitos a tiempo", "Hitos entregados a tiempo sobre el total.",
           "hecho_hito", "100 * a_tiempo / *", ("cumplimiento de hitos", "entregas a tiempo")),
    # --- hecho_practica (instantánea acumulativa) ------------------------------------------------------------
    _conteo("practicas", "Prácticas", "Número de prácticas empresariales.",
            "hecho_practica", ("prácticas empresariales", "practicantes", "cuántas prácticas"),
            unidad="practicas", columna_personas="seudonimo_estudiante"),
    _medida("duracion_practica", "Duración de las prácticas", "Duración de cada práctica en días.",
            "hecho_practica", "duracion_dias", ("tiempo de práctica",),
            agregaciones=_PROMEDIABLE, aditividad=_NO, unidad="dias", columna_personas="seudonimo_estudiante"),
    _razon("pct_tareas_cumplidas", "Porcentaje de tareas cumplidas", "Tareas cumplidas sobre tareas asignadas.",
           "hecho_practica", "100 * tareas_cumplidas / tareas_asignadas",
           ("cumplimiento de tareas", "avance de las prácticas"), columna_personas="seudonimo_estudiante"),
    _razon("pct_practicas_finalizadas", "Porcentaje de prácticas finalizadas", "Prácticas finalizadas sobre el total.",
           "hecho_practica", "100 * finalizada / *", ("tasa de finalización", "prácticas terminadas"),
           columna_personas="seudonimo_estudiante"),
    # --- hecho_convenio (instantánea mensual) ----------------------------------------------------------------
    _conteo("convenios", "Convenios", "Número de convenios en la fecha de corte.",
            "hecho_convenio", ("acuerdos", "cuántos convenios"), aditividad=_SEMI, unidad="convenios"),
    _medida("dias_para_vencer", "Días para vencer", "Días que faltan para que venza cada convenio.",
            "hecho_convenio", "dias_para_vencer", ("vencimiento de convenios",),
            agregaciones=_PROMEDIABLE, aditividad=_NO, unidad="dias"),
    _razon("pct_convenios_renovados", "Tasa de renovación de convenios", "Convenios renovados sobre el total.",
           "hecho_convenio", "100 * renovado / *", ("renovación de convenios", "tasa de renovación")),
    _razon("pct_docs_completos", "Convenios con documentos completos", "Convenios con documentación completa.",
           "hecho_convenio", "100 * docs_completos / *", ("documentación completa", "soportes completos")),
    # --- hecho_consultoria (instantánea acumulativa) ---------------------------------------------------------
    _conteo("consultorias", "Consultorías", "Número de consultorías.",
            "hecho_consultoria", ("asesorías", "cuántas consultorías"), unidad="consultorias"),
    _medida("valor_consultoria", "Valor facturado por consultoría", "Valor total facturado de cada consultoría.",
            "hecho_consultoria", "valor_facturado", ("valor de las consultorías", "ingreso por consultoría"),
            unidad="COP"),
    _medida("satisfaccion", "Satisfacción del cliente", "Calificación de satisfacción de cada consultoría.",
            "hecho_consultoria", "satisfaccion", ("calificación del cliente", "satisfacción"),
            agregaciones=_PROMEDIABLE, aditividad=_NO, unidad="puntos"),
    _medida("n_consultores", "Consultores por consultoría", "Número de consultores asignados a cada consultoría.",
            "hecho_consultoria", "n_consultores", ("número de consultores", "tamaño del equipo consultor"),
            agregaciones=(_A.PROMEDIO, _A.MEDIANA, _A.SUMA), unidad="personas"),
    _medida("duracion_consultoria", "Duración de las consultorías", "Duración de cada consultoría en días.",
            "hecho_consultoria", "duracion_dias", ("tiempo de consultoría",),
            agregaciones=_PROMEDIABLE, aditividad=_NO, unidad="dias"),
    # --- agg_facturacion_mes ---------------------------------------------------------------------------------
    _medida("facturacion", "Facturación de consultorías", "Valor facturado por consultorías, por mes de la factura.",
            "agg_facturacion_mes", "valor_facturado",
            ("plata facturada", "ingresos por consultoría", "facturación mensual", "ventas de consultoría"),
            agregaciones=(_A.SUMA, _A.PROMEDIO), unidad="COP"),
    # --- hecho_acceso_diario ---------------------------------------------------------------------------------
    _medida("accesos", "Accesos al sistema", "Ingresos exitosos al sistema.",
            "hecho_acceso_diario", "n_accesos", ("ingresos", "inicios de sesión"),
            agregaciones=(_A.SUMA, _A.PROMEDIO), unidad="accesos", columna_personas="sk_persona"),
    _medida("intentos_fallidos", "Intentos fallidos", "Intentos de ingreso fallidos.",
            "hecho_acceso_diario", "n_fallidos", ("accesos fallidos", "errores de ingreso"),
            agregaciones=(_A.SUMA, _A.PROMEDIO), unidad="intentos", columna_personas="sk_persona"),
    _medida("bloqueos", "Bloqueos de cuenta", "Bloqueos generados por intentos fallidos.",
            "hecho_acceso_diario", "bloqueos", ("cuentas bloqueadas",),
            agregaciones=(_A.SUMA, _A.PROMEDIO), unidad="bloqueos", columna_personas="sk_persona"),
)  # fmt: skip

_CAT = TipoDimension.CATEGORICA
_TMP = TipoDimension.TEMPORAL


def _dim(codigo, nombre, descripcion, tabla_columna, sinonimos=(), tipo=_CAT, **kw) -> Dimension:
    return Dimension(codigo=codigo, nombre=nombre, descripcion=descripcion, tabla_columna=tabla_columna,
                     sinonimos=sinonimos, tipo=tipo, **kw)  # fmt: skip


DIMENSIONES: tuple[Dimension, ...] = (
    _dim("tiempo", "Tiempo", "Fecha, con granularidad mes, trimestre, semestre o año.", "dim_tiempo.fecha",
         ("fecha", "mes a mes", "mensual", "trimestral", "semestral", "anual", "evolución"), _TMP),
    _dim("periodo_academico", "Periodo académico", "Periodo académico, p. ej. 2026-2.", "dim_tiempo.periodo_academico",
         ("semestre académico", "periodo"), _TMP),
    _dim("anio", "Año", "Año calendario.", "dim_tiempo.anio", ("año", "vigencia"), _TMP),
    _dim("facultad", "Facultad", "Facultad a la que pertenece el programa.", "dim_linea_programa.facultad",
         ("facultades",)),
    _dim("programa", "Programa académico", "Programa académico.", "dim_linea_programa.programa",
         ("carrera", "programas")),
    _dim("linea_investigacion", "Línea de investigación", "Línea de investigación del proyecto.",
         "dim_linea_programa.linea_investigacion", ("línea", "líneas de investigación")),
    _dim("estado", "Estado", "Estado del registro en su módulo.", "dim_estado.estado", ("estados", "situación")),
    _dim("macroproyecto", "Macroproyecto", "Macroproyecto al que pertenece el registro.", "dim_macroproyecto.nombre",
         ("macro proyecto",), viaja_a_ia=False),
    _dim("empresa", "Empresa", "Empresa vinculada (se identifica por una clave interna, nunca por su razón social).",
         "dim_empresa.sk_empresa", ("empresas", "organización", "cliente"), viaja_a_ia=False),
    _dim("sector", "Sector de la empresa", "Sector económico de la empresa.", "dim_empresa.sector",
         ("sector económico", "industria")),
    _dim("ciudad", "Ciudad de la empresa", "Ciudad de la empresa.", "dim_empresa.ciudad", ("ciudades", "ubicación")),
    _dim("tipo_empresa", "Tipo de empresa", "Tipo de empresa.", "dim_empresa.tipo", ("clase de empresa",)),
    _dim("segmento_actividad", "Segmento de actividad", "Grupo de la empresa según su actividad con el centro.",
         "dim_empresa.segmento_actividad", ("segmento", "grupo de empresas")),
    _dim("tipo_convenio", "Tipo de convenio", "Marco, específico o cooperación.", "dim_tipo_convenio.tipo_convenio",
         ("clase de convenio",)),
    _dim("rol", "Rol", "Rol de la persona asociada al registro (tutor, consultor…).", "dim_persona_rol.rol",
         ("roles",)),
    # Identifican personas: existen para explicar el rechazo (paso 7 del validador), nunca se compilan.
    _dim("persona", "Persona", "Tutor, consultor o usuario individual.", "dim_persona_rol.seudonimo",
         ("tutor", "consultor", "usuario", "nombre", "correo", "documento", "quién"),
         identifica_persona=True, viaja_a_ia=False),
    _dim("estudiante", "Estudiante", "Estudiante en práctica.", "hecho_practica.seudonimo_estudiante",
         ("estudiantes", "practicante", "alumno", "nombres de estudiantes", "correos de estudiantes"),
         identifica_persona=True, viaja_a_ia=False),
    # Binaria derivada de una razón (D-19): categorías 'atrasado' y 'a_tiempo'.
    Dimension(codigo="estado_hito", nombre="Estado del hito (atrasado o a tiempo)",
              descripcion="Dos categorías derivadas del porcentaje de hitos atrasados. Solo como variable de una "
                          "prueba con esa métrica.",
              sinonimos=("hitos atrasados o no", "atraso de hitos"), tipo=_CAT,
              binaria_de_metrica="pct_hitos_atrasados"),
)  # fmt: skip

EXCLUSIONES: frozenset[tuple[str, str]] = frozenset(
    # D-13: las prácticas tienen programa y facultad, no línea de investigación.
    {(m, "linea_investigacion") for m in ("practicas", "duracion_practica", "pct_tareas_cumplidas",
                                          "pct_practicas_finalizadas")}
)  # fmt: skip


def derivar_compatibilidad(metricas=METRICAS, dimensiones=DIMENSIONES) -> frozenset[tuple[str, str]]:
    """Matriz de bus como reglas: (métrica, dimensión) si el hecho de la métrica tiene esa dimensión."""
    return frozenset(
        (m.codigo, d.codigo)
        for m in metricas
        for d in dimensiones
        if alcanzable(m, d) and (m.codigo, d.codigo) not in EXCLUSIONES
    )


def capa_semilla() -> CapaSemantica:
    return CapaSemantica(
        metricas={m.codigo: m for m in METRICAS},
        dimensiones={d.codigo: d for d in DIMENSIONES},
        compatibilidad=derivar_compatibilidad(),
    )


# --- Plantillas base (rpt_plantilla) -------------------------------------------------------------------------
# El diseño habla de 18 plantillas base pero no las enumera. Aquí están las que describe con suficiente detalle
# (acordado con Daniel el 2026-11-11); las demás se agregan como registros cuando se entregue la lista.
# Los nombres son provisionales. `alcance` es un marcador: el backend lo reemplaza siempre (RF-21).

_E = "ciumb.spec/1.0"
_ALC = {"rol": "directivo"}
_TODOS = ("directivo", "coordinador", "administrador")


def _plantilla(codigo, nombre, roles=_TODOS, **spec) -> dict:
    return {
        "codigo_informe": codigo,
        "nombre": nombre,
        "roles_permitidos": roles,
        "spec": {"esquema": _E, "origen": "plantilla_base", "base": codigo, **spec, "alcance": _ALC},
    }


PLANTILLAS: tuple[dict, ...] = (
    _plantilla("INF-INV-01", "Proyectos de investigación por estado",
               metricas=[{"id": "proyectos", "agregacion": "conteo"}],
               dimensiones=[{"id": "tiempo", "granularidad": "mes"}, {"id": "estado"}],
               analisis={"metodo": "serie"}, grafico={"tipo": "lineas", "origen": "recomendado"}),
    _plantilla("INF-INV-02", "Ejecución presupuestal de proyectos",
               metricas=[{"id": "pct_ejecucion"}],
               analisis={"metodo": "descriptiva", "atipicos": {"metodo": "RIC", "k": 1.5}},
               grafico={"tipo": "histograma", "origen": "recomendado"}),
    _plantilla("INF-COS-02", "Facturación mensual de consultorías",
               metricas=[{"id": "facturacion", "agregacion": "suma"}],
               dimensiones=[{"id": "tiempo", "granularidad": "mes"}],
               analisis={"metodo": "serie", "acumulado": True}, grafico={"tipo": "lineas", "origen": "recomendado"}),
    _plantilla("INF-EMP-03", "Segmentación de empresas por actividad", roles=("directivo", "administrador"),
               metricas=[{"id": "practicas", "agregacion": "conteo"}, {"id": "convenios", "agregacion": "conteo"},
                         {"id": "consultorias", "agregacion": "conteo"}],
               dimensiones=[{"id": "empresa"}],
               analisis={"metodo": "segmentacion", "tecnica": "kmedias"},
               grafico={"tipo": "dispersion", "origen": "recomendado"}),
    _plantilla("INF-TRA-04", "Comparación entre periodos",
               metricas=[{"id": "proyectos", "agregacion": "conteo"}],
               dimensiones=[{"id": "tiempo", "granularidad": "semestre"}],
               analisis={"metodo": "variacion"}, grafico={"tipo": "barras", "origen": "recomendado"}),
    _plantilla("INF-TRA-05", "Pronóstico de prácticas",
               metricas=[{"id": "practicas", "agregacion": "conteo"}],
               dimensiones=[{"id": "tiempo", "granularidad": "semestre"}],
               analisis={"metodo": "pronostico", "tecnica": "holt", "horizonte": 2, "nivel_confianza": 0.95},
               grafico={"tipo": "lineas", "origen": "recomendado"}),
    _plantilla("INF-TRA-06", "Relación entre consultores y satisfacción",
               metricas=[{"id": "n_consultores"}, {"id": "satisfaccion"}],
               analisis={"metodo": "spearman", "variables": ["n_consultores", "satisfaccion"], "alfa": 0.05},
               grafico={"tipo": "dispersion", "origen": "recomendado"}),
    _plantilla("INF-TRA-07", "Valores atípicos de presupuesto ejecutado",
               metricas=[{"id": "presupuesto_ejecutado"}],
               analisis={"metodo": "atipicos", "tecnica": "RIC", "k": 1.5},
               grafico={"tipo": "histograma", "origen": "recomendado"}),
)  # fmt: skip
