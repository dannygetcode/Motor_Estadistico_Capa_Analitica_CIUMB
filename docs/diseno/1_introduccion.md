# 1. Introducción

El Centro de Investigaciones de la Universidad Manuela Beltrán (CIUMB) desarrolla un sistema de información para gestionar macroproyectos, proyectos de investigación, prácticas empresariales, convenios, consultorías, empresas y usuarios. Varios de sus siete módulos ya funcionan y otros siguen en construcción. Cada módulo guarda sus propios datos, y en conjunto acumulan la información que la dirección necesita convertir en indicadores para planear, hacer seguimiento y rendir cuentas.

Para aprovechar esos datos, el centro pidió incorporar un chatbot con inteligencia artificial (IA) que entregue informes estadísticos y gráficos a partir de una solicitud en lenguaje natural. En la reunión de inicio, la coordinación de práctica fijó dos condiciones. El modelo de IA se consume por API y su costo debe ser cero, y el sistema debe pasar de un proveedor gratuito a otro cuando alguno falle o agote su cuota. También indicó que la práctica debía orientarse a la ciencia de datos, al procesamiento de volúmenes de información y a la analítica descriptiva, predictiva o prescriptiva.

Este documento de ingeniería corresponde a la práctica de Daniel Fernando Barragán Chía y cubre el área analítica del chatbot. El proceso de extracción y organización de los datos, la capa semántica y el validador de las especificaciones de informe, el compilador de consultas, el motor estadístico, el módulo de machine learning, el generador de gráficos, la exportación de los informes, el contrato de datos con la capa de IA y el validador de cifras. La interfaz conversacional, la interpretación del prompt, el orquestador de proveedores de IA, la seguridad y la gobernanza de la IA están a cargo de la práctica complementaria de Laura Valentina Maldonado Pérez, y la integración al sistema del CIUMB corresponde al equipo de mantenimiento, conformado por Juan Stiven Castro Chaves y Manuel Ernesto Bonilla Muñoz.

El documento llega hasta la fase de diseño, como lo pide la actividad 3 del aula. El capítulo 1 presenta el problema, la justificación, los objetivos y el diseño metodológico. El capítulo 2 reúne el marco teórico de Big Data y analítica de datos, y el capítulo 3 las técnicas y tecnologías de minería de datos y de opinión. El capítulo 4 contiene el análisis y el diseño de las estructuras de datos, incluido el diseño abierto de los informes con diez prompts de ejemplo. El diagrama de bloques, los modelos de las fuentes, el modelo del datawarehouse, la arquitectura general y el diseño de los tableros. Cada sección teórica cierra con su aplicación al caso del CIUMB, para que el lector vea qué se toma de cada concepto y qué se descarta.

La Tabla 1 relaciona la práctica con las áreas de conocimiento que definió el comité curricular del programa de Ingeniería de Software para las prácticas empresariales (Universidad Manuela Beltrán, 2020).

**Tabla 1. Articulación de la práctica con las áreas temáticas del programa**

| Área | Competencia del área | Aporte de la práctica |
|---|---|---|
| Analítica de datos (principal) | Analiza, diseña y construye soluciones analíticas en ciencia de datos según las necesidades empresariales y su aplicabilidad en los ecosistemas analíticos. | Proceso ETL, datawarehouse lógico, motor estadístico (descriptiva, series de tiempo, inferencia), machine learning (pronóstico, anomalías, segmentación), gráficos y validador de cifras. |
| Desarrollo de software (apoyo) | Desarrolla soluciones de software que cumplen los requerimientos y facilitan el manejo efectivo de la información. | Servicio de informes con API REST, contrato de datos versionado, exportación a PDF, DOCX, XLSX, HTML y CSV, e integración con el sistema del CIUMB. |

Fuente: Elaboración propia a partir de Universidad Manuela Beltrán (2020).
