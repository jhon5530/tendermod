
Actividades ejecutadas
- (08-01-25) Se desplego el proyecto con BPS (poetry + github (local + cloud rep) + dotenv) y se realizo prueba de funcionamiento de la correcta importacion de los modulos.
- (12-01-25) Se movio todo el codigo de indicadores para visual code.
- (17-02-25) Se realizo: 
   - Pruebas con diferentes PDFs (Funciona perfecto con K de 2)
   - Correccion de info en cache (Se creo un flujo para ingesta y otro para consulta)
   - Correccion de contexto (Unicamente veia el ultimo de los K)
   - Adiciono el agente SQL con funcion de cargue
   - Actualizacion de version de langchain y otras con refactoring.
- (24-01-26)Adicionar la logica para comparar los valores y terminar el caso de uso de experiencia completo
- (31-01-26) Se realizo la adicion de experiencia pero unicamente:
   - Ingesta de datos a db.
   - Chunking y cargue a base de datos vectorial
   - Se probo y funciona muy bien para traer objetos similares
- (07-02-26)
 - Adicionar el query especifico para que lea la experiencia en los pliegos y entregue un JSON
 - Se creo un borrador de Script para que revise en base a la info el cumplimiento.
- (15-03-26) Usando Claude code se termino track 1 y 2
- (22-03-26) 
 - Correccion de errores en interpretacion de presupuesto.
 - Creacion de interfaz grafica
- (08-04-26)  Se realizo ajuste de subrequisitos para evaluar experiencias especificas puntuales
- (01-05-26)  Ajustes a extraccion, afinamiento de extraccion y de resultados en Excel.
- (09-05-26) Se realizo correccion de errores de extraccion, se cargaron perfiles, se creo un modulo de evaluacion de equipo (manual tipo Chatbot) y se genero un prompt de auditoria, tambien se genero un archivo de arquitectura con Cowork para mejorar la extraccion y que sea mas parecida a lo que es Claude Cowork, pero no se ha evaluado ni implementado
- (10-05-26) Se incio proceso de validacion de auditoria pero se encuentra:
   - Gran parte de la informacion encontrada no es relevante.
   - Falta orden en los capitulos.
   - Si es informacion util para generar un resumen de los requerimientos.
   - La informacion de Experiencia e indicadores es muy relevante y se encuentra organizada (ANE)
   - Mejoras:
      - Plantear una organizacion de los capitulos y/o extratos relevantes para temas particulares, (Ej. Equipo de trabajo)
      - Para estos temas particulares hacer un nuevo flujo de extraccion de informacion literal (no LLM,extraccion pura de Texto), con el fin de organizar un documento expecifico de este requerimiento y sobre esto por medio de un LLM organizar en un schema especifico los requerimientos de personal, por perfil identificar:
         - Tipo de perfil
         - Cantidad
         - Experiencia laboral requerida:
            - Años
            - Tipo de requerimiento.
         - Estudios academicos (rama de la ingenieria, especializacion, si es o no Afin)
         - Certificaciones
         - Requerimiento literal
Proximos pasos
- Validar la auditoria y en base a esto realizar mejoras a la extraccion.
- Mejorar la evaluacion del equipo de trabajo y adicionar un modulo de extraccion de equipo basado en los requisitos generales para evaluar el equipo.
   
- Validar Fase 3 (Cargar mas archivos):
   - Generar una version 1 de una interfaz grafica que permita:
      - Cargar los archivos de la licitacion
      - Ejecutar el agente para que interpreta y devuelva los resultados esperados.


Mejoras
 - Quizas es buena idea hacer al menos 3 consultas y de las 3 escoger la respuesta que mas probabilidades o repeticiones tenga, debido a que no siempre da la misma respuesta.
 - Cambiar el modo de comparacion de indicadores para que la comparacion se haga punto por punto y no en prosa (ver chat GPT), esto mejorara el resultado que aveces da resultados inesperados
 - Mejorar uso de tokens no ingestando siempre