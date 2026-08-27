# Métodos: qué se calcula, por qué, y de dónde sale

Este documento explica, con bibliografía, cada método estadístico y de
procesamiento de señal que usa `pressure_lab`: qué es un baseline adaptativo y qué
significa cada panel de los gráficos. Pensado para leerse una vez y volver a
consultar, no para memorizar. Complementa a [../README.md](../README.md),
que cubre la estructura del código y cómo correrlo.

## 1. El problema de fondo: separar deriva lenta de eventos rápidos

El sensor entrega un número (`G_uS`, conductancia) que mezcla dos cosas:

- **Deriva lenta y legítima**: temperatura, acomodamiento mecánico. Cambia en
  escala de minutos.
- **Eventos rápidos, que es lo que nos interesa**: un robot empuja, se arma
  un atasco. Cambia en fracciones de segundo a segundos.

Para saber "cuánta fuerza hay ahora" hace falta restarle al valor crudo su
"nivel de reposo" (`baseline`) — pero ese nivel de reposo también hay que
estimarlo de los mismos datos, sin saber de antemano cuáles son eventos.

## 2. Baseline causal (EMA, idea de origen en el firmware) vs. baseline offline (centrado, en Python)

`pressure_lab` calcula su **propio** baseline en Python — el firmware
actual (`Codigo/fsr_single_read/fsr_single_read.ino`) no calcula ninguno:
solo transmite conductancia cruda y una versión suavizada de la misma
conductancia para monitoreo en vivo (ver sección 6). Una revisión anterior
del firmware sí calculaba un baseline on-device, con el método que se
describe abajo; esa revisión ya no está versionada en el repo, pero es la
que generó el `G0_mon`/`sigma_mon` que todavía traen algunas mediciones
más viejas (sección 7), y vale la pena entenderla igual: es un patrón de
diseño genuinamente útil para cualquier sistema embebido con memoria y
tiempo real limitados, y es contra lo que se compara el método de Python
en la sección 2.3.

### 2.1 El método de la revisión anterior del firmware: EMA con congelamiento

Reconstruido a partir de las columnas `G0_mon`/`sigma_mon` que quedaron
grabadas en mediciones más viejas — el archivo `.ino` que lo calculaba ya
no está en el repo. Corría en tiempo real en el Arduino mientras se medía.
Fórmula:

```
G0_nuevo = G0_viejo + α · (G_actual − G0_viejo)
```

Con `α` chico (0.0033 ≈ constante de tiempo de ~15 s a 20 Hz), cada muestra
mueve al promedio solo un poquito. Además, la actualización se **congela**
cuando la lectura actual se aleja demasiado del baseline (más de `k` sigmas),
para que un evento real no se filtre adentro del "nivel normal".

Es una **media móvil exponencial (EMA / exponential smoothing)**, la misma
familia de técnica que se usa en control de procesos industriales (cartas de
control EWMA) y en análisis de series de tiempo en general.

