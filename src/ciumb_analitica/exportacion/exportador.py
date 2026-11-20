"""Ensamblado y exportación del informe: PDF, DOCX, XLSX, HTML y CSV con identidad UMB (RF-16, OE3).
Librerías: Jinja2 + WeasyPrint (HTML y PDF), python-docx, openpyxl y pandas (CSV).

Meta de OE3 (Tabla 2): 18 plantillas base x 5 formatos = 90 archivos que abren sin errores y con las cifras
del motor. Las cifras de las tablas salen de `InformeEnsamblado.tablas`; el texto sale de la narrativa ya
aprobada por el validador de cifras. El exportador no calcula ni redondea nada por su cuenta: formatea con
`validador_cifras.extraccion.formatear_numero`.
Pruebas: `tests/exportacion/test_exportador.py`.
"""

from __future__ import annotations

import base64
import io
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from jinja2 import Environment, select_autoescape

from ciumb_analitica.contrato.modelos import Contrato
from ciumb_analitica.contrato.pii import PATRONES_PII, ErrorPII, HallazgoPII
from ciumb_analitica.exportacion import identidad
from ciumb_analitica.graficos.generador import Grafico
from ciumb_analitica.spec.modelos import Formato
from ciumb_analitica.validador_cifras.extraccion import formatear_numero
from ciumb_analitica.validador_cifras.validador import Narrativa

MODO_CON_IA = "con_ia"
MODO_DEGRADADO = "degradado"

TIPOS_MIME = {
    Formato.PDF: "application/pdf",
    Formato.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    Formato.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    Formato.HTML: "text/html; charset=utf-8",
    Formato.CSV: "text/csv; charset=utf-8",
}


class FormatoNoDisponible(RuntimeError):  # noqa: N818 - nombre de dominio en español
    """El servidor no puede producir ese formato (p. ej. PDF sin las bibliotecas de WeasyPrint)."""


LEYENDA_DEGRADADO = "Texto generado con plantilla, sin IA (modo degradado, RF-11)."
LEYENDA_CON_IA = "Texto redactado con asistencia de IA; todas sus cifras se verificaron contra el motor."
PATRONES_NARRATIVA = ("correo", "nit")
"""En la narrativa solo se buscan correos y NIT: sus números ya pasaron el validador de cifras y un total como
«1.250.000» tiene la forma del patrón de documento (D-26). Título, anexo y tablas se revisan con la lista completa."""


@dataclass(frozen=True)
class InformeEnsamblado:
    """Todo lo que un formato necesita. Es lo que devuelve el paso 18 de la Figura 11.

    titulo: título del informe (nombre de la plantilla o resumen del prompt).
    contrato: paquete 2.0.0 (periodo, alcance, indicadores, advertencias, huella).
    narrativa: texto aprobado (`ResultadoFinal.narrativa`); modo: 'con_ia' o 'degradado' (RF-11).
    tablas: nombre -> DataFrame para mostrar y exportar. SIN columnas que empiecen por `_` y sin dimensiones
      que identifiquen personas.
    graficos: salida de `graficos.generar_grafico`.
    anexo: avisos y declaraciones (periodo por defecto, grupos suprimidos, gráfico sustituido, método).
    """

    titulo: str
    contrato: Contrato
    narrativa: Narrativa
    modo: str
    tablas: dict[str, pd.DataFrame] = field(default_factory=dict)
    graficos: tuple[Grafico, ...] = ()
    anexo: tuple[str, ...] = ()


_HUELLA = re.compile(r"(?:sha256:)?(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")


# --- Preparación común -------------------------------------------------------------------------------------------


