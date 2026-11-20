"""Identidad visual UMB compartida por gráficos y exportación (RF-15, RF-16; diseño 4.5).

Regla del diseño (4.5): el rojo institucional se usa para la marca (encabezados, navegación) y un azul oscuro
para los datos, de modo que los semáforos rojos no se confundan con la marca. Los valores hexadecimales son
PROVISIONALES hasta recibir el manual de marca de la UMB (D-27); cambiarlos aquí los cambia en todo el informe.
"""

from __future__ import annotations

ROJO_UMB = "#B0131E"
AZUL_DATOS = "#1F3A5F"
GRIS_TEXTO = "#333333"
GRIS_SUAVE = "#8C8C8C"
FONDO_TABLA = "#F2F2F2"

PALETA_DATOS: tuple[str, ...] = (
    AZUL_DATOS,
    "#4C78A8",
    "#72B7B2",
    "#9D755D",
    "#B279A2",
    "#54A24B",
    "#EECA3B",
    "#79706E",
)
"""Colores de las series, en orden. El primero es el azul de datos; ninguno es el rojo de la marca."""

ESCALA_CALOR = "Blues"
"""Mapa de color secuencial (Matplotlib y Plotly) para los mapas de calor."""

FUENTE = "DejaVu Sans"
"""Tipografía de los gráficos: viene con Matplotlib, así el PNG es igual en cualquier máquina."""

FUENTE_DOCUMENTO = "Arial"
"""Tipografía de DOCX, HTML y PDF (con respaldo sans-serif)."""

INSTITUCION = "Universidad Manuela Beltrán"
UNIDAD = "Centro de Investigaciones de la Universidad Manuela Beltrán (CIUMB)"
