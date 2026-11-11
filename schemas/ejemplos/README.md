# Ejemplos transcritos del diseño (Figuras 12–15)

Transcripción literal de las figuras de la sección 4.4.3–4.4.4. Son **ejemplos**, no JSON Schema.
JSON no admite comentarios: los comentarios `//` de las figuras se conservan aquí.

| Archivo | Figura | Comentarios de la figura |
|---|---|---|
| `fig12_contrato_p_fig10.json` | 12. Paquete del contrato de datos para el prompt de la Figura 10 | `huella_datos`: "sin nombres, documentos, correos ni NIT". La huella aparece **truncada** en la figura (`91c4…e07b`); no es un SHA-256 válido. |
| `fig13_spec_p2_torta_practicas.json` | 13. Ejemplo 1: torta de prácticas por programa (P2) | `alcance`: "lo agrega el backend". Validación: 9 programas > 6 sectores → los 4 menores se agrupan en "Otros" y se avisa. |
| `fig14_spec_p4_calor_hitos_chi2.json` | 14. Ejemplo 2: mapa de calor de hitos atrasados con chi-cuadrado (P4) | `metricas`: "razón: no aditiva". `periodo`: "T4 incompleto: se excluye". Validación: celdas con frecuencia esperada < 5 → se advierte junto al valor p (RNF-13). |
| `fig15_spec_p6_plantilla_inf_inv_02.json` | 15. Ejemplo 3: plantilla base INF-INV-02 modificada por el prompt (P6) | `origen/base`: "punto de partida opcional"; `metricas`, `periodo`, `analisis`: "heredado (de la base)"; `filtros`: "tomado del prompt"; `grafico`: "el prompt manda". Validación: n = 9 proyectos < 20 → el histograma se dibuja con aviso de muestra pequeña. |

Observaciones: el contrato usa la clave `"contrato"` mientras las specs usan `"esquema"`; la spec de la
Figura 13 omite `periodo` (usa un filtro por `periodo_academico`); la Figura 15 no incluye `dimensiones`.
