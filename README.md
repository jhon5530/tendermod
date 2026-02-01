
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

Proximos pasos
- Cambiar el modo de comparacion de indicadores para que la comparacion se haga punto por punto y no en prosa (ver chat GPT)
- Repetir este paso y ahora desplegar el caso de uso de experiencia.
- Una vez se tengan ambos casos operativos se deben afinar (Ej. Indicadores debe evaluar todos en una sola evaluacion) para que entreguen ls datos necesarios y guarden en disco la info para retomarla mas adelante.
- Generar una version 1 de una interfaz grafica que permita:
   - Cargar los archivos de la licitacion
   - Ejecutar el agente para que interpreta y devuelva los resultados esperados.
   - Dar formato a esa respuesta.


Mejoras
 - Quizas es buena idea hacer al menos 3 consultas y de las 3 escoger la respuesta que mas probabilidades o repeticiones tenga, debido a que no siempre da la misma respuesta