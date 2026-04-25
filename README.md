
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






Proximos pasos
- 0. Validar:
       - [ ] (TM) Fase 1:
        - [ ] Orden por valor para los que cumplan umbral (Proceso FNA Rafa)
        - [ ] Si hay experiencia general?
        - [ ] Si hay experiencias especificas?
        - [ ] Si son las mismas?
        - [ ] No funcionan esas experiencias especificas
        - [ ] Análisis semántico.
- 1. Adicionar fragmentos de texto de experiencia que se tuvo en cuenta para la evaluacion, junto con sus paginas. Esto para que el humano que revise la experiencia tenga rapidamente un punto de comparacion del requerimiento textual del pliego vs el resultado de la evaluacion, esto tambien adicionarlo al .txt descargable.
- 2. Corregir errores como:
 - No funciona la funcion de evaluar objeto (Pareciera que no busca los resultados mas cercanos al objeto sino que parte por los de mayor valor y cumplimiento de codigos).
 - No funciona si no evaluo todos los pasos.
 - Adicion de umbral:
- 3. Adicionar modulo requerimientos generales.
- 4. Entregar un informe general en un word de cumplimiento.
 

- Formato de valores en la interfaz grafica


 - No esta almacenando la informacion cuando edito sobre el paso 2, eso quiere decir que cuando me devuelvo sigue con la info original.



- Generar una version 1 de una interfaz grafica que permita:
   - Cargar los archivos de la licitacion
   - Ejecutar el agente para que interpreta y devuelva los resultados esperados.





Mejoras
 - Quizas es buena idea hacer al menos 3 consultas y de las 3 escoger la respuesta que mas probabilidades o repeticiones tenga, debido a que no siempre da la misma respuesta.
 - Cambiar el modo de comparacion de indicadores para que la comparacion se haga punto por punto y no en prosa (ver chat GPT), esto mejorara el resultado que aveces da resultados inesperados
 - Mejorar uso de tokens no ingestando siempre