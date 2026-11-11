"""Divide el documento de diseño (.docx) en archivos markdown por sección.

Herramienta de desarrollo (no forma parte del servicio). Uso:

    uv run --with python-docx python herramientas/dividir_diseno.py

Reglas:
- Cada encabezado (Heading 1/2/3) abre un fragmento; los fragmentos que solo tienen
  el título se fusionan con el siguiente. Resultado: un archivo por sección de
  nivel 3 donde existe y de nivel 2 donde no hay subsecciones.
- Tablas -> tablas markdown. Imágenes -> docs/diseno/figuras/figura_NN.png y en el
  texto el título, el enlace y una descripción tomada de
  herramientas/figuras_descripciones.json (bloque "> ..." que no cuenta como
  contenido original en la verificación de palabras).
- Al final imprime la verificación de palabras docx vs. markdown.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import unicodedata
from pathlib import Path

import docx
from docx.table import Table
from docx.text.paragraph import Paragraph

RAIZ = Path(__file__).resolve().parents[1]
DOCX = next((RAIZ / "docs" / "fuentes").glob("*.docx"))
SALIDA = RAIZ / "docs" / "diseno"
FIGURAS = SALIDA / "figuras"
DESCRIPCIONES = RAIZ / "herramientas" / "figuras_descripciones.json"

NS_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
NS_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def slug(texto: str, max_palabras: int = 5) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    texto = re.sub(r"[^a-zA-Z0-9 ]+", " ", texto).lower()
    vacias = {"de", "del", "la", "las", "el", "los", "y", "en", "para", "por", "a", "un", "una", "que"}
    palabras = [p for p in texto.split() if p not in vacias]
    return "_".join(palabras[:max_palabras]) or "seccion"


def numero_y_titulo(texto: str) -> tuple[str, str]:
    m = re.match(r"^\s*(\d+(?:\.\d+)*)\.?\s+(.*)$", texto)
    if m:
        return m.group(1), m.group(2)
    return "99", texto


def celda(texto: str) -> str:
    texto = texto.strip().replace("|", "\\|")
    return re.sub(r"\s*\n\s*", "<br>", texto)


def tabla_md(tabla: Table) -> str:
    filas: list[list[str]] = []
    previas: list = []
    for fila in tabla.rows:
        actuales = []
        textos = []
        ultimo = None
        for col, c in enumerate(fila.cells):
            if c._tc is ultimo:  # fusión horizontal: se omite la repetición
                continue
            ultimo = c._tc
            arriba = previas[len(actuales)] if len(actuales) < len(previas) else None
            actuales.append(c._tc)
            textos.append("" if c._tc is arriba else celda(c.text))  # fusión vertical
        previas = actuales
        filas.append(textos)
    ancho = max(len(f) for f in filas)
    filas = [f + [""] * (ancho - len(f)) for f in filas]
    lineas = ["| " + " | ".join(filas[0]) + " |", "|" + "---|" * ancho]
    lineas += ["| " + " | ".join(f) + " |" for f in filas[1:]]
    return "\n".join(lineas)


def imagenes(parrafo: Paragraph) -> list[str]:
    return [b.get(f"{NS_R}embed") for b in parrafo._p.iter(f"{NS_A}blip")]


def palabras_docx(documento) -> int:
    total = sum(len(p.text.split()) for p in documento.paragraphs)
    for t in documento.tables:
        vistos = set()
        for fila in t.rows:
            for c in fila.cells:
                if c._tc in vistos:
                    continue
                vistos.add(c._tc)
                total += len(c.text.split())
    return total


def palabras_md(texto: str) -> int:
    lineas = []
    for linea in texto.splitlines():
        if linea.startswith(">") or linea.startswith("[Ver "):
            continue  # descripciones y enlaces añadidos
        if re.fullmatch(r"\|(---\|)+", linea):
            continue
        linea = linea.replace("<br>", " ").replace("\\|", "")
        linea = re.sub(r"^#+\s|^- |\*\*|\|", " ", linea)
        lineas.append(linea)
    return sum(len(linea.split()) for linea in lineas)


def main() -> int:
    documento = docx.Document(str(DOCX))
    descripciones = json.loads(DESCRIPCIONES.read_text(encoding="utf-8")) if DESCRIPCIONES.exists() else {}
    # Limpieza acotada: solo se borra docs/diseno/figuras y se recrea.
    assert FIGURAS.parent == SALIDA and FIGURAS.name == "figuras" and SALIDA.parent.name == "docs"
    if FIGURAS.exists():
        shutil.rmtree(FIGURAS)
    FIGURAS.mkdir(parents=True)
    partes = documento.part.related_parts

    fragmentos: list[dict] = []  # {"nivel", "numero", "titulo", "lineas"}
    actual = {"nivel": 0, "numero": "00", "titulo": "Portada", "lineas": []}
    leyendas_pendientes: list[int] = []
    sin_leyenda: list[str] = []

    def emitir_figura(rid: str, numero: int, destino: list[str]) -> None:
        nombre = f"figura_{numero:02d}.png"
        (FIGURAS / nombre).write_bytes(partes[rid].blob)
        bloque = [f"[Ver figura {numero}](figuras/{nombre})", ""]
        desc = descripciones.get(str(numero), "PENDIENTE: describir la figura.")
        bloque += [f"> {linea}" if linea else ">" for linea in desc.splitlines()] + [""]
        destino.extend(bloque)

    for elemento in documento.element.body.iterchildren():
        etiqueta = elemento.tag.rsplit("}", 1)[-1]
        if etiqueta == "tbl":
            actual["lineas"] += [tabla_md(Table(elemento, documento)), ""]
            continue
        if etiqueta != "p":
            continue
        p = Paragraph(elemento, documento)
        estilo = p.style.name if p.style is not None else ""
        texto = p.text.strip()

        m = re.match(r"Heading (\d)", estilo)
        if m and texto:
            fragmentos.append(actual)
            numero, titulo = numero_y_titulo(texto)
            actual = {"nivel": int(m.group(1)), "numero": numero, "titulo": titulo, "lineas": []}
            actual["lineas"] += ["#" * int(m.group(1)) + " " + texto, ""]
            continue

        # En el documento la leyenda va ENCIMA de la imagen.
        for rid in imagenes(p):
            if leyendas_pendientes:
                emitir_figura(rid, leyendas_pendientes.pop(0), actual["lineas"])
            else:  # logo de portada u otra imagen sin leyenda
                nombre = f"imagen_sin_leyenda_{len(sin_leyenda) + 1}.png"
                (FIGURAS / nombre).write_bytes(partes[rid].blob)
                sin_leyenda.append(nombre)
                actual["lineas"] += [f"[Ver imagen sin leyenda](figuras/{nombre})", ""]

        if not texto:
            continue
        if estilo.startswith("Leyenda"):
            actual["lineas"] += [f"**{texto}**", ""]
            mf = re.match(r"Figura (\d+)", texto)
            if mf:
                leyendas_pendientes.append(int(mf.group(1)))
            continue
        if estilo == "List Paragraph":
            actual["lineas"] += [f"- {texto}", ""]
        else:
            actual["lineas"] += [texto, ""]
    fragmentos.append(actual)
    sin_figura = sin_leyenda + [f"leyenda Figura {n} sin imagen" for n in leyendas_pendientes]

    # Fusionar fragmentos que solo contienen su título con el siguiente.
    fusionados: list[dict] = []
    arrastre: list[str] = []
    for f in fragmentos:
        contenido = [x for x in f["lineas"][1:] if x.strip()]
        if not contenido and f["nivel"] > 0:
            arrastre += f["lineas"]
            continue
        f = dict(f)
        f["lineas"] = arrastre + f["lineas"]
        arrastre = []
        fusionados.append(f)

    for viejo in SALIDA.glob("*.md"):
        if viejo.name != "00_indice.md":
            viejo.unlink()

    generados = []
    total_md = 0
    for f in fusionados:
        if f["nivel"] == 0:
            nombre = "00_portada.md"
        elif f["numero"] == "99":
            nombre = "99_" + slug(f["titulo"]) + ".md"
        else:
            nombre = f"{f['numero']}_{slug(f['titulo'])}.md"
        texto = "\n".join(f["lineas"]).strip() + "\n"
        (SALIDA / nombre).write_text(texto, encoding="utf-8")
        total_md += palabras_md(texto)
        generados.append((nombre, palabras_md(texto)))

    total_docx = palabras_docx(documento)
    print("Archivos generados:", len(generados))
    for nombre, n in generados:
        print(f"  {nombre}: {n}")
    print(f"Palabras docx (párrafos + tablas sin duplicar fusiones): {total_docx}")
    print(f"Palabras en markdown (sin descripciones añadidas): {total_md}")
    print(f"Diferencia: {total_md - total_docx} ({(total_md - total_docx) / total_docx:.2%})")
    if sin_figura:
        print("Imágenes o leyendas sin emparejar:", sin_figura)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