def _revisar_pii(informe: InformeEnsamblado) -> None:
    hallazgos: list[HallazgoPII] = []

    def revisar(texto: str, ruta: str, patrones=tuple(PATRONES_PII)) -> None:
        texto = _HUELLA.sub("", texto)  # un SHA-256 no es un dato personal (como `huella_datos` en el contrato)
        for nombre in patrones:
            if PATRONES_PII[nombre].search(texto):
                hallazgos.append(HallazgoPII(ruta=ruta, patron=nombre))

    revisar(informe.titulo, "titulo")
    for i, linea in enumerate(informe.anexo):
        revisar(linea, f"anexo[{i}]")
    for s in informe.narrativa.secciones:
        revisar(s.texto, f"narrativa.{s.id}", PATRONES_NARRATIVA)
    for nombre, tabla in informe.tablas.items():
        revisar(str(nombre), f"tablas.{nombre} (nombre)")
        for columna in tabla.columns:
            revisar(str(columna), f"tablas.{nombre}.{columna} (columna)")
        for columna in tabla.select_dtypes(exclude="number").columns:
            for valor in tabla[columna].dropna().astype(str).unique():
                revisar(valor, f"tablas.{nombre}.{columna}")
    if hallazgos:
        raise ErrorPII(hallazgos)


def _revisar_tablas(informe: InformeEnsamblado) -> None:
    for nombre, tabla in informe.tablas.items():
        auxiliares = [str(c) for c in tabla.columns if str(c).startswith("_")]
        if auxiliares:
            raise ValueError(
                f"la tabla '{nombre}' trae columnas auxiliares que no se exportan: {', '.join(auxiliares)}"
            )


def _es_entera(serie: pd.Series) -> bool:
    return pd.api.types.is_integer_dtype(serie) or pd.api.types.is_bool_dtype(serie)


def _decimales_columna(serie: pd.Series) -> int:
    """Decimales con que se muestra una columna: los que necesita su valor más preciso (0, 1 o 2), para que
    365.0 y 412.6 se lean «365,0» y «412,6». No redondea más allá de lo que hace `formatear_numero`."""
    if _es_entera(serie):
        return 0
    valores = pd.to_numeric(serie, errors="coerce").dropna()
    if valores.empty:
        return 0
    return max(len(formatear_numero(float(v)).rpartition(",")[2]) if "," in formatear_numero(float(v)) else 0
               for v in valores)  # fmt: skip


def _celdas_texto(tabla: pd.DataFrame, *, miles: bool = True) -> list[list[str]]:
    """Tabla como texto en formato español (coma decimal). Sin `miles` no lleva punto de miles (CSV)."""
    columnas = []
    for nombre in tabla.columns:
        serie = tabla[nombre]
        if pd.api.types.is_numeric_dtype(serie) and not pd.api.types.is_bool_dtype(serie):
            d = _decimales_columna(serie)
            texto = [
                ""
                if pd.isna(v)
                else (formatear_numero(float(v), d) if miles else f"{float(v):.{d}f}".replace(".", ","))
                for v in serie
            ]
        else:
            texto = ["" if pd.isna(v) else str(v) for v in serie]
        columnas.append(texto)
    return [list(fila) for fila in zip(*columnas, strict=True)] if columnas else []


def _png_b64(grafico: Grafico) -> str:
    return base64.b64encode(grafico.png).decode("ascii")


def _secciones(informe: InformeEnsamblado) -> list[dict]:
    textos = {s.id: s.texto for s in informe.narrativa.secciones}
    return [
        {
            "id": s.id,
            "titulo": s.id.replace("_", " ").capitalize(),
            "parrafos": [linea for linea in textos.get(s.id, "").splitlines() if linea.strip()],
            "metodo": s.metodo,
            "advertencias": list(s.advertencias),
        }
        for s in informe.contrato.secciones
    ]


def _encabezado(informe: InformeEnsamblado) -> dict[str, str]:
    c = informe.contrato
    alcance = c.alcance.rol.value + (f" · facultad {c.alcance.facultad}" if c.alcance.facultad else "")
    return {
        "periodo": f"{c.periodo.desde.isoformat()} a {c.periodo.hasta.isoformat()}",
        "corte": c.periodo.corte.isoformat(),
        "alcance": alcance,
        "especificacion": c.especificacion.id
        + (f" (plantilla {c.especificacion.base})" if c.especificacion.base else ""),
        "huella": c.huella_datos,
        "leyenda": LEYENDA_DEGRADADO if informe.modo == MODO_DEGRADADO else LEYENDA_CON_IA,
    }


