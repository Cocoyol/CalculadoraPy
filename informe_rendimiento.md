# Informe de rendimiento

Fecha: 2026-03-15

## Alcance

Se realizó una revisión completa del flujo de cálculo, formateo y scroll horizontal de resultados en la calculadora científica de precisión arbitraria.

Objetivos de la revisión:

- detectar cuellos de botella cuando el usuario ya ha solicitado varios cientos de dígitos adicionales;
- medir el costo del cálculo incremental con una expresión compleja;
- medir el costo del scroll sintético sobre resultados largos;
- documentar cambios recomendados, con archivos, líneas y el aspecto que mejora.

No se aplicaron cambios al código en esta etapa. Este documento describe cambios recomendados.

## Expresión usada en la evaluación

```text
sqrt(log(atan(sin(0.8π)*10000))*3570!/cos(0.4π))^ln(25!/tan(7.1e))
```

## Resumen ejecutivo

La evaluación numérica de la expresión de prueba no mostró un problema grave en los tamaños de precisión ensayados. El cuello de botella dominante aparece en el renderizado del scroll horizontal del resultado una vez que ya existen cientos de dígitos cargados.

El principal problema no es el motor de cálculo sino la recomputación repetida de texto derivado dentro de `ResultDisplay`, especialmente en los cambios de estado por desplazamiento.

## Resultados de medición

### 1. Evaluación y expansión de precisión

Mediciones obtenidas sobre `ArbitraryPrecisionCalculatorEngine`:

| Operación | Tiempo aprox. | Longitud del resultado |
| --- | ---: | ---: |
| `evaluate()` inicial | `0.0107 s` | `27` |
| `request_more_precision()` 1 | `0.0158 s` | `147` |
| `request_more_precision()` 2 | `0.0420 s` | `267` |
| `request_more_precision()` 3 | `0.0364 s` | `387` |

Conclusión:

- el costo del cálculo está dominado por `mpmath`, en especial por factorial/gamma para la expresión usada;
- en este escenario, el motor aún responde rápido;
- no se detectó aquí el principal problema de rendimiento percibido por el usuario.

### 2. Scroll horizontal sobre resultados largos

Se midieron `700` pasos sintéticos de `_advance_scientific(1)` sobre resultados ya expandidos:

| Caso | Longitud aprox. | Tiempo aprox. |
| --- | ---: | ---: |
| Resultado de la expresión compleja | `987` | `0.1048 s` |
| Fracción larga (`5/7`) | `980` | `0.1644 s` |

Conclusión:

- el tiempo por scroll ya se concentra de forma clara en el renderizado del widget;
- las fracciones largas son especialmente sensibles porque disparan más lógica de transición entre decimal plano y notación científica;
- el costo crece por recomputaciones repetidas dentro del mismo evento de scroll.

## Hallazgos y cambios recomendados

### 1. Caché de dígitos virtuales para desplazamiento

Severidad: alta

Archivo y líneas:

