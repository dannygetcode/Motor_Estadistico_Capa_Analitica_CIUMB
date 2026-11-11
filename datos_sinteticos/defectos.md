# Datos sintéticos de la fuente 1

Generado por `datos_sinteticos/generar.py` (no editar a mano).
Semilla `20261111` · periodo 2019-01-01 a 2026-10-31 · Faker `es_CO`.

## Filas por tabla

| Tabla | Filas |
|---|---:|
| rol | 8 |
| usuario | 3.165 |
| registro_acceso | 45.000 |
| facultad_programa | 16 |
| linea_investigacion | 19 |
| macroproyecto | 48 |
| fase_macroproyecto | 179 |
| proyecto_investigacion | 640 |
| hito_entregable | 3.466 |
| integrante_proyecto | 2.575 |
| empresa | 260 |
| convenio | 328 |
| documento_convenio | 931 |
| practica | 2.791 |
| consultoria | 310 |
| factura_consultoria | 810 |
| consultor_consultoria | 797 |

## Defectos de calidad intencionales

Conteos exactos y disjuntos dentro de cada tabla (una fila tiene a lo sumo un defecto,
salvo los NIT, donde la fila duplicada no tiene otro defecto). Los detecta el ETL (Tabla 13, INF-TRA-08).

| Defecto | Cantidad | Detalle |
|---|---:|---|
| `proyecto_fin_antes_inicio` | 12 | proyecto_investigacion con fecha_fin < fecha_inicio |
| `practica_fin_antes_inicio` | 15 | practica con fecha_fin < fecha_inicio |
| `convenio_fin_antes_inicio` | 6 | convenio con fecha_fin < fecha_inicio |
| `empresa_nit_repetido` | 8 | empresas cuyo NIT copia el de otra empresa (filas adicionales con NIT duplicado) |
| `practica_sin_tutor_academico` | 18 | practica con id_tutor_academico NULL (tiene tutor empresarial) |
| `practica_sin_tutor_empresarial` | 22 | practica con id_tutor_empresarial NULL (tiene tutor académico) |
| `practica_sin_tutor_ninguno` | 6 | practica sin ningún tutor (ambos NULL) |
| `proyecto_estado_fuera_catalogo` | 10 | proyecto_investigacion.estado fuera de CATALOGO_ESTADOS |
| `practica_estado_fuera_catalogo` | 12 | practica.estado fuera de CATALOGO_ESTADOS |
| `convenio_estado_fuera_catalogo` | 5 | convenio.estado fuera de CATALOGO_ESTADOS |
| `proyecto_presupuesto_ejecutado_negativo` | 4 | proyecto_investigacion.presupuesto_ejecutado < 0 |
| `practica_sin_empresa` | 7 | practica con id_empresa NULL |
| `convenio_sin_fecha_fin` | 9 | convenio con fecha_fin NULL |

Valores inválidos de estado usados: `'En Ejecución'`, `'FINALIZADO'`, `'aprobado '`, `'pendiente_revision'`, `'N/A'`, `'activo?'`, `'cerrada'`.

## Catálogo de estados válidos

- `usuario`: activo, inactivo, bloqueado
- `macroproyecto`: activo, en_cierre, cerrado, suspendido
- `proyecto_investigacion`: formulado, en_validacion, aprobado, en_ejecucion, finalizado, cancelado
- `hito_entregable`: pendiente, entregado, vencido
- `empresa`: activa, inactiva
- `convenio`: vigente, vencido, en_renovacion, terminado
- `practica`: por_iniciar, en_curso, finalizada, cancelada
- `consultoria`: propuesta, en_ejecucion, finalizada, cancelada

## Supuestos del generador

- El estudiante de la práctica es un `usuario` con rol `estudiante`; los tutores empresariales son
  usuarios con rol `tutor_empresarial` (el modelo inferido no define esas tablas).
- `fecha_modificacion` existe solo en `proyecto_investigacion` y `practica`, para probar los dos caminos
  de la carga incremental (por fecha y por huella de fila).
- PII (`nombre_completo`, `documento`, `correo`) y `contrasena_hash` son ficticios.