# --- HTML y PDF ---------------------------------------------------------------------------------------------------

_PLANTILLA_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ titulo }}</title>
<style>
  :root { --marca: {{ c.marca }}; --datos: {{ c.datos }}; --texto: {{ c.texto }}; --suave: {{ c.suave }}; }
  body { font-family: {{ c.fuente }}, "Helvetica Neue", Arial, sans-serif; color: var(--texto); margin: 0;
         background: #ffffff; line-height: 1.45; }
  header { background: var(--marca); color: #fff; padding: 18px 28px; }
  header .institucion { font-size: 12px; letter-spacing: .04em; text-transform: uppercase; opacity: .9; }
  header h1 { margin: 4px 0 0; font-size: 22px; }
  main { padding: 18px 28px 28px; max-width: 980px; }
  .meta { display: grid; grid-template-columns: max-content 1fr; gap: 2px 14px; font-size: 13px;
          border-left: 4px solid var(--datos); padding: 6px 12px; background: {{ c.fondo }}; }
  .meta dt { font-weight: bold; } .meta dd { margin: 0; }
  .leyenda { font-size: 12px; color: var(--suave); margin: 10px 0 0; font-style: italic; }
  h2 { color: var(--datos); border-bottom: 1px solid #ddd; padding-bottom: 4px; margin-top: 28px; font-size: 18px; }
  table { border-collapse: collapse; margin: 10px 0 18px; font-size: 13px; }
  th { background: var(--datos); color: #fff; text-align: left; padding: 6px 10px; }
  td { border-bottom: 1px solid #e5e5e5; padding: 5px 10px; }
  td.num { text-align: right; font-variant-numeric: tabular-nums; }
  figure { margin: 12px 0 22px; } figure img { max-width: 100%; height: auto; }
  figcaption { font-size: 12px; color: var(--suave); }
  .anexo { font-size: 12px; color: var(--suave); } .anexo li { margin: 2px 0; }
  .huella { font-family: monospace; word-break: break-all; }
</style>
</head>
<body>
<header>
  <div class="institucion">{{ institucion }} · {{ unidad }}</div>
  <h1>{{ titulo }}</h1>
</header>
<main>
  <dl class="meta">
    <dt>Periodo</dt><dd>{{ e.periodo }}</dd>
    <dt>Fecha de corte</dt><dd>{{ e.corte }}</dd>
    <dt>Alcance</dt><dd>{{ e.alcance }}</dd>
    <dt>Especificación</dt><dd>{{ e.especificacion }}</dd>
  </dl>
  <p class="leyenda">{{ e.leyenda }}</p>
  {% for s in secciones %}
  <section id="{{ s.id }}">
    <h2>{{ s.titulo }}</h2>
    {% for p in s.parrafos %}<p>{{ p }}</p>
    {% endfor %}
  </section>
  {% endfor %}
  {% for g in graficos %}
  <figure>
    <img alt="{{ g.titulo }}" src="data:image/png;base64,{{ g.b64 }}">
    <figcaption>{{ g.titulo }}. {{ g.fuente }}{% for n in g.notas %} {{ n }}{% endfor %}</figcaption>
  </figure>
  {% endfor %}
  {% for t in tablas %}
  <h2>{{ t.nombre }}</h2>
  <table>
    <thead><tr>{% for col in t.columnas %}<th>{{ col }}</th>{% endfor %}</tr></thead>
    <tbody>{% for fila in t.filas %}<tr>{% for celda in fila %}
      <td{% if t.numericas[loop.index0] %} class="num"{% endif %}>{{ celda }}</td>{% endfor %}</tr>
    {% endfor %}</tbody>
  </table>
  {% endfor %}
  <h2>Anexo metodológico</h2>
  <ul class="anexo">
    {% for s in secciones %}<li>Método ({{ s.titulo }}): {{ s.metodo }}</li>
    {% for a in s.advertencias %}<li>Advertencia: {{ a }}</li>{% endfor %}
    {% endfor %}
    {% for linea in anexo %}<li>{{ linea }}</li>
    {% endfor %}
    <li>Huella de los datos: <span class="huella">{{ e.huella }}</span></li>
  </ul>
</main>
</body>
</html>
"""

_JINJA = Environment(autoescape=select_autoescape(default=True, default_for_string=True))


def _html(informe: InformeEnsamblado) -> str:
    tablas = [
        {
            "nombre": nombre,
            "columnas": [str(c) for c in tabla.columns],
            "filas": _celdas_texto(tabla),
            "numericas": [
                pd.api.types.is_numeric_dtype(tabla[c]) and not pd.api.types.is_bool_dtype(tabla[c])
                for c in tabla.columns
            ],
        }
        for nombre, tabla in informe.tablas.items()
    ]
    graficos = [
        {"titulo": g.titulo, "fuente": g.fuente, "notas": g.notas, "b64": _png_b64(g)} for g in informe.graficos
    ]
    colores = {
        "marca": identidad.ROJO_UMB,
        "datos": identidad.AZUL_DATOS,
        "texto": identidad.GRIS_TEXTO,
        "suave": identidad.GRIS_SUAVE,
        "fondo": identidad.FONDO_TABLA,
        "fuente": identidad.FUENTE_DOCUMENTO,
    }
    return _JINJA.from_string(_PLANTILLA_HTML).render(
        titulo=informe.titulo,
        institucion=identidad.INSTITUCION,
        unidad=identidad.UNIDAD,
        c=colores,
        e=_encabezado(informe),
        secciones=_secciones(informe),
        graficos=graficos,
        tablas=tablas,
        anexo=informe.anexo,
    )


def _pdf(informe: InformeEnsamblado) -> bytes:
    try:
        from weasyprint import HTML  # importación diferida: necesita Pango/GTK del sistema
    except (ImportError, OSError) as e:
        raise FormatoNoDisponible(
            "el PDF no está disponible en este servidor: WeasyPrint no encuentra sus bibliotecas (Pango/GTK)"
        ) from e
    return HTML(string=_html(informe)).write_pdf()


# --- DOCX --------------------------------------------------------------------------------------------------------


def _docx(informe: InformeEnsamblado) -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt, RGBColor

    def rgb(hexa: str) -> RGBColor:
        return RGBColor.from_string(hexa.lstrip("#").upper())

    documento = Document()
    estilo = documento.styles["Normal"]
    estilo.font.name = identidad.FUENTE_DOCUMENTO
    estilo.font.size = Pt(10.5)
    for seccion_doc in documento.sections:
        seccion_doc.left_margin = seccion_doc.right_margin = Cm(2.2)
        cabecera = seccion_doc.header.paragraphs[0]
        cabecera.text = f"{identidad.INSTITUCION} · {identidad.UNIDAD}"
        cabecera.runs[0].font.size = Pt(8)
        cabecera.runs[0].font.color.rgb = rgb(identidad.ROJO_UMB)

    titulo = documento.add_heading(informe.titulo, level=0)
    for run in titulo.runs:
        run.font.color.rgb = rgb(identidad.ROJO_UMB)
    e = _encabezado(informe)
    for etiqueta, valor in (("Periodo", e["periodo"]), ("Fecha de corte", e["corte"]), ("Alcance", e["alcance"]),
                            ("Especificación", e["especificacion"])):  # fmt: skip
        p = documento.add_paragraph()
        p.add_run(f"{etiqueta}: ").bold = True
        p.add_run(valor)
    leyenda = documento.add_paragraph().add_run(e["leyenda"])
    leyenda.italic = True
    leyenda.font.color.rgb = rgb(identidad.GRIS_SUAVE)

    for s in _secciones(informe):
        encabezado = documento.add_heading(s["titulo"], level=1)
        for run in encabezado.runs:
            run.font.color.rgb = rgb(identidad.AZUL_DATOS)
        for parrafo in s["parrafos"]:
            documento.add_paragraph(parrafo)

    for g in informe.graficos:
        documento.add_picture(io.BytesIO(g.png), width=Cm(16))
        documento.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        nota = documento.add_paragraph(" ".join([f"{g.titulo}.", g.fuente, *g.notas]))
        nota.runs[0].font.size = Pt(8)

    for nombre, tabla in informe.tablas.items():
        documento.add_heading(str(nombre), level=2)
        celdas = _celdas_texto(tabla)
        t = documento.add_table(rows=1 + len(celdas), cols=len(tabla.columns))
        t.style = "Light Grid Accent 1"
        for j, columna in enumerate(tabla.columns):
            t.cell(0, j).text = str(columna)
        for i, fila in enumerate(celdas, start=1):
            for j, valor in enumerate(fila):
                t.cell(i, j).text = valor

    documento.add_heading("Anexo metodológico", level=1)
    for s in _secciones(informe):
        documento.add_paragraph(f"Método ({s['titulo']}): {s['metodo']}", style="List Bullet")
        for a in s["advertencias"]:
            documento.add_paragraph(f"Advertencia: {a}", style="List Bullet")
    for linea in informe.anexo:
        documento.add_paragraph(linea, style="List Bullet")
    documento.add_paragraph(f"Huella de los datos: {e['huella']}", style="List Bullet")

    salida = io.BytesIO()
    documento.core_properties.title = informe.titulo
    documento.core_properties.author = identidad.UNIDAD
    documento.save(salida)
    return salida.getvalue()


# --- XLSX --------------------------------------------------------------------------------------------------------

_INVALIDOS_HOJA = re.compile(r"[\\/*?:\[\]]")


def _nombre_hoja(nombre: str, usados: set[str]) -> str:
    base = _INVALIDOS_HOJA.sub("_", str(nombre)).strip() or "Tabla"
    base = base[:31]
    candidato, k = base, 2
    while candidato.lower() in {u.lower() for u in usados}:
        sufijo = f" ({k})"
        candidato, k = base[: 31 - len(sufijo)] + sufijo, k + 1
    usados.add(candidato)
    return candidato


def _valor_xlsx(valor):
    if valor is None or (isinstance(valor, float) and np.isnan(valor)) or valor is pd.NA or valor is pd.NaT:
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


def _xlsx(informe: InformeEnsamblado) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Informe"
    e = _encabezado(informe)
    negrita = Font(bold=True)
    filas = [
        ("Informe", informe.titulo),
        ("Institución", f"{identidad.INSTITUCION} · {identidad.UNIDAD}"),
        ("Periodo", e["periodo"]),
        ("Fecha de corte", e["corte"]),
        ("Alcance", e["alcance"]),
        ("Especificación", e["especificacion"]),
        ("Modo", e["leyenda"]),
    ]
    for s in _secciones(informe):
        filas.append((f"Método · {s['titulo']}", s["metodo"]))
        filas += [("Advertencia", a) for a in s["advertencias"]]
    filas += [("Anexo", linea) for linea in informe.anexo]
    filas.append(("Huella de los datos", e["huella"]))
    for fila in filas:
        hoja.append(list(fila))
    for celda in hoja["A"]:
        celda.font = negrita
    hoja.column_dimensions["A"].width = 26
    hoja.column_dimensions["B"].width = 90
    hoja["B1"].font = Font(bold=True, size=13, color=identidad.ROJO_UMB.lstrip("#"))

    relleno = PatternFill("solid", fgColor=identidad.AZUL_DATOS.lstrip("#"))
    usados = {"Informe"}
    for nombre, tabla in informe.tablas.items():
        h = libro.create_sheet(_nombre_hoja(nombre, usados))
        h.append([str(c) for c in tabla.columns])
        for celda in h[1]:
            celda.font = Font(bold=True, color="FFFFFF")
            celda.fill = relleno
        for fila in tabla.itertuples(index=False):
            h.append([_valor_xlsx(v) for v in fila])
        for j, columna in enumerate(tabla.columns, start=1):
            if pd.api.types.is_float_dtype(tabla[columna]):
                d = _decimales_columna(tabla[columna])
                formato = "#,##0" + ("." + "0" * d if d else "")
                for (celda,) in h.iter_rows(min_row=2, min_col=j, max_col=j):
                    celda.number_format = formato
        h.freeze_panes = "A2"
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


# --- CSV ---------------------------------------------------------------------------------------------------------


def _csv(informe: InformeEnsamblado) -> bytes:
    def bloque(tabla: pd.DataFrame) -> list[str]:
        def campo(texto: str) -> str:
            return f'"{texto.replace(chr(34), chr(34) * 2)}"' if any(c in texto for c in ';"\n\r') else texto

        lineas = [";".join(campo(str(c)) for c in tabla.columns)]
        lineas += [";".join(campo(v) for v in fila) for fila in _celdas_texto(tabla, miles=False)]
        return lineas

    lineas: list[str] = []
    for i, (nombre, tabla) in enumerate(informe.tablas.items()):
        if i:
            lineas += ["", str(nombre)]
        lineas += bloque(tabla)
    return ("\ufeff" + "\r\n".join(lineas) + "\r\n").encode("utf-8")


def exportar(informe: InformeEnsamblado, formato: Formato) -> bytes:
    """Devuelve el archivo del informe en el formato pedido.

    Contenido común (PDF, DOCX, HTML): encabezado con identidad UMB y título; periodo, fecha de corte y
    alcance; por cada sección, su texto, su tabla y su gráfico con título, ejes y fuente; anexo con método,
    advertencias y la huella de datos; en modo degradado, la leyenda «Texto generado con plantilla, sin IA».
      pdf   WeasyPrint sobre el mismo HTML. Empieza por `%PDF`.
      docx  python-docx; gráficos como imagen PNG. Es un ZIP con `word/document.xml`.
      xlsx  openpyxl; una hoja por tabla con los valores NUMÉRICOS (no texto) y una hoja «Informe» con
            periodo, alcance, advertencias y huella.
      html  documento autocontenido (CSS en línea, gráficos Plotly o PNG en base64).
      csv   la tabla principal en UTF-8 con BOM, separador `;` y coma decimal (lo que abre Excel en español);
            las demás tablas, a continuación, separadas por una línea en blanco y su nombre.
    Todos los textos pasan por el filtro de PII antes de escribirse (`contrato.pii.buscar_pii`).
    Lanza `ValueError` si una tabla trae columnas auxiliares (`_...`).
    """
    _revisar_tablas(informe)
    _revisar_pii(informe)
    formato = Formato(formato)
    if formato is Formato.HTML:
        return _html(informe).encode("utf-8")
    if formato is Formato.PDF:
        return _pdf(informe)
    if formato is Formato.DOCX:
        return _docx(informe)
    if formato is Formato.XLSX:
        return _xlsx(informe)
    return _csv(informe)


def nombre_archivo(informe: InformeEnsamblado, formato: Formato) -> str:
    """Nombre sugerido: `<base o 'informe'>_<AAAAMMDD de corte>_<8 primeros hex de la huella>.<ext>`, solo con
    letras, dígitos, guion y guion bajo (p. ej. `INF-INV-02_20261031_91c4e07b.pdf`)."""
    contrato = informe.contrato
    base = contrato.especificacion.base or "informe"
    huella = contrato.huella_datos.removeprefix("sha256:")[:8]
    nombre = f"{base}_{contrato.periodo.corte:%Y%m%d}_{huella}"
    return re.sub(r"[^A-Za-z0-9_-]", "_", nombre) + f".{Formato(formato).value}"