- [calculator_ui.py](calculator_ui.py#L765-L777)

Código implicado:

- `_virtual_digits_for_shifting()` en [calculator_ui.py](calculator_ui.py#L765-L777)

Problema:

- este método reconstruye repetidamente la cadena virtual de dígitos;
- cuando el valor requiere completar cola con ceros, ejecuta `digits + ("0" * scale)` en cada llamada;
- esa cadena se vuelve a calcular muchas veces durante un mismo paso de scroll.

Evidencia:

- aparece como uno de los hot paths del perfil del scroll;
- es invocado indirectamente desde múltiples helpers usados por `_advance_scientific()`;
- en perfiles con ~980 dígitos, el trabajo repetido de este método contribuye de forma visible al tiempo acumulado.

Aspecto que mejora:

- reduce asignaciones de strings grandes;
- reduce costo por evento de rueda/arrastre;
- mejora la suavidad del scroll cuando el usuario ya ha prefetched varios cientos de dígitos.

Cambio recomendado:

- añadir caché interna invalidada en `set_text()`;
- reutilizar la cadena virtual mientras no cambien `self._sci_digits` o `self._sci_exponent`.

### 2. Evitar recomputación múltiple del mismo estado durante `_advance_scientific()`

Severidad: alta

Archivo y líneas:

- [calculator_ui.py](calculator_ui.py#L458-L548)
- [calculator_ui.py](calculator_ui.py#L502-L527)
- [calculator_ui.py](calculator_ui.py#L571-L587)
- [calculator_ui.py](calculator_ui.py#L591-L641)
- [calculator_ui.py](calculator_ui.py#L969-L1035)

Código implicado:

- `_advance_scientific()` en [calculator_ui.py](calculator_ui.py#L458-L548)
- `_preview_scientific_text()` en [calculator_ui.py](calculator_ui.py#L571-L587)
- `_render_scientific()` en [calculator_ui.py](calculator_ui.py#L591-L641)
- `_build_shifted_scientific_text()` en [calculator_ui.py](calculator_ui.py#L969-L1035)

Problema:

- dentro del loop de candidatos se llama a `_build_shifted_scientific_text(candidate)` para validar ancho;
- después se vuelve a calcular el texto con `_preview_scientific_text(candidate)`;
- luego `_render_scientific()` recalcula otra vez el texto final a mostrar;
- un único desplazamiento puede reconstruir varias veces el mismo estado visual.

Evidencia:

- en el perfil del scroll, `_build_shifted_scientific_text()` fue la función con mayor tiempo acumulado;
- para `700` scroll steps, esta función se ejecutó miles de veces;
- la llamada en el loop de candidatos está en [calculator_ui.py](calculator_ui.py#L503-L527) y el render final vuelve a construir el resultado en [calculator_ui.py](calculator_ui.py#L633-L636).

Aspecto que mejora:

- reduce tiempo CPU por paso de scroll;
- reduce trabajo duplicado entre preview y render;
- mejora respuesta del widget en resultados largos y densamente desplazables.

Cambio recomendado:

- reutilizar el texto y metadatos calculados en la fase de decisión del candidato;
- pasar ese resultado al render final o almacenarlo temporalmente para el mismo evento.

### 3. No derivar el exponente reconstruyendo toda la cadena científica

Severidad: media-alta

Archivo y líneas:

- [calculator_ui.py](calculator_ui.py#L851-L859)
- [calculator_ui.py](calculator_ui.py#L862-L871)
- [calculator_ui.py](calculator_ui.py#L874-L890)

Código implicado:

- `_shifted_exponent()` en [calculator_ui.py](calculator_ui.py#L851-L859)
- `_should_render_plain_tail()` en [calculator_ui.py](calculator_ui.py#L862-L871)
- `_should_render_plain_decimal_window()` en [calculator_ui.py](calculator_ui.py#L874-L890)

Problema:

- `_shifted_exponent()` llama a `_build_shifted_scientific_text()` solo para encontrar `e±n` y parsearlo de vuelta;
- esto acopla una decisión numérica simple a la generación completa de la cadena visual.

Evidencia:

- en el perfil de fracciones largas, `_shifted_exponent()` apareció con tiempo acumulado relevante;
- el costo real proviene de reconstruir la cadena completa para extraer un dato que puede calcularse directamente.

Aspecto que mejora:

- reduce trabajo algorítmico en decisiones de layout;
- simplifica la ruta crítica del scroll;
- mejora especialmente los casos con transición a decimal plano.

Cambio recomendado:

- calcular el exponente desplazado de forma directa a partir de `self._sci_exponent`, `shift`, `effective_shift` y `shown_digits`;
- evitar construir y volver a parsear una cadena para este propósito.

### 4. Reducir el costo del loop de búsqueda de candidato válido

Severidad: media

Archivo y líneas:

- [calculator_ui.py](calculator_ui.py#L502-L533)

Código implicado:

- loop `while candidate > 0 and candidate <= max_shift:` en [calculator_ui.py](calculator_ui.py#L502-L533)

Problema:

- el loop explora candidatos secuencialmente y en cada iteración consulta múltiples helpers costosos;
- cada candidato puede provocar nuevas llamadas a `_build_shifted_scientific_text()`, `_should_render_plain_decimal_window()`, `_should_render_plain_tail()` y `_preview_scientific_text()`;
- el costo total del scroll crece por candidato evaluado, no solo por estado finalmente mostrado.

Evidencia:

- la zona de mayor densidad de costo está concentrada en ese loop;
- al combinar perfiles y lectura de código, se observa recomputación del mismo conjunto de datos por candidato.

Aspecto que mejora:

- hace más predecible el tiempo por scroll;
- evita picos cuando el widget debe saltar estados inválidos o underfull;
- reduce jitter visual en scroll continuo.

Cambio recomendado:

- cache local por evento para exponentes, textos y flags del candidato;
- evitar recalcular datos del mismo `candidate` más de una vez.

### 5. Reutilizar preprocessing de expresiones en expansiones de precisión

Severidad: media

Archivo y líneas:

- [arbitrary_precision_engine.py](arbitrary_precision_engine.py#L123-L149)
- [formula_evaluator.py](formula_evaluator.py#L119-L128)

Código implicado:

- `request_more_precision()` en [arbitrary_precision_engine.py](arbitrary_precision_engine.py#L123-L131)
- `_evaluate_with_digits()` en [arbitrary_precision_engine.py](arbitrary_precision_engine.py#L134-L149)
- `_preprocess()` en [formula_evaluator.py](formula_evaluator.py#L119-L128)

Problema:

- cada expansión de precisión vuelve a validar, preprocesar, tokenizar literales y evaluar desde cero la misma expresión;
- para la expresión probada esto todavía no domina el tiempo total, pero sí añade costo fijo innecesario en cada prefetch.

Evidencia:

- en la evaluación inicial, una parte apreciable del tiempo acumulado estaba en `_preprocess()` y en regex relacionadas;
- en expansiones posteriores domina `mpmath`, pero el reprocesado de la expresión sigue ocurriendo en cada request.

Aspecto que mejora:

- baja latencia de prefetch cuando la expresión es compleja a nivel sintáctico;
- reduce costo fijo por expansión;
- mejora escalabilidad si se agregan expresiones más largas o más funciones anidadas.

Cambio recomendado:

- cachear la expresión ya validada y preprocesada tras `evaluate()`;
- reutilizar la versión promovida en `request_more_precision()` mientras la expresión no cambie.

### 6. Sustituir creación repetida de threads por un trabajador persistente

Severidad: baja-media

Archivo y líneas:

- [calculator_ui.py](calculator_ui.py#L1417-L1434)
- [calculator_ui.py](calculator_ui.py#L1456-L1478)

Código implicado:

- `_calculate()` en [calculator_ui.py](calculator_ui.py#L1417-L1434)
- `_request_more_precision()` en [calculator_ui.py](calculator_ui.py#L1456-L1478)

Problema:

- tanto el cálculo inicial como el prefetch crean un `threading.Thread` nuevo por operación;
- `_loading_more` evita la superposición de prefetch, pero no elimina el overhead de creación/destrucción de hilos.

Evidencia:

- no fue el cuello principal del perfil;
- sigue siendo un punto de mejora estructural para mantener latencia estable si aumenta la frecuencia de solicitudes.

Aspecto que mejora:

- reduce overhead de scheduling y creación de hilos;
- hace más simple controlar cancelación, serialización y limpieza del trabajo en segundo plano;
- prepara mejor la app para futuras mejoras de prefetch.

Cambio recomendado:

- usar un worker único o `ThreadPoolExecutor(max_workers=1)`;
- serializar cálculos y expansiones a través de esa cola de trabajo.

## Prioridad sugerida de implementación

1. Cachear `_virtual_digits_for_shifting()`.
2. Eliminar recomputación múltiple del mismo estado entre decisión, preview y render.
3. Reemplazar `_shifted_exponent()` por cálculo directo, sin construir cadena.
4. Añadir caché local por candidato dentro de `_advance_scientific()`.
5. Reutilizar expresión preprocesada en `ArbitraryPrecisionCalculatorEngine`.
6. Unificar trabajo en background con un worker persistente.

## Impacto esperado

Si se implementan los primeros tres cambios, el efecto esperado es:

- menor uso de CPU por desplazamiento;
- menor número de asignaciones temporales de strings largos;
- scroll más estable cuando ya se han prefetched cientos de dígitos;
- menor latencia percibida antes de necesitar otra expansión de precisión.

## Conclusión

La aplicación no muestra todavía un problema grave en el motor numérico para la expresión usada como benchmark. La principal oportunidad de rendimiento está en el widget de resultado, donde el mismo estado visual puede reconstruirse varias veces durante un solo paso de scroll.

La optimización de mayor retorno inmediato está en [calculator_ui.py](calculator_ui.py), especialmente en el grupo de funciones formado por `_advance_scientific()`, `_preview_scientific_text()`, `_render_scientific()`, `_virtual_digits_for_shifting()` y `_build_shifted_scientific_text()`.