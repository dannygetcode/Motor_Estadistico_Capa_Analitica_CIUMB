"""Generador de datos sintéticos de la fuente 1 (modelo inferido, ver ddl.sql).

Uso:
    uv run python -m datos_sinteticos.generar                # carga en la BD de DATABASE_URL_ADMIN
    uv run python -m datos_sinteticos.generar --sql salida.sql  # solo vuelca INSERT a un archivo
    uv run python -m datos_sinteticos.generar --resumen      # solo imprime conteos

Determinista: la misma semilla produce exactamente las mismas filas (no depende de la
fecha actual). Periodo 2019-01-01 a FECHA_CORTE. Inserta defectos de calidad con
conteos exactos (DEFECTOS) y escribe datos_sinteticos/defectos.md.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import random
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path

from faker import Faker

SEMILLA = 20261111
INICIO = date(2019, 1, 1)
FECHA_CORTE = date(2026, 10, 31)
ESQUEMA = "ciumb"

# Catálogo de estados válidos por entidad. Todo valor fuera de esta lista es un defecto.
CATALOGO_ESTADOS: dict[str, list[str]] = {
    "usuario": ["activo", "inactivo", "bloqueado"],
    "macroproyecto": ["activo", "en_cierre", "cerrado", "suspendido"],
    "proyecto_investigacion": ["formulado", "en_validacion", "aprobado", "en_ejecucion", "finalizado", "cancelado"],
    "hito_entregable": ["pendiente", "entregado", "vencido"],
    "empresa": ["activa", "inactiva"],
    "convenio": ["vigente", "vencido", "en_renovacion", "terminado"],
    "practica": ["por_iniciar", "en_curso", "finalizada", "cancelada"],
    "consultoria": ["propuesta", "en_ejecucion", "finalizada", "cancelada"],
}
ESTADOS_INVALIDOS = ["En Ejecución", "FINALIZADO", "aprobado ", "pendiente_revision", "N/A", "activo?", "cerrada"]

# Defectos intencionales: (clave, descripción) -> cantidad exacta.
DEFECTOS: dict[str, int] = {
    "proyecto_fin_antes_inicio": 12,
    "practica_fin_antes_inicio": 15,
    "convenio_fin_antes_inicio": 6,
    "empresa_nit_repetido": 8,
    "practica_sin_tutor_academico": 18,
    "practica_sin_tutor_empresarial": 22,
    "practica_sin_tutor_ninguno": 6,
    "proyecto_estado_fuera_catalogo": 10,
    "practica_estado_fuera_catalogo": 12,
    "convenio_estado_fuera_catalogo": 5,
    "proyecto_presupuesto_ejecutado_negativo": 4,
    "practica_sin_empresa": 7,
    "convenio_sin_fecha_fin": 9,
}
DESCRIPCION_DEFECTOS = {
    "proyecto_fin_antes_inicio": "proyecto_investigacion con fecha_fin < fecha_inicio",
    "practica_fin_antes_inicio": "practica con fecha_fin < fecha_inicio",
    "convenio_fin_antes_inicio": "convenio con fecha_fin < fecha_inicio",
    "empresa_nit_repetido": "empresas cuyo NIT copia el de otra empresa (filas adicionales con NIT duplicado)",
    "practica_sin_tutor_academico": "practica con id_tutor_academico NULL (tiene tutor empresarial)",
    "practica_sin_tutor_empresarial": "practica con id_tutor_empresarial NULL (tiene tutor académico)",
    "practica_sin_tutor_ninguno": "practica sin ningún tutor (ambos NULL)",
    "proyecto_estado_fuera_catalogo": "proyecto_investigacion.estado fuera de CATALOGO_ESTADOS",
    "practica_estado_fuera_catalogo": "practica.estado fuera de CATALOGO_ESTADOS",
    "convenio_estado_fuera_catalogo": "convenio.estado fuera de CATALOGO_ESTADOS",
    "proyecto_presupuesto_ejecutado_negativo": "proyecto_investigacion.presupuesto_ejecutado < 0",
    "practica_sin_empresa": "practica con id_empresa NULL",
    "convenio_sin_fecha_fin": "convenio con fecha_fin NULL",
}

# Orden de carga (respeta las FK).
ORDEN_TABLAS = [
    "rol",
    "usuario",
    "registro_acceso",
    "facultad_programa",
    "linea_investigacion",
    "macroproyecto",
    "fase_macroproyecto",
    "proyecto_investigacion",
    "hito_entregable",
    "integrante_proyecto",
    "empresa",
    "convenio",
    "documento_convenio",
    "practica",
    "consultoria",
    "factura_consultoria",
    "consultor_consultoria",
]

FACULTADES = {
    "Ingeniería": ["Ingeniería de Software", "Ingeniería Industrial", "Ingeniería Electrónica", "Ingeniería Ambiental"],
    "Ciencias de la Salud": ["Enfermería", "Fisioterapia", "Instrumentación Quirúrgica", "Optometría"],
    "Educación": ["Licenciatura en Educación Infantil", "Licenciatura en Educación Física"],
    "Ciencias Sociales y Humanas": ["Psicología", "Derecho", "Trabajo Social"],
    "Ciencias Económicas y Administrativas": [
        "Administración de Empresas",
        "Contaduría Pública",
        "Negocios Internacionales",
    ],
}
LINEAS_EXTRA = {
    "Ingeniería de Software": ["Analítica de datos", "Ingeniería de software y calidad"],
    "Ingeniería Industrial": ["Logística y cadena de suministro", "Productividad"],
    "Ingeniería Electrónica": ["Internet de las cosas"],
    "Ingeniería Ambiental": ["Gestión del recurso hídrico"],
    "Enfermería": ["Cuidado de la salud"],
    "Fisioterapia": ["Movimiento corporal humano"],
    "Instrumentación Quirúrgica": ["Seguridad del paciente"],
    "Optometría": ["Salud visual"],
    "Licenciatura en Educación Infantil": ["Pedagogía e infancia"],
    "Licenciatura en Educación Física": ["Actividad física y deporte"],
    "Psicología": ["Salud mental", "Psicología organizacional"],
    "Derecho": ["Derecho y sociedad"],
    "Trabajo Social": ["Intervención comunitaria"],
    "Administración de Empresas": ["Emprendimiento e innovación"],
    "Contaduría Pública": ["Contabilidad y finanzas"],
    "Negocios Internacionales": ["Comercio exterior"],
}
ROLES = [
    (1, "directivo", "1,2,3,4,5,6,7"),
    (2, "coordinador", "1,2,3"),
    (3, "tutor", "3"),
    (4, "consultor", "5"),
    (5, "administrador", "7"),
    (6, "investigador", "1,2"),
    (7, "estudiante", "3"),
    (8, "tutor_empresarial", "3"),
]
TIPOS_DOCUMENTO = ["Minuta firmada", "Certificado de existencia", "Póliza", "Acta de inicio"]
SECTORES = [
    "Tecnología",
    "Salud",
    "Educación",
    "Manufactura",
    "Servicios financieros",
    "Comercio",
    "Construcción",
    "Logística",
    "Sector público",
    "Agroindustria",
]
CIUDADES = (["Bogotá"] * 10) + [
    "Medellín",
    "Cali",
    "Barranquilla",
    "Bucaramanga",
    "Tunja",
    "Chía",
    "Soacha",
    "Villavicencio",
    "Pereira",
]


@dataclass
class Datos:
    tablas: dict[str, list[dict]] = field(default_factory=dict)
    defectos: dict[str, list[int]] = field(default_factory=dict)  # clave -> ids afectados

    def conteos(self) -> dict[str, int]:
        return {t: len(self.tablas[t]) for t in ORDEN_TABLAS}


# ---------------------------------------------------------------------------
def _fecha(rng: random.Random, desde: date, hasta: date) -> date:
    return desde + timedelta(days=rng.randint(0, max(0, (hasta - desde).days)))


def _fecha_creciente(rng: random.Random, desde: date, hasta: date) -> date:
    """Fecha con tendencia creciente (más actividad en años recientes)."""
    dias = (hasta - desde).days
    return desde + timedelta(days=int(dias * (rng.random() ** 0.7)))


def _momento(rng: random.Random, d: date) -> datetime:
    return datetime.combine(d, time(rng.randint(6, 21), rng.randint(0, 59), rng.randint(0, 59)))


def _periodo(d: date) -> str:
    return f"{d.year}-{1 if d.month <= 6 else 2}"


def _tomar(rng: random.Random, disponibles: list[int], n: int) -> list[int]:
    """Toma n ids sin reemplazo y los quita de la lista (defectos disjuntos)."""
    elegidos = rng.sample(disponibles, n)
    usados = set(elegidos)
    disponibles[:] = [x for x in disponibles if x not in usados]
    return sorted(elegidos)


# ---------------------------------------------------------------------------
def generar(semilla: int = SEMILLA) -> Datos:
    rng = random.Random(semilla)
    fake = Faker("es_CO")
    fake.seed_instance(semilla)
    t: dict[str, list[dict]] = {nombre: [] for nombre in ORDEN_TABLAS}

    # --- rol y usuario ------------------------------------------------------
    t["rol"] = [{"id_rol": i, "nombre_rol": n, "alcance_modulos": a} for i, n, a in ROLES]
    cantidades = {1: 6, 2: 30, 3: 90, 4: 35, 5: 4, 6: 140, 7: 2600, 8: 260}
    por_rol: dict[int, list[int]] = {}
    id_u = 0
    for id_rol, cant in cantidades.items():
        for _ in range(cant):
            id_u += 1
            creacion = _fecha_creciente(rng, date(2018, 6, 1), FECHA_CORTE)
            ultimo = _fecha(rng, creacion, FECHA_CORTE)
            t["usuario"].append(
                {
                    "id_usuario": id_u,
                    "id_rol": id_rol,
                    "nombre_completo": fake.name(),
                    "documento": str(rng.randint(10_000_000, 1_199_999_999)),
                    "correo": fake.unique.email(),
                    "contrasena_hash": "pbkdf2_sha256$sintetico$"
                    + hashlib.sha256(f"{semilla}-{id_u}".encode()).hexdigest(),
                    "estado": rng.choices(CATALOGO_ESTADOS["usuario"], weights=[85, 12, 3])[0],
                    "fecha_creacion": creacion,
                    "ultimo_acceso": _momento(rng, ultimo),
                    "fecha_vence_contrasena": ultimo + timedelta(days=rng.choice([90, 180])),
                }
            )
            por_rol.setdefault(id_rol, []).append(id_u)

    # --- registro_acceso (personal, no estudiantes) ------------------------
    personal = [u for r in (1, 2, 3, 4, 5, 6) for u in por_rol[r]]
    for i in range(1, 45_001):
        exitoso = rng.random() > 0.08
        t["registro_acceso"].append(
            {
                "id_acceso": i,
                "id_usuario": rng.choice(personal),
                "fecha_hora": _momento(rng, _fecha_creciente(rng, INICIO, FECHA_CORTE)),
                "exitoso": exitoso,
                "bloqueo_generado": (not exitoso) and rng.random() < 0.12,
            }
        )

    # --- facultad_programa y linea_investigacion ----------------------------
    programas: dict[int, str] = {}  # id_programa -> facultad
    id_p = id_l = 0
    for facultad, nombres in FACULTADES.items():
        for nombre in nombres:
            id_p += 1
            programas[id_p] = facultad
            t["facultad_programa"].append({"id_programa": id_p, "nombre_programa": nombre, "facultad": facultad})
            for linea in LINEAS_EXTRA.get(nombre, []):
                id_l += 1
                t["linea_investigacion"].append({"id_linea": id_l, "nombre": linea, "id_programa": id_p})
    linea_programa = {fila["id_linea"]: fila["id_programa"] for fila in t["linea_investigacion"]}
    # Programa de cada estudiante (la fuente no lo tiene en usuario; se usa en practica.id_programa).
    programa_estudiante = {u: rng.choice(list(programas)) for u in por_rol[7]}

    # --- macroproyecto y fase ----------------------------------------------
    nombres_fase = ["Formulación", "Diagnóstico", "Desarrollo", "Validación", "Cierre y socialización"]
    id_f = 0
    for id_m in range(1, 49):
        inicio = _fecha(rng, INICIO, date(2025, 6, 30))
        fin_plan = inicio + timedelta(days=rng.randint(540, 1460))
        if fin_plan < FECHA_CORTE and rng.random() < 0.8:
            fin_real = fin_plan + timedelta(days=rng.randint(-30, 240))
            fin_real = min(fin_real, FECHA_CORTE)
            estado, avance = "cerrado", 100.0
        else:
            fin_real = None
            transcurrido = (FECHA_CORTE - inicio).days / max(1, (fin_plan - inicio).days)
            avance = round(min(98.0, max(3.0, 100 * transcurrido * rng.uniform(0.6, 1.1))), 2)
            estado = rng.choices(["activo", "en_cierre", "suspendido"], weights=[80, 12, 8])[0]
        t["macroproyecto"].append(
            {
                "id_macroproyecto": id_m,
                "nombre": f"Macroproyecto {fake.catch_phrase()}",
                "estado": estado,
                "id_coordinador": rng.choice(por_rol[2]),
                "id_programa": rng.choice(list(programas)),
                "fecha_inicio": inicio,
                "fecha_fin_planeada": fin_plan,
                "fecha_fin_real": fin_real,
                "porcentaje_avance": avance,
            }
        )
        n_fases = rng.randint(3, 5)
        for k in range(n_fases):
            id_f += 1
            fin_fase = inicio + (fin_plan - inicio) * (k + 1) / n_fases
            completada = fin_fase < FECHA_CORTE and (fin_real is not None or rng.random() < 0.85)
            t["fase_macroproyecto"].append(
                {
                    "id_fase": id_f,
                    "id_macroproyecto": id_m,
                    "nombre_fase": nombres_fase[k] if k < n_fases - 1 else nombres_fase[-1],
                    "avance": 100.0 if completada else round(rng.uniform(0, 90), 2),
                    "fecha_fin_planeada": fin_fase,
                    "fecha_fin_real": fin_fase + timedelta(days=rng.randint(-20, 120)) if completada else None,
                }
            )

    # --- proyecto_investigacion, hito, integrante ----------------------------
    macro_ids = [m["id_macroproyecto"] for m in t["macroproyecto"]]
    id_h = 0
    tipos_hito = ["Informe de avance", "Artículo", "Ponencia", "Software", "Informe final", "Prototipo"]
    investigadores = por_rol[6] + por_rol[3]
    for id_pr in range(1, 641):
        creacion = _fecha_creciente(rng, INICIO, FECHA_CORTE - timedelta(days=10))
        validacion = creacion + timedelta(days=rng.randint(5, 40))
        aprobacion = validacion + timedelta(days=rng.randint(7, 75))
        inicio = aprobacion + timedelta(days=rng.randint(0, 30))
        fin = inicio + timedelta(days=rng.randint(180, 730))
        asignado = round(rng.lognormvariate(17.2, 0.6), -3)  # ~30 M COP mediana
        if validacion > FECHA_CORTE:
            estado, validacion, aprobacion, inicio, fin = "formulado", None, None, None, None
        elif aprobacion > FECHA_CORTE:
            estado, aprobacion, inicio, fin = "en_validacion", None, None, None
        elif inicio > FECHA_CORTE:
            estado = "aprobado"
        elif fin > FECHA_CORTE:
            estado = rng.choices(["en_ejecucion", "cancelado"], weights=[95, 5])[0]
        else:
            estado = rng.choices(["finalizado", "cancelado"], weights=[93, 7])[0]
        if inicio is None or inicio > FECHA_CORTE:
            ejecutado = 0.0
        else:
            avance_tiempo = min(1.0, (FECHA_CORTE - inicio).days / max(1, (fin - inicio).days))
            ejecutado = round(asignado * avance_tiempo * rng.betavariate(8, 2) * rng.uniform(0.85, 1.35), 2)
        t["proyecto_investigacion"].append(
            {
                "id_proyecto": id_pr,
                "id_macroproyecto": rng.choice(macro_ids) if rng.random() < 0.9 else None,
                "id_linea": rng.choice(list(linea_programa)),
                "titulo": fake.sentence(nb_words=8).rstrip("."),
                "estado": estado,
                "fecha_creacion": creacion,
                "fecha_validacion": validacion,
                "fecha_aprobacion": aprobacion,
                "fecha_inicio": inicio,
                "fecha_fin": fin,
                "presupuesto_asignado": asignado,
                "presupuesto_ejecutado": ejecutado,
                "fecha_modificacion": _momento(rng, _fecha(rng, creacion, FECHA_CORTE)),
            }
        )
        if inicio is not None and inicio <= FECHA_CORTE:
            for _ in range(rng.randint(3, 8)):
                id_h += 1
                planeada = _fecha(rng, inicio, fin)
                retraso = int(rng.expovariate(1 / 18)) - 8
                real = planeada + timedelta(days=retraso)
                if real > FECHA_CORTE:
                    real = None
                    h_estado = "vencido" if planeada < FECHA_CORTE else "pendiente"
                else:
                    h_estado = "entregado"
                t["hito_entregable"].append(
                    {
                        "id_hito": id_h,
                        "id_proyecto": id_pr,
                        "tipo": rng.choice(tipos_hito),
                        "fecha_planeada": planeada,
                        "fecha_real": real,
                        "estado": h_estado,
                    }
                )
        miembros = rng.sample(investigadores, rng.randint(1, 4)) + rng.sample(por_rol[7], rng.randint(0, 3))
        for k, u in enumerate(miembros):
            rol = "investigador_principal" if k == 0 else ("auxiliar" if u in programa_estudiante else "coinvestigador")
            t["integrante_proyecto"].append({"id_proyecto": id_pr, "id_usuario": u, "rol_en_proyecto": rol})

    # --- empresa ------------------------------------------------------------
    for id_e in range(1, 261):
        t["empresa"].append(
            {
                "id_empresa": id_e,
                "nit": f"{rng.randint(800_000_000, 901_999_999)}-{rng.randint(0, 9)}",
                "razon_social": fake.company(),
                "sector": rng.choice(SECTORES),
                "ciudad": rng.choice(CIUDADES),
                "tipo": rng.choices(["privada", "publica", "mixta", "ong"], weights=[70, 15, 5, 10])[0],
                "fecha_registro": _fecha_creciente(rng, date(2018, 1, 1), FECHA_CORTE),
                "estado": rng.choices(CATALOGO_ESTADOS["empresa"], weights=[88, 12])[0],
            }
        )
    empresas = [e["id_empresa"] for e in t["empresa"]]
    # Actividad desigual: pocas empresas concentran prácticas y consultorías (útil para k-medias).
    peso_empresa = {e: rng.paretovariate(1.3) for e in empresas}

    # --- convenio y documento ----------------------------------------------
    id_c = id_d = 0
    convenios_empresa: dict[int, list[dict]] = {}
    for id_e in empresas:
        n = min(5, int(peso_empresa[id_e]) + rng.choice([0, 0, 1]))
        anterior = None
        firma = _fecha(rng, max(INICIO, t["empresa"][id_e - 1]["fecha_registro"]), date(2024, 6, 30))
        for _ in range(n):
            if firma > FECHA_CORTE:
                break
            id_c += 1
            inicio = firma + timedelta(days=rng.randint(0, 45))
            fin = inicio + timedelta(days=365 * rng.choice([1, 2, 3, 5]))
            if fin < FECHA_CORTE:
                estado = rng.choices(["vencido", "terminado"], weights=[70, 30])[0]
            else:
                estado = "en_renovacion" if (fin - FECHA_CORTE).days < 60 else "vigente"
            fila = {
                "id_convenio": id_c,
                "id_empresa": id_e,
                "tipo": rng.choices(["marco", "especifico", "cooperacion"], weights=[30, 50, 20])[0],
                "fecha_firma": firma,
                "fecha_inicio": inicio,
                "fecha_fin": fin,
                "id_convenio_anterior": anterior,
                "estado": estado,
            }
            t["convenio"].append(fila)
            convenios_empresa.setdefault(id_e, []).append(fila)
            for tipo_doc in TIPOS_DOCUMENTO[: rng.randint(2, 4)]:
                id_d += 1
                t["documento_convenio"].append(
                    {
                        "id_documento": id_d,
                        "id_convenio": id_c,
                        "tipo_documento": tipo_doc,
                        "cargado": rng.random() < 0.85,
                    }
                )
            # ¿Se renueva? El siguiente convenio arranca cerca del fin del actual.
            if rng.random() < 0.45:
                anterior, firma = id_c, fin - timedelta(days=rng.randint(0, 30))
            else:
                anterior, firma = None, fin + timedelta(days=rng.randint(60, 700))

    # --- practica -----------------------------------------------------------
    con_convenio = [e for e in empresas if e in convenios_empresa]
    pesos = [peso_empresa[e] for e in con_convenio]
    semestres = [(a, s) for a in range(2019, 2027) for s in (1, 2)]
    id_pa = 0
    for anio, sem in semestres:
        base = 95 + 22 * (anio - 2019) + (25 if sem == 2 else 0)  # tendencia y estacionalidad
        if anio == 2020:
            base = int(base * 0.6)  # caída por pandemia
        for _ in range(int(base * rng.uniform(0.9, 1.1))):
            id_pa += 1
            inicio = date(anio, 2 if sem == 1 else 8, 1) + timedelta(days=rng.randint(0, 20))
            fin = inicio + timedelta(days=rng.randint(110, 150))
            id_e = rng.choices(con_convenio, weights=pesos)[0]
            vigentes = [c for c in convenios_empresa[id_e] if c["fecha_inicio"] <= inicio <= c["fecha_fin"]]
            asignadas = rng.randint(8, 30)
            if inicio > FECHA_CORTE:
                estado, cumplidas = "por_iniciar", 0
            elif fin > FECHA_CORTE:
                estado = "en_curso"
                cumplidas = int(asignadas * (FECHA_CORTE - inicio).days / (fin - inicio).days * rng.uniform(0.6, 1.0))
            else:
                estado = rng.choices(["finalizada", "cancelada"], weights=[94, 6])[0]
                cumplidas = asignadas if estado == "finalizada" and rng.random() < 0.6 else rng.randint(0, asignadas)
            est = rng.choice(por_rol[7])
            t["practica"].append(
                {
                    "id_practica": id_pa,
                    "id_estudiante": est,
                    "id_empresa": id_e,
                    "id_convenio": rng.choice(vigentes)["id_convenio"] if vigentes else None,
                    "id_macroproyecto": rng.choice(macro_ids) if rng.random() < 0.3 else None,
                    "id_programa": programa_estudiante[est],
                    "id_tutor_academico": rng.choice(por_rol[3]),
                    "id_tutor_empresarial": rng.choice(por_rol[8]),
                    "periodo": f"{anio}-{sem}",
                    "estado": estado,
                    "fecha_inicio": inicio,
                    "fecha_fin": fin,
                    "tareas_asignadas": asignadas,
                    "tareas_cumplidas": cumplidas,
                    "fecha_modificacion": _momento(rng, min(FECHA_CORTE, fin)),
                }
            )

    # --- consultoria, factura, consultor ------------------------------------
    id_fa = 0
    for id_co in range(1, 311):
        id_e = rng.choices(empresas, weights=[peso_empresa[e] for e in empresas])[0]
        inicio = _fecha_creciente(rng, INICIO, FECHA_CORTE - timedelta(days=15))
        fin = inicio + timedelta(days=rng.randint(30, 300))
        valor = round(rng.lognormvariate(16.6, 0.7), -3)  # ~16 M COP mediana
        n_consultores = rng.randint(1, 4)
        cierre = rng.choices(["finalizada", "cancelada"], weights=[92, 8])[0]
        estado = "en_ejecucion" if fin > FECHA_CORTE else cierre
        satisf = None
        if estado == "finalizada":
            satisf = round(min(5.0, max(1.0, rng.gauss(3.6 + 0.2 * n_consultores, 0.6))), 1)
        vigentes = [c for c in convenios_empresa.get(id_e, []) if c["fecha_inicio"] <= inicio <= c["fecha_fin"]]
        t["consultoria"].append(
            {
                "id_consultoria": id_co,
                "id_empresa": id_e,
                "id_convenio": rng.choice(vigentes)["id_convenio"] if vigentes else None,
                "estado": estado,
                "fecha_inicio": inicio,
                "fecha_fin": fin,
                "valor_contratado": valor,
                "calificacion_satisfaccion": satisf,
            }
        )
        if estado != "cancelada":
            n_fact = rng.randint(1, 5)
            for k in range(n_fact):
                fecha = inicio + (fin - inicio) * (k + 1) / n_fact
                if fecha > FECHA_CORTE:
                    break
                id_fa += 1
                t["factura_consultoria"].append(
                    {
                        "id_factura": id_fa,
                        "id_consultoria": id_co,
                        "fecha_factura": fecha,
                        "valor": round(valor / n_fact, 2),
                    }
                )
        for k, u in enumerate(rng.sample(por_rol[4], n_consultores)):
            t["consultor_consultoria"].append(
                {
                    "id_consultoria": id_co,
                    "id_usuario": u,
                    "rol": "lider" if k == 0 else "consultor",
                }
            )

    datos = Datos(tablas=t)
    _inyectar_defectos(rng, datos)
    return datos


# ---------------------------------------------------------------------------
def _inyectar_defectos(rng: random.Random, datos: Datos) -> None:
    t, d = datos.tablas, datos.defectos

    # Proyectos: fin antes de inicio, estado fuera de catálogo, ejecutado negativo (disjuntos).
    proyectos = {p["id_proyecto"]: p for p in t["proyecto_investigacion"]}
    con_fechas = [i for i, p in proyectos.items() if p["fecha_inicio"] and p["fecha_fin"]]
    d["proyecto_fin_antes_inicio"] = _tomar(rng, con_fechas, DEFECTOS["proyecto_fin_antes_inicio"])
    for i in d["proyecto_fin_antes_inicio"]:
        p = proyectos[i]
        p["fecha_fin"] = p["fecha_inicio"] - timedelta(days=rng.randint(1, 120))
    d["proyecto_estado_fuera_catalogo"] = _tomar(rng, con_fechas, DEFECTOS["proyecto_estado_fuera_catalogo"])
    for i in d["proyecto_estado_fuera_catalogo"]:
        proyectos[i]["estado"] = rng.choice(ESTADOS_INVALIDOS)
    d["proyecto_presupuesto_ejecutado_negativo"] = _tomar(
        rng, con_fechas, DEFECTOS["proyecto_presupuesto_ejecutado_negativo"]
    )
    for i in d["proyecto_presupuesto_ejecutado_negativo"]:
        proyectos[i]["presupuesto_ejecutado"] = -round(rng.uniform(100_000, 5_000_000), 2)

    # Prácticas: un solo defecto por fila para que los conteos sean exactos.
    practicas = {p["id_practica"]: p for p in t["practica"]}
    libres = list(practicas)
    d["practica_fin_antes_inicio"] = _tomar(rng, libres, DEFECTOS["practica_fin_antes_inicio"])
    for i in d["practica_fin_antes_inicio"]:
        p = practicas[i]
        p["fecha_fin"] = p["fecha_inicio"] - timedelta(days=rng.randint(1, 90))
    for clave, campos in [
        ("practica_sin_tutor_academico", ["id_tutor_academico"]),
        ("practica_sin_tutor_empresarial", ["id_tutor_empresarial"]),
        ("practica_sin_tutor_ninguno", ["id_tutor_academico", "id_tutor_empresarial"]),
    ]:
        d[clave] = _tomar(rng, libres, DEFECTOS[clave])
        for i in d[clave]:
            for c in campos:
                practicas[i][c] = None
    d["practica_estado_fuera_catalogo"] = _tomar(rng, libres, DEFECTOS["practica_estado_fuera_catalogo"])
    for i in d["practica_estado_fuera_catalogo"]:
        practicas[i]["estado"] = rng.choice(ESTADOS_INVALIDOS)
    d["practica_sin_empresa"] = _tomar(rng, libres, DEFECTOS["practica_sin_empresa"])
    for i in d["practica_sin_empresa"]:
        practicas[i]["id_empresa"] = None
        practicas[i]["id_convenio"] = None

    # Convenios. Solo convenios sin renovación posterior, para no romper la cadena anterior/siguiente.
    convenios = {c["id_convenio"]: c for c in t["convenio"]}
    referidos = {c["id_convenio_anterior"] for c in t["convenio"] if c["id_convenio_anterior"]}
    usados_por = {p["id_convenio"] for p in t["practica"]} | {c["id_convenio"] for c in t["consultoria"]}
    libres_c = [i for i in convenios if i not in referidos and i not in usados_por]
    d["convenio_fin_antes_inicio"] = _tomar(rng, libres_c, DEFECTOS["convenio_fin_antes_inicio"])
    for i in d["convenio_fin_antes_inicio"]:
        c = convenios[i]
        c["fecha_fin"] = c["fecha_inicio"] - timedelta(days=rng.randint(1, 200))
    d["convenio_sin_fecha_fin"] = _tomar(rng, libres_c, DEFECTOS["convenio_sin_fecha_fin"])
    for i in d["convenio_sin_fecha_fin"]:
        convenios[i]["fecha_fin"] = None
    d["convenio_estado_fuera_catalogo"] = _tomar(rng, libres_c, DEFECTOS["convenio_estado_fuera_catalogo"])
    for i in d["convenio_estado_fuera_catalogo"]:
        convenios[i]["estado"] = rng.choice(ESTADOS_INVALIDOS)

    # Empresas con NIT repetido: copian el NIT de otra empresa distinta.
    empresas = {e["id_empresa"]: e for e in t["empresa"]}
    libres_e = list(empresas)
    d["empresa_nit_repetido"] = _tomar(rng, libres_e, DEFECTOS["empresa_nit_repetido"])
    origenes = _tomar(rng, libres_e, DEFECTOS["empresa_nit_repetido"])
    for i, j in zip(d["empresa_nit_repetido"], origenes, strict=True):
        empresas[i]["nit"] = empresas[j]["nit"]


# ---------------------------------------------------------------------------
def contar_defectos(datos: Datos) -> dict[str, int]:
    """Recuenta los defectos desde las filas (independiente de cómo se inyectaron)."""
    t = datos.tablas
    cat = CATALOGO_ESTADOS
    pr, pa, co = t["proyecto_investigacion"], t["practica"], t["convenio"]

    def fin_antes(filas):
        return sum(1 for f in filas if f["fecha_inicio"] and f["fecha_fin"] and f["fecha_fin"] < f["fecha_inicio"])

    nits = Counter(e["nit"] for e in t["empresa"])
    return {
        "proyecto_fin_antes_inicio": fin_antes(pr),
        "practica_fin_antes_inicio": fin_antes(pa),
        "convenio_fin_antes_inicio": fin_antes(co),
        "empresa_nit_repetido": sum(n - 1 for n in nits.values() if n > 1),
        "practica_sin_tutor_academico": sum(
            1 for p in pa if p["id_tutor_academico"] is None and p["id_tutor_empresarial"] is not None
        ),
        "practica_sin_tutor_empresarial": sum(
            1 for p in pa if p["id_tutor_empresarial"] is None and p["id_tutor_academico"] is not None
        ),
        "practica_sin_tutor_ninguno": sum(
            1 for p in pa if p["id_tutor_academico"] is None and p["id_tutor_empresarial"] is None
        ),
        "proyecto_estado_fuera_catalogo": sum(1 for p in pr if p["estado"] not in cat["proyecto_investigacion"]),
        "practica_estado_fuera_catalogo": sum(1 for p in pa if p["estado"] not in cat["practica"]),
        "convenio_estado_fuera_catalogo": sum(1 for c in co if c["estado"] not in cat["convenio"]),
        "proyecto_presupuesto_ejecutado_negativo": sum(1 for p in pr if (p["presupuesto_ejecutado"] or 0) < 0),
        "practica_sin_empresa": sum(1 for p in pa if p["id_empresa"] is None),
        "convenio_sin_fecha_fin": sum(1 for c in co if c["fecha_fin"] is None),
    }


def escribir_defectos_md(datos: Datos, ruta: Path) -> None:
    conteos = datos.conteos()
    lineas = [
        "# Datos sintéticos de la fuente 1",
        "",
        "Generado por `datos_sinteticos/generar.py` (no editar a mano).",
        f"Semilla `{SEMILLA}` · periodo {INICIO.isoformat()} a {FECHA_CORTE.isoformat()} · Faker `es_CO`.",
        "",
        "## Filas por tabla",
        "",
        "| Tabla | Filas |",
        "|---|---:|",
        *[f"| {tabla} | {n:,} |".replace(",", ".") for tabla, n in conteos.items()],
        "",
        "## Defectos de calidad intencionales",
        "",
        "Conteos exactos y disjuntos dentro de cada tabla (una fila tiene a lo sumo un defecto,",
        "salvo los NIT, donde la fila duplicada no tiene otro defecto). Los detecta el ETL (Tabla 13, INF-TRA-08).",
        "",
        "| Defecto | Cantidad | Detalle |",
        "|---|---:|---|",
        *[f"| `{k}` | {v} | {DESCRIPCION_DEFECTOS[k]} |" for k, v in DEFECTOS.items()],
        "",
        "Valores inválidos de estado usados: " + ", ".join(f"`{e!r}`" for e in ESTADOS_INVALIDOS) + ".",
        "",
        "## Catálogo de estados válidos",
        "",
        *[f"- `{ent}`: " + ", ".join(v) for ent, v in CATALOGO_ESTADOS.items()],
        "",
        "## Supuestos del generador",
        "",
        "- El estudiante de la práctica es un `usuario` con rol `estudiante`; los tutores empresariales son",
        "  usuarios con rol `tutor_empresarial` (el modelo inferido no define esas tablas).",
        "- `fecha_modificacion` existe solo en `proyecto_investigacion` y `practica`, para probar los dos caminos",
        "  de la carga incremental (por fecha y por huella de fila).",
        "- PII (`nombre_completo`, `documento`, `correo`) y `contrasena_hash` son ficticios.",
        "",
    ]
    ruta.write_text("\n".join(lineas), encoding="utf-8")


# ---------------------------------------------------------------------------
def cargar(datos: Datos, url: str) -> None:
    from sqlalchemy import MetaData, create_engine, text

    motor = create_engine(url)
    meta = MetaData()
    with motor.begin() as con:
        meta.reflect(bind=con, schema=ESQUEMA)
        con.execute(text(f"TRUNCATE {', '.join(f'{ESQUEMA}.{t}' for t in ORDEN_TABLAS)} CASCADE"))
        for nombre in ORDEN_TABLAS:
            filas = datos.tablas[nombre]
            tabla = meta.tables[f"{ESQUEMA}.{nombre}"]
            for i in range(0, len(filas), 5000):
                con.execute(tabla.insert(), filas[i : i + 5000])


def _literal(valor) -> str:
    """Literal SQL para valores generados por este módulo (no se usa con entradas externas)."""
    if valor is None:
        return "NULL"
    if isinstance(valor, bool):
        return "TRUE" if valor else "FALSE"
    if isinstance(valor, int | float):
        return repr(valor)
    if isinstance(valor, date | datetime):
        return f"'{valor.isoformat(sep=' ') if isinstance(valor, datetime) else valor.isoformat()}'"
    return "'" + str(valor).replace("'", "''") + "'"


def volcar_sql(datos: Datos, ruta: Path) -> None:
    with ruta.open("w", encoding="utf-8") as f:
        f.write(f"-- Datos sintéticos (semilla {SEMILLA}). Ejecutar después de ddl.sql.\nBEGIN;\n")
        for nombre in ORDEN_TABLAS:
            filas = datos.tablas[nombre]
            columnas = ", ".join(filas[0])
            for i in range(0, len(filas), 1000):
                valores = ",\n".join(
                    "(" + ", ".join(_literal(v) for v in fila.values()) + ")" for fila in filas[i : i + 1000]
                )
                f.write(f"INSERT INTO {ESQUEMA}.{nombre} ({columnas}) VALUES\n{valores};\n")
        f.write("COMMIT;\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--semilla", type=int, default=SEMILLA)
    parser.add_argument("--sql", type=Path, help="vuelca INSERT a este archivo en lugar de cargar en la BD")
    parser.add_argument("--resumen", action="store_true", help="solo imprime conteos")
    args = parser.parse_args(argv)

    datos = generar(args.semilla)
    print("Filas por tabla:")
    for tabla, n in datos.conteos().items():
        print(f"  {tabla:24s} {n:>7d}")
    print("Defectos inyectados (recontados):")
    for clave, n in contar_defectos(datos).items():
        print(f"  {clave:40s} {n:>4d}")
    if args.semilla == SEMILLA:
        escribir_defectos_md(datos, Path(__file__).with_name("defectos.md"))
    if args.resumen:
        return 0
    if args.sql:
        volcar_sql(datos, args.sql)
        print(f"SQL escrito en {args.sql}")
        return 0
    url = os.environ.get("DATABASE_URL_ADMIN")
    if not url:
        print("Defina DATABASE_URL_ADMIN (ver .env.example) o use --sql / --resumen.", file=sys.stderr)
        return 2
    cargar(datos, url)
    print("Carga completa.")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