- [Wikipedia — Exponential smoothing](https://en.wikipedia.org/wiki/Exponential_smoothing)

**Por qué existía así, y no de otra forma**: el Arduino UNO tiene ~2KB de
RAM, no puede guardar un buffer de muestras (descarta un promedio móvil
clásico de ventana), tiene que decidir en tiempo real sin mirar el futuro
(descarta cualquier método "no causal"), y tiene que hacerlo con aritmética
simple de punto flotante en cada vuelta del loop (descarta algo tan prolijo
como un filtro de Kalman). El EMA con congelamiento es, dentro de esas tres
restricciones, un punto razonable: memoria de un solo número, actualización
barata, y una regla simple para no dejar que el propio evento contamine la
definición de "normal".

**Su defecto**: al ser causal, siempre reacciona *después* del cambio real, y
si un evento dura lo suficiente, el baseline lo empieza a perseguir.

### 2.2 El pipeline de Python: ventana centrada (no causal)

Implementado en [`pressure_lab/analysis/offline.py`](../pressure_lab/analysis/offline.py)
(`centered_baseline`, `centered_sigma`) y orquestado en
[`pressure_lab/analysis/pipeline.py`](../pressure_lab/analysis/pipeline.py)
(`prepare_force_proxy`). Como el análisis corre en una computadora sobre el
archivo ya grabado, ninguna de las tres restricciones de arriba aplica:

- Se puede usar una ventana **centrada**: cada punto mira muestras de antes
  *y* de después. Un cambio real se ve venir simétricamente, así que el
  baseline lo alcanza en la mitad de tiempo que un EMA causal del mismo
  ancho, sin arrastre.
- En vez de la media, se usa la **mediana móvil centrada** (parámetro
  `robust=True`, default) — mismo espíritu que el "congelamiento" del EMA:
  unos pocos valores extremos dentro de la ventana no logran arrastrar el
  baseline hacia ellos, porque la mediana ignora la magnitud de los outliers,
  solo cuenta cuántos hay.
- El "ruido normal" (`sigma_offline`) se estima con la **desviación absoluta
  media (MAD)** alrededor de ese baseline, con el mismo factor de conversión
  a sigma (`1.2533`, la relación teórica entre MAD y desvío estándar para
  una distribución gaussiana).

- [Wikipedia — Median absolute deviation](https://en.wikipedia.org/wiki/Median_absolute_deviation)
- [ConsultGLP — Robust Statistics: The MAD Method](https://consultglp.com/assets/uploads/2015/02/robust-statistics-mad-method.pdf) (explica con ejemplos por qué MAD no se deja "engañar" por outliers, a diferencia del desvío estándar)

**¿Por qué no usar directamente el desvío estándar?** Porque eleva al
cuadrado las diferencias: un solo pico enorme dispara la estimación de
"ruido normal" muchísimo más de lo que debería, y eso sube el umbral de
detección justo cuando más interesa que se mantenga sensible.

**El límite de la mediana centrada, y el segundo paso que lo corrige.**
La mediana es robusta a *unos pocos* valores extremos dentro de la
ventana, pero no a un evento que ocupe una fracción grande de la ventana
misma. En los datos reales, un "clog" puede durar varias decenas de
segundos — con una ventana de pocos segundos, la mediana termina
metiéndose adentro del propio evento en vez de ignorarlo, y el evento
"desaparece" de `dG_offline` justo donde más importa verlo. La función
usada en la práctica es `centered_baseline_robust`, no `centered_baseline`
sola: calcula un primer baseline (el de arriba), marca qué muestras se ven
anómalas contra ese primer cálculo, y recalcula baseline **y** sigma una
segunda vez excluyendo esas muestras por completo de cada ventana — así un
evento largo ya no compite por un lugar en su propia línea de base. La
ventana además se agrandó a 60 s (contra los pocos segundos que hubieran
alcanzado si los eventos fueran realmente breves) para darle margen a esta
segunda pasada.

### 2.3 Entonces, ¿cuál conviene usar?

- **En vivo, durante el experimento**: hoy el firmware no ofrece ningún
  baseline para esto — lo único que transmite es `ENV`, una versión
  suavizada de la conductancia misma (sección 6), útil como chequeo visual
  rápido pero no equivalente a restarle un nivel de reposo a la señal. Si
  en algún momento se necesita un baseline confiable en vivo, el método de
  la sección 2.1 (EMA con congelamiento) sigue siendo la referencia
  razonable dadas las limitaciones del microcontrolador.
- **Para el análisis estadístico posterior** (todo lo que hace este
  paquete: CCDF, histogramas, skewness): el baseline offline de Python es
  la única opción real, y además la más precisa (sin el retraso del EMA), y
  se puede recalcular con otros parámetros sin repetir la medición.

Por eso `pressure_lab` no depende de que un archivo traiga `G0_mon` — usa
`prepare_force_proxy` para calcular el suyo siempre, incluso en los pocos
archivos que ya traen uno propio.

## 3. Detección de eventos y segmentación en bursts / clogs

Implementado en [`pressure_lab/analysis/events.py`](../pressure_lab/analysis/events.py)
(`detect_spikes`, `segment_bursts_and_clogs`), orquestado desde
`scripts/make_figures.py`. Fuente de datos: **todas** las mediciones que
`discover_measurements()` encuentre bajo `Mediciones/` — no hay un número
fijo de sesiones ni de archivos, el script recorre la carpeta entera. Cada
medición se procesa por separado, y los bursts/clogs que salen de todas se
juntan en una sola colección para los gráficos que los comparan entre sí.

**Primer intento (no funcionó): umbral sobre la señal cruda.** La idea más
directa es marcar como "evento" cualquier muestra con
`|dG_offline| > k · sigma_offline` (la misma regla de "¿te alejaste de tu
vecindad?" que usaba la revisión anterior del firmware para congelar su
propio baseline, sección 2.1). En la práctica esto casi no encontraba
clogs: un evento real acá dura de segundos a un par de decenas de
segundos, pero es *ruidoso* mientras dura, así que muchas muestras
individuales adentro del evento caían por debajo del umbral al azar. El
resultado eran docenas de fragmentos de menos de un segundo en vez de un
puñado de eventos largos.

**Lo que corre hoy: umbral sobre una envolvente suavizada.** Antes de
aplicar el umbral, `activity_envelope` promedia `|dG_offline|` en una
ventana de 1.5 s. Esa ventana es corta comparada con la duración típica de
un evento (así no lo aplana), pero larga comparada con el ruido de muestra
a muestra (así lo filtra). El resultado es una curva que sube y baja una
sola vez por evento en vez de docenas de veces. Sobre esa envolvente se
calcula, con el mismo método centrado/robusto de la sección 2, un baseline
y un sigma propios (`envelope_baseline`, `envelope_sigma`), y recién ahí
se aplica `|envelope − envelope_baseline| > k · envelope_sigma`. Los
instantes marcados se agrupan en segmentos consecutivos
(`segment_bursts_and_clogs`); uno más corto que `MIN_CLOG_DURATION_S` es
"burst", uno más largo es "clog" — y el valor que se reporta como "pico"
de cada segmento se lee de la señal cruda `dG_offline` en ese tramo, no de
la envolvente (la envolvente decide *cuándo*, la señal cruda dice
*cuánto*).

Esto sigue siendo una versión simplificada, a mano, de lo que en la
literatura de series de tiempo se llama **detección de cambios
(change-point detection)** — el mismo problema de "¿en qué momento cambió
el régimen de la señal?" tiene métodos mucho más formales (por ejemplo
CUSUM), útiles si en algún momento este umbral no alcanza:

- [Towards Data Science — Probabilistic CUSUM for change point detection](https://towardsdatascience.com/probabilistic-cusum-for-change-point-detection-121f793ab3a1/)

## 4. Los gráficos, explicados desde la estadística que usan

Implementado en [`pressure_lab/analysis/stats.py`](../pressure_lab/analysis/stats.py)
y dibujado en [`pressure_lab/plotting/figures.py`](../pressure_lab/plotting/figures.py).

### 4.1 CCDF — "¿qué tan seguido pasan los eventos grandes?"

La función de distribución acumulada complementaria, `P(X ≥ x)`, responde:
de todas las lecturas, ¿qué fracción fue igual o mayor a `x`? Es la misma
idea que la "función de supervivencia" en estadística. Se grafica en
log-log porque así una **cola exponencial** (eventos grandes cada vez más
raros, pero de forma "predecible") se ve como una recta — y una curva que se
despega hacia arriba de esa recta señala eventos grandes más frecuentes de
lo esperable ("cola pesada"), que es justo el tipo de comportamiento que
distingue un empaquetamiento a punto de atascarse de uno que fluye normal.

- [Wikipedia — Survival function](https://en.wikipedia.org/wiki/Survival_function)

### 4.2 QQ plot — "¿tienen la misma forma dos distribuciones?"

Compara cuantil a cuantil dos muestras (acá, picos durante bursts vs.
durante clogs). Si cayeran sobre la recta `y = x`, una sería literalmente
la otra (misma forma, quizás distinta escala). Que se curven por encima
significa que "clog" no es solo "un burst más grande" — tiene una forma de
distribución distinta, con más peso en valores altos.

- [Wikipedia — Q–Q plot](https://en.wikipedia.org/wiki/Q%E2%80%93Q_plot)

### 4.3 Histogramas de δf y skewness vs. δt

`δf(t) = dG(t+δt) − dG(t)`: cuánto cambió la señal en una ventana de tiempo
`δt`. El histograma (semilog-y) muestra qué tan común es cada tamaño de
cambio. La **asimetría (skewness)** mide si esos cambios son igual de
probables para arriba que para abajo (skewness ≈ 0) o si hay una dirección
preferida — acá, valores negativos indican que las *caídas* bruscas grandes
son más comunes que las subidas bruscas grandes, coherente con que un
atasco se arma gradual pero se libera de golpe.

- [NIST e-Handbook — Measures of Skewness and Kurtosis](https://www.itl.nist.gov/div898/handbook/eda/section3/eda35b.htm)

## 5. El filtro anti-aliasing en el firmware

`fsr_single_read.ino` muestrea el ADC en un loop libre (varios miles de
veces por segundo — el orden de magnitud típico de `analogRead()` en un
AVR de 8 bits) y promedia todo lo acumulado en cada ventana de 50 ms antes
de transmitir el resultado. Ese promedio es un **filtro boxcar /
anti-aliasing**: tiene que pasar en tiempo real porque las muestras rápidas
nunca se guardan — si no se combinan en el momento, se pierden para
siempre. Es la única etapa de este sistema que, por su naturaleza, no
podría hacerse después con post-procesado.

- [Wikipedia — Anti-aliasing filter](https://en.wikipedia.org/wiki/Anti-aliasing_filter)
- [Tom Verbeure — Moving Average and CIC Filters](https://tomverbeure.github.io/2020/09/30/Moving-Average-and-CIC-Filters.html) (explicación intuitiva de por qué un promedio en ventana es, ni más ni menos, un filtro pasabajos)

## 6. Qué hace el firmware, en detalle

`Codigo/fsr_single_read/fsr_single_read.ino`, en su versión actual, corre
estas etapas en cada vuelta del `loop()` — y **nada más**: no calcula
baseline, no calcula sigma, no detecta eventos, no marca saturaciones del
ADC. Todo eso quedó exclusivamente del lado de Python (secciones 2 y 3).

1. **Muestreo + boxcar** (sección 5): acumula lecturas del ADC durante
   50 ms (`WINDOW_MS`) y promedia → `adcAvg`.
2. **Conductancia**: `gs = adcAvg * K_G_US`, con `K_G_US` derivado de
   `V_EXC`, `R_FEEDBACK` y `V_REF` (la conversión eléctrica del
   amplificador inversor, sección 2).
3. **Envolvente suavizada**: `envG += ALPHA_ENV * (|gs| − envG)`, con
   `ALPHA_ENV = 0.025` (constante de tiempo ≈ 2 s). Es una media móvil
   exponencial de la conductancia misma — **no** una línea de base ni una
   medida de actividad relativa a un reposo, solo `gs` con el ruido rápido
   atenuado, para que la curva sea más legible mirándola en vivo.
4. **Salida por Teleplot**: transmite `ADC_RAW` (`adcAvg`), `G` (`gs`) y
   `ENV` (`envG`) por Serial en formato Teleplot
   (`>variable:tiempo:valor|tipo`), para verlos en vivo con esa herramienta
   mientras se mide. No hay ningún otro canal ni ninguna decisión tomada
   sobre los datos a esta altura — eso es tarea de `prepare_force_proxy` en
   Python, después.

`V_EXC = 0.7534` y `R_FEEDBACK = 12000` (ohms) son los valores realmente
grabados en el firmware — fuente de verdad del front-end analógico;
`App/pressure_lab/config.py` los replica para los cálculos en Python. Si
algún día cambian en el Arduino, hay que actualizarlos ahí también.

Existe además un sketch separado, `Codigo/fsr_array_read/fsr_array_read.ino`,
que sí multiplexa varios sensores del anillo por un CD4051 (lectura canal
por canal en vez de una señal total agregada) — no es el que se usó para
generar las mediciones que trae hoy `Mediciones/`.

## 7. Por qué no todas las mediciones vienen en el mismo formato

`discover_measurements()` no asume ni un número fijo de mediciones ni un
formato único: recorre `Mediciones/` recursivamente y parsea cada archivo
CSV que encuentra. Algunas mediciones más viejas incluyen columnas
`timestamp(ms), t, n, dt_ms, adc_raw, R_ohm, G_uS, G0_mon, sigma_mon` — con
baseline y sigma calculados on-device — porque se grabaron con una
revisión del firmware que ya no está versionada acá y que escribía CSV
directamente en vez de transmitir por Teleplot (formato
`>variable:tiempo:valor|tipo`, el que emite la versión actual).

Esto no le genera ningún problema al análisis: el loader
(`pressure_lab/io/loader.py`) parsea el formato CSV plano directamente, y
cuando una medición sí trae `G0_mon`/`sigma_mon` propios, esos archivos
sirven además para la comparación de baselines de la sección 2.3. Si en
algún momento se decide loguear directamente el stream de Teleplot a un
archivo, hace falta escribir un parser distinto (no incluido todavía) — el
resto del pipeline (`prepare_force_proxy` en adelante) no cambiaría,
porque solo necesita `adc_raw` (o `G_uS`) y un timestamp por muestra,
sin importar cuántas mediciones haya ni de qué formato vengan.

## 8. Bibliografía, todo junto

| Tema | Referencia |
|---|---|
| EMA / suavizado exponencial | [NIST e-Handbook — Control Charts](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc3.htm) · [Wikipedia — Exponential smoothing](https://en.wikipedia.org/wiki/Exponential_smoothing) |
| MAD / estadística robusta | [Wikipedia — MAD](https://en.wikipedia.org/wiki/Median_absolute_deviation) · [ConsultGLP — Robust Statistics: MAD](https://consultglp.com/assets/uploads/2015/02/robust-statistics-mad-method.pdf) |
| Detección de cambios (bursts/clogs) | [CUSUM para change-point detection](https://towardsdatascience.com/probabilistic-cusum-for-change-point-detection-121f793ab3a1/) |
| CCDF / función de supervivencia | [Wikipedia — Survival function](https://en.wikipedia.org/wiki/Survival_function) · [StatisticsHowTo — CCDF](https://www.statisticshowto.com/complementary-cumulative-distribution-function-ccdf/) |
| QQ plot | [NIST e-Handbook — Q-Q Plot](https://www.itl.nist.gov/div898/handbook/eda/section3/qqplot.htm) · [Wikipedia — Q–Q plot](https://en.wikipedia.org/wiki/Q%E2%80%93Q_plot) |
| Skewness | [NIST e-Handbook — Skewness and Kurtosis](https://www.itl.nist.gov/div898/handbook/eda/section3/eda35b.htm) |
| Anti-aliasing / boxcar | [Wikipedia — Anti-aliasing filter](https://en.wikipedia.org/wiki/Anti-aliasing_filter) · [Tom Verbeure — Moving Average and CIC Filters](https://tomverbeure.github.io/2020/09/30/Moving-Average-and-CIC-Filters.html) |
