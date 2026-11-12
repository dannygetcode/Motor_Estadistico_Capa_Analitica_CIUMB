"""exportacion.exportador (RF-16, RF-11, OE3): cinco formatos que abren y traen las cifras del motor."""

from __future__ import annotations

import io
import zipfile

import openpyxl
import pandas as pd
import pytest
from docx import Document

from ciumb_analitica.contrato.modelos import cargar_contrato
from ciumb_analitica.exportacion import exportador
from ciumb_analitica.spec.modelos import Formato
from ciumb_analitica.validador_cifras.plantilla import plantilla_por_defecto
from ciumb_analitica.validador_cifras.validador import validar_narrativa
from tests.conftest import DIR_FIXTURES, PENDIENTE, leer_json

pytestmark = PENDIENTE

CONTRATO = cargar_contrato(leer_json(DIR_FIXTURES / "contrato_p03.json"))
TABLA = pd.DataFrame({"anio": [2025, 2026], "facturacion_ene_oct": [365.0, 412.6], "consultorias": [104, 118]})
ANEXO = ("Método: suma mensual.", "El periodo se limita al 2026-10-31, último mes cerrado.")


def _informe(modo=exportador.MODO_DEGRADADO, tablas=None) -> exportador.InformeEnsamblado:
    return exportador.InformeEnsamblado(
        titulo="Facturación de consultorías",
        contrato=CONTRATO,
        narrativa=plantilla_por_defecto(CONTRATO),
        modo=modo,
        tablas={"Facturación": TABLA} if tablas is None else tablas,
        anexo=ANEXO,
    )


def test_pdf():
    try:
        import weasyprint  # noqa: F401
    except (ImportError, OSError):  # en Windows, WeasyPrint necesita las bibliotecas GTK
        pytest.skip("WeasyPrint no puede cargar sus bibliotecas nativas en esta máquina")
    pdf = exportador.exportar(_informe(), Formato.PDF)
    assert pdf.startswith(b"%PDF") and pdf.rstrip().endswith(b"%%EOF") and len(pdf) > 3000


def test_docx_abre_y_trae_titulo_texto_y_tabla():
    archivo = exportador.exportar(_informe(), Formato.DOCX)
    assert zipfile.ZipFile(io.BytesIO(archivo)).testzip() is None
    documento = Document(io.BytesIO(archivo))
    texto = "\n".join(p.text for p in documento.paragraphs)
    assert "Facturación de consultorías" in texto and "412,6" in texto and "sin IA" in texto
    celdas = [c.text for t in documento.tables for fila in t.rows for c in fila.cells]
    assert "412,6" in celdas and "118" in celdas


def test_xlsx_guarda_numeros_no_texto():
    archivo = exportador.exportar(_informe(), Formato.XLSX)
    libro = openpyxl.load_workbook(io.BytesIO(archivo))
    assert libro.sheetnames == ["Informe", "Facturación"]
    hoja = libro["Facturación"]
    filas = list(hoja.iter_rows(values_only=True))
    assert filas[0] == ("anio", "facturacion_ene_oct", "consultorias")
    assert filas[1:] == [(2025, 365.0, 104), (2026, 412.6, 118)]
    assert all(isinstance(v, (int, float)) for fila in filas[1:] for v in fila)
    resumen = " ".join(str(c) for fila in libro["Informe"].iter_rows(values_only=True) for c in fila if c)
    assert CONTRATO.huella_datos in resumen and "2026-10-31" in resumen


def test_html_autocontenido_y_con_cifras_verificables():
    html = exportador.exportar(_informe(), Formato.HTML).decode("utf-8")
    assert html.lstrip().lower().startswith("<!doctype html") and "</html>" in html
    assert "Facturación de consultorías" in html and "412,6" in html and CONTRATO.huella_datos in html
    assert 'src="http' not in html and 'href="http' not in html  # sin recursos externos
    assert "<script src" not in html


def test_csv_para_excel_en_espanol():
    crudo = exportador.exportar(_informe(), Formato.CSV)
    assert crudo.startswith(b"\xef\xbb\xbf")  # BOM UTF-8
    lineas = crudo.decode("utf-8-sig").splitlines()
    assert lineas[0] == "anio;facturacion_ene_oct;consultorias"
    assert lineas[1:3] == ["2025;365,0;104", "2026;412,6;118"]


@pytest.mark.parametrize("formato", [Formato.DOCX, Formato.HTML])
def test_modo_degradado_se_declara_y_con_ia_no(formato):
    def texto(modo):
        archivo = exportador.exportar(_informe(modo), formato)
        if formato is Formato.HTML:
            return archivo.decode("utf-8")
        return "\n".join(p.text for p in Document(io.BytesIO(archivo)).paragraphs)

    assert "sin IA" in texto(exportador.MODO_DEGRADADO)
    assert "sin IA" not in texto(exportador.MODO_CON_IA)


def test_el_texto_exportado_sigue_pasando_el_validador_de_cifras():
    html = exportador.exportar(_informe(), Formato.HTML).decode("utf-8")
    cuerpo = html[html.index("<body") :]
    seccion = CONTRATO.secciones[0].id
    narrativa = plantilla_por_defecto(CONTRATO).secciones[0].texto
    assert all(linea in cuerpo for linea in narrativa.splitlines()[:1])
    assert validar_narrativa({seccion: narrativa}, CONTRATO).aprobado


@pytest.mark.parametrize("columna", ["_n_personas", "_persona", "_registro"])
def test_las_columnas_auxiliares_no_se_exportan(columna):
    con_auxiliar = {"Facturación": TABLA.assign(**{columna: 1})}
    with pytest.raises(ValueError, match=columna):
        exportador.exportar(_informe(tablas=con_auxiliar), Formato.XLSX)


def test_nombre_de_archivo():
    nombre = exportador.nombre_archivo(_informe(), Formato.PDF)
    assert nombre == f"informe_20261031_{CONTRATO.huella_datos.removeprefix('sha256:')[:8]}.pdf"
    assert exportador.nombre_archivo(_informe(), Formato.XLSX).endswith(".xlsx")


def test_tipos_mime_de_los_cinco_formatos():
    assert set(exportador.TIPOS_MIME) == set(Formato)
    exportador.exportar(_informe(), Formato.CSV)
