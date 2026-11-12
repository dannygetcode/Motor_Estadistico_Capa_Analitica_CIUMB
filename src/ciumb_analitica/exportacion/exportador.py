"""Ensamblado y exportación del informe: PDF, DOCX, XLSX, HTML y CSV con identidad UMB (RF-16, OE3).
Librerías: Jinja2 + WeasyPrint (HTML y PDF), python-docx, openpyxl y pandas (CSV).

Meta de OE3 (Tabla 2): 18 plantillas base x 5 formatos = 90 archivos que abren sin errores y con las cifras
del motor. Las cifras de las tablas salen de `InformeEnsamblado.tablas`; el texto sale de la narrativa ya
aprobada por el validador de cifras. El exportador no calcula ni redondea nada por su cuenta: formatea con
`validador_cifras.extraccion.formatear_numero`.
Pruebas: `tests/exportacion/test_exportador.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ciumb_analitica.contrato.modelos import Contrato
from ciumb_analitica.graficos.generador import Grafico
from ciumb_analitica.motor.resultado import PENDIENTE
from ciumb_analitica.spec.modelos import Formato
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
    raise NotImplementedError(PENDIENTE)


def nombre_archivo(informe: InformeEnsamblado, formato: Formato) -> str:
    """Nombre sugerido: `<base o 'informe'>_<AAAAMMDD de corte>_<8 primeros hex de la huella>.<ext>`, solo con
    letras, dígitos, guion y guion bajo (p. ej. `INF-INV-02_20261031_91c4e07b.pdf`)."""
    raise NotImplementedError(PENDIENTE)
