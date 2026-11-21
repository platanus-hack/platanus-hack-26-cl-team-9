# Pitch ideas

*
*
*
*
*
*
*
* El problema del milenio, cuando Navier Stokes llega a la singularidad con esta forma tan extraña, es porque miles de agentes probaron distintas configuraciones hasta encontrar la adecuada. 


* Las pérdidas por el 25 de Febrero se estiman en US$ 984 millones de dólares.

[1] https://www.revistaei.cl/estudio-estima-las-perdidas-economicas-generadas-por-el-blackout-del-25-de-febrero/


## Ideas momentos wow:

* Mostrar el apagón del 25F
* Cortar la luz (?)
* 


## Beneficios de este proyecto

* Ayuda a evitar que una falla local se vuelva un apagón nacional
* Reduce pérdidas económicas como los US$ 984 millones del 25F
* Indica dónde invertir para obtener más resiliencia
* Muestra combinaciones de costo vs resiliencia y encuentra los mejores equilibrios
* Encuentra la mejor combinación de medidas para un presupuesto dado
* Calcula la inversión mínima que evita un apagón nacional
* Pone precio a la energía no suministrada
* Traduce un ciberataque a su consecuencia física
* Apoya los planes de continuidad de la Ley 21.663
* Identifica las defensas que no pueden fallar
* Permite probar la resistencia de sistemas futuros
* Democratiza el acceso a la simulación de la red
* Mejora las observaciones a los informes del Coordinador
* Genera confianza con un modelo validado y fuentes citadas
* Explica la red eléctrica a cualquier persona
* Da evidencia al periodismo ante el próximo apagón
* Sirve para formar estudiantes y equipos de ciberseguridad
* mejoras 

### Detalle de cada beneficio

**1. Evitar que una falla local se vuelva un apagón nacional.**
Sub50 no evita apagones por sí solo. Muestra qué medida habría contenido la cascada (más desconexión automática de carga, baterías rápidas en una isla o un esquema de defensa terminado) para que quien decide la pida o la priorice. El 25F empezó con una sola línea doble de 500 kV entre Atacama y Coquimbo y terminó con el país entero sin luz, de Arica a Chiloé.

**2. Reducir pérdidas económicas.**
Las pérdidas del 25F se estiman en US$ 984 millones [1]. Si una medida evita o acorta un evento así, el ahorro se mide en cientos de millones de dólares. El simulador permite comparar el costo de la medida con el costo del apagón que evita.

**3. Indicar dónde invertir.**
El simulador compara alternativas sobre el mismo escenario. Por ejemplo, calcula cuántos MW de baterías rápidas necesita una isla para no colapsar. Así la inversión va a la medida que contiene la falla con menos recursos.

**4. Mostrar combinaciones de costo vs resiliencia y encontrar los mejores equilibrios.**
Cada combinación de medidas (MW de baterías por isla, ajuste de la desconexión automática de carga, esquemas de defensa activos) tiene un costo y un resultado: personas sin luz, energía no suministrada y si la red sobrevive o colapsa. Si se simulan muchas combinaciones sobre los mismos escenarios, se puede dibujar una curva de costo vs resiliencia. Los mejores equilibrios son las combinaciones donde no existe otra más barata que proteja igual o mejor. Todo lo demás en el gráfico es gastar de más o proteger de menos.

**5. Encontrar la mejor combinación para un presupuesto dado.**
La pregunta se da vuelta: "con US$ X millones, ¿qué combinación deja menos gente sin luz?". Esto sirve a un regulador que debe elegir qué exigir, o a una empresa que debe decidir dónde poner sus baterías. También muestra desde qué punto invertir más casi no mejora la resiliencia.

**6. Calcular la inversión mínima que evita un apagón nacional.**
Para un escenario como el 25F, el simulador busca el punto donde la red deja de colapsar. Por ejemplo, desde cuántos MW de baterías rápidas en una isla el apagón total se convierte en un evento local. Comparar esa inversión con los US$ 984 millones del 25F da un argumento directo para el pitch y para quien decide.

> Nota sobre los beneficios 4 a 6: los costos de las medidas (por ejemplo, US$ por MW de batería) son valores asumidos.

**7. Poner precio a la energía no suministrada.**
La tarjeta de consecuencias entrega personas sin luz, MW desconectados, energía no suministrada y su costo para una duración editable. Una discusión técnica se convierte en una cifra que entiende un directorio, un ministerio o un juez.

**8. Traducir un ciberataque a su consecuencia física.**
El usuario elige el efecto del ataque (plantas o líneas fuera de servicio, defensas que no actúan, pérdida de control) y ve cuánta gente queda sin luz y por cuánto tiempo. El caso es real: en agosto de 2026 un ciberataque dejó fuera de servicio la planta solar Huatacondo (103 MW) y sus baterías en Tarapacá. Sub50 modela el efecto, nunca la técnica del ataque.

**9. Apoyar los planes de continuidad de la Ley 21.663.**
La ley obliga a los operadores de importancia vital a mantener planes de continuidad. Sub50 les da escenarios concretos con consecuencias medidas para dimensionar esos planes. También sirve a la ANCI y al área de ciberseguridad del Coordinador para estimar el impacto de un incidente.

**10. Identificar las defensas que no pueden fallar.**
El simulador muestra qué defensas deben seguir funcionando y cuánta generación simultánea puede perder la red sin colapsar. La protección se concentra donde un fallo convierte un evento local en un apagón.

**11. Probar la resistencia de sistemas futuros.**
Los escenarios incluyen la red de 2026 con mucha generación solar al mediodía. Se puede evaluar cómo responde la red con nuevas líneas, plantas o baterías antes de construirlas, y no después del primer apagón.

**12. Democratizar el acceso a la simulación de la red.**
Hoy solo el Coordinador simula fallas, con software comercial con licencia (DIgSILENT PowerFactory), y publica los resultados una vez al año en PDFs de más de 100 páginas. Sub50 corre en el navegador, es abierto y responde en un segundo.

**13. Mejorar las observaciones a los informes del Coordinador.**
Analistas de la CNE, la SEC y el Ministerio de Energía, académicos y consultoras pueden respaldar sus comentarios con simulaciones propias, en vez de depender solo de las conclusiones del operador.

**14. Generar confianza con un modelo validado.**
El modelo se valida como código contra los resultados publicados del 25F y los estudios anuales de defensa del Coordinador. Cada número que muestra la interfaz lleva su fuente o una marca de supuesto, y la tabla de validación compara nuestro valor con el publicado.

**15. Explicar la red eléctrica a cualquier persona.**
La animación de la cascada muestra el flujo que se redistribuye, las líneas que se sobrecargan, el país que se divide en dos islas y las ciudades que se apagan. La cadena de eventos se narra en español simple. Ver el 25F en el mapa explica por qué una falla en Atacama dejó sin luz a Chiloé.

**16. Dar evidencia al periodismo.**
Ante el próximo evento, el periodismo de datos puede reconstruir la cadena de fallas y explicar qué la habría contenido, con números y fuentes en lugar de especulación.

**17. Formar estudiantes y equipos de ciberseguridad.**
Universidades y equipos de continuidad pueden practicar con escenarios realistas sin tocar la red real, que no se puede probar en la vida real.

> Nota para el pitch: ningún usuario ha sido entrevistado todavía. Los beneficios describen el valor esperado, no demanda validada (`idea.md` sección 3.1).Simulación de infraestructura crítica en expansión: nuevos datacenters, territorios, etc
* 