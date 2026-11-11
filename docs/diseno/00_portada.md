[Ver imagen sin leyenda](figuras/imagen_sin_leyenda_1.png)

Motor de Informes Estadísticos con IA por API en el Centro de Investigaciones UMB

Avance hasta la fase de diseño

Daniel Fernando Barragán Chía

Docente: Ing. Jader Jesús Jácome Solano

Supervisor externo: Ing. Héctor Vargas, Centro de Investigaciones UMB

Programa de Ingeniería de Software, Universidad Manuela Beltrán

Práctica Empresarial II

5 de noviembre de 2026

Tabla de contenido

Lista de tablas

Tabla 1. Articulación de la práctica con las áreas temáticas del programa	8

Tabla 2. Indicadores y metas de los objetivos específicos	14

Tabla 3. Fases de CRISP-DM distribuidas en los sprints de la práctica	15

Tabla 4. Tipos de datos presentes en el proyecto y su tratamiento	20

Tabla 5. Las cinco V de Big Data aplicadas al CIUMB	22

Tabla 6. Relación de las áreas de análisis de datos con el proyecto	25

Tabla 7. Tecnologías de soporte de Big Data y su equivalente en el diseño	29

Tabla 8. Técnicas estadísticas y de minería de datos del área analítica	30

Tabla 9. Aplicabilidad de las técnicas del capítulo al proyecto	34

Tabla 10. Descripción de las entidades del área de investigación (fuente 1)	42

Tabla 11. Descripción de las entidades del área de relación externa (fuente 1)	43

Tabla 12. Descripción de las entidades del área de usuarios y de la fuente 2	43

Tabla 13. Clasificación de los campos sensibles y su tratamiento en el ETL	44

Tabla 14. Decisión de diseño DA-01: dónde se almacena el datawarehouse	47

Tabla 15. Matriz de bus del datawarehouse	48

Tabla 16. Descripción de las dimensiones	49

Tabla 17. Descripción de las tablas de hechos	49

Tabla 18. Registro resumido de decisiones de arquitectura	54

Tabla 19. Tecnologías del área analítica y su licencia	55

Tabla 20. Campos de la especificación de informe (ciumb.spec/1.0)	56

Tabla 21. Reglas de compatibilidad y recomendación del tipo de gráfico	59

Tabla 22. Prompts de ejemplo y especificación que produce cada uno	63

Tabla 23. Pantallas del prototipo y requerimientos que cubren	68

Lista de figuras

Figura 1. Diagrama de causa y efecto del problema de generación de informes en el CIUMB	10

Figura 2. Diagrama de bloques del área analítica del motor de informes	36

Figura 3. Fuente 1, área de investigación: macroproyectos y proyectos de investigación (modelo inferido)	39

Figura 4. Fuente 1, área de relación externa: empresas, convenios, prácticas y consultorías (modelo inferido)	40

Figura 5. Fuente 1, área de usuarios y seguridad: Módulo 7 (modelo inferido)	40

Figura 6. Fuente 2: esquema rpt_ del servicio de informes	41

Figura 7. Constelación de hechos del datawarehouse lógico (esquema ana_)	46

Figura 8. Estrella de la tabla hecho_proyecto con sus dimensiones	47

Figura 9. Arquitectura general de la solución	52

Figura 10. Del prompt al informe: recorrido de una solicitud abierta	56

Figura 11. Diagrama de secuencia de una solicitud abierta, del prompt al informe	61

Figura 12. Ejemplo de paquete del contrato de datos para el prompt de la Figura 10	62

Figura 13. Especificación del ejemplo 1: torta de prácticas por programa (P2)	65

Figura 14. Especificación del ejemplo 2: mapa de calor de hitos atrasados con chi-cuadrado (P4)	66

Figura 15. Especificación del ejemplo 3: plantilla base INF-INV-02 modificada por el prompt (P6)	67

Figura 16. Mockup del asistente de informes en el chatbot	68

Figura 17. Mockup del tablero ejecutivo (INF-TRA-01)	70

Figura 18. Mockup del informe de ejecución presupuestal (INF-INV-02)	71

Figura 19. Mockup de analítica avanzada: pronóstico y segmentación	72

Figura 20. Mockup del estado del servicio y de la calidad de las cifras	73
