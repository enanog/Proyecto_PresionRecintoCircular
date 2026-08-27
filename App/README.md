# App — pressure_lab

Herramientas en Python para analizar las mediciones del anillo de sensores
FSR del proyecto (presión total en un recinto circular con partículas
activas / robots) y producir gráficos estadísticos: CDF complementaria (CCDF) de fuerzas,
comparación entre régimen de "burst" y de "clog", quantile-quantile plot, e
histogramas/asimetría de incrementos de fuerza.

Para el detalle de **qué es cada método y por qué se usa ese y no otro**
(con bibliografía), ver [docs/METODOS.md](docs/METODOS.md); para la
**fórmula exacta de cada cálculo** (baseline, sigma, envolvente, CCDF,
skewness, etc.), ver [docs/ECUACIONES.md](docs/ECUACIONES.md). Este
README es la referencia práctica: estructura del código y cómo correrlo.

## Qué mide el sistema

Un anillo de sensores FSR (resistivos, sensibles a fuerza) rodea un recinto
circular, y se lee como un único canal de "presión total". El sensor es exctado a través de un amplificador inversor
 (resistencia de realimentación `R_F = 12 kΩ`, tensión de
excitación `V_EXC`), y  se lee la salida con el ADC de 10 bits integrado del Arduino UNO. Más fuerza sobre
el anillo → menos resistencia → más conductancia → más tensión de salida
del amplificador.

## Estructura

```
App/
  pressure_lab/            paquete principal (editable, sin instalar nada)
    config.py              paths del repo + parámetros del front-end analógico
    io/loader.py           descubre y parsea los archivos de Mediciones/
    calibration/convert.py ADC -> conductancia, y el mapeo a fuerza real (placeholder)
    analysis/offline.py    baseline y sigma no causales (post-procesado, ventana centrada)
    analysis/pipeline.py   prepare_force_proxy(): arma la señal de fuerza para cualquier archivo
    analysis/stats.py      CCDF, ajuste exponencial de cola, QQ, incrementos, asimetría
    analysis/events.py     detección de eventos (spikes) y segmentación burst/clog
    plotting/style.py      estilo matplotlib + paleta secuencial por N_tot
    plotting/figures.py    funciones de graficado (una por tipo: CCDF, QQ, histograma, skewness)
  scripts/
    quickstart.py          ejemplo mínimo: carga 1 archivo, grafica señal + 1 CCDF
    make_figures.py        pipeline completo: recorre Mediciones/, genera las figuras
    compare_baselines.py   compara el baseline on-device (firmware) vs. el offline (Python)
  docs/METODOS.md          explicación de cada método + bibliografía
  docs/ECUACIONES.md       fórmula exacta de cada cálculo (baseline, sigma, CCDF, skewness...)
  tests/                   pruebas automáticas (unittest, sin dependencias extra)
  output/                  figuras generadas (no versionado)
```

Cada módulo tiene una sola responsabilidad, para poder editar/iterar sin
tener que entender todo el resto. `plotting/figures.py` no guarda nada a
disco por sí mismo: recibe/devuelve `Axes`/`Figure` de matplotlib, así que
se puede llamar desde un script, una notebook, o la consola interactiva.

## Uso rápido

```bash
cd App
pip install -r requirements.txt

python scripts/quickstart.py          # una medición, dos paneles, para verificar que todo carga
python scripts/make_figures.py        # pipeline completo -> output/*.png
python scripts/compare_baselines.py   # compara el baseline del firmware vs. el de Python
```

No hace falta instalar el paquete: los scripts se ejecutan directo (agregan
`App/` a `sys.path` vía `scripts/_bootstrap.py`). Si preferís importarlo
desde una notebook, `pip install -e .` (usa `pyproject.toml`) lo deja
instalable.

Correr las pruebas:

```bash
python -m unittest discover -s tests -v
```

## De dónde sale la señal de fuerza que usan los gráficos

Todo el análisis parte de una sola función,
[`prepare_force_proxy`](pressure_lab/analysis/pipeline.py):

1. `ensure_conductance_uS`: si el archivo no trae `G_uS` (conductancia)
   calculada, la deriva de `adc_raw` con la conversión eléctrica del
   amplificador inversor (fija por el circuito: `V_EXC`, `R_F`, `V_REF`).
2. `centered_baseline_robust`: estima una línea de base y un nivel de
   ruido normal (`baseline_offline`, `sigma_offline`) con un método propio
   que mira toda la sesión ya grabada (ventana centrada, no causal, 60 s),
   refinado en una segunda pasada que excluye las muestras ya marcadas
   como evento para que un episodio largo no termine "diluido" en su
   propia línea de base. Es más preciso para análisis posterior que lo que
   puede hacer un microcontrolador en tiempo real con memoria limitada —
   explicación completa en la sección 2 de [docs/METODOS.md](docs/METODOS.md).
3. `dG_offline = G_uS − baseline_offline`: la señal de fuerza (sin
   calibrar) que usan todos los gráficos de distribución (CCDF,
   histogramas, skewness), en microsiemens.
4. `activity_envelope`: una versión suavizada de `|dG_offline|` (ventana
   de 1.5 s), con su propio baseline/sigma (`envelope_baseline`,
   `envelope_sigma`). No se usa para los gráficos de distribución — sirve
   solo para decidir *cuándo* hay un burst o un clog (ver más abajo).

Todavía no hay curva peso↔conductancia para el anillo FSR (se va a obtener
después, cruzando con la cámara / análisis de materia activa). Mientras
tanto, [`calibration/convert.py`](pressure_lab/calibration/convert.py) ya
separa esto en dos capas para no tener que tocar nada cuando esa curva
exista:

1. Conversión eléctrica (ADC → conductancia): implementada, fija por el
   circuito.
2. `Calibration`: mapea `δG` (uS) a fuerza real. Por default es la
   identidad (no calibrado). El día que exista la curva, se define un
   `Calibration(scale=..., offset=..., unit="g")` (o un `fit_fn` para algo
   no lineal) y el resto del código (eventos, estadística, gráficos, ya
   escrito en términos de "fuerza") empieza a reportar unidades reales sin
   modificarse.

## Sobre bursts y clogs: de dónde salen y cómo se determinan

**De dónde salen.** `scripts/make_figures.py` recorre **todos** los
archivos de medición que encuentre bajo `Mediciones/` —
`discover_measurements()` los descubre recursivamente en cualquier
subcarpeta, sin límite de cantidad ni de sesiones; agregar una medición
nueva es solo dejar el archivo ahí, no hace falta tocar el código. Cada
archivo se analiza por separado — se le calcula su propio `dG_offline` y
su propia envolvente — y los bursts/clogs de **todas** las mediciones
cargadas se juntan en una sola bolsa para `ccdf_bursts_vs_clogs.png` y
`qq_bursts_vs_clogs.png`. Es decir, esos dos gráficos no distinguen de qué
medición vino cada evento, solo si fue "burst" o "clog"; el resto de los
gráficos (CCDF por N, histogramas, skewness) sí mantienen cada medición
(agrupada por `N_tot`) separada.

**Cómo se determinan.** Ni "burst" ni "clog" vienen etiquetados en la
medición — es una clasificación que arma `analysis/events.py` con una
regla de tres pasos:

1. **Envolvente, no señal cruda**: se suaviza `|dG_offline|` en una
   ventana de 1.5 s (`activity_envelope`). Hace falta este paso porque un
   evento real acá dura de segundos a un par de decenas de segundos, pero
   es *ruidoso* mientras dura — la lectura sigue vibrando arriba y abajo
   aunque el nivel de fondo esté elevado. Comparar cada muestra cruda
   contra un umbral fragmenta ese evento en pedacitos de menos de un
   segundo; suavizar primero lo convierte en una sola subida-y-bajada que
   sí se puede medir en duración.
2. **Umbral**: un instante de la envolvente cuenta como "evento" si supera
   en `SPIKE_K` (default 4) desvíos (`envelope_sigma`) a su propio fondo
   (`envelope_baseline`) — ambos, igual que el baseline de fuerza, calculados
   con ventana centrada y refinados excluyendo eventos ya detectados.
3. **Duración**: instantes de evento consecutivos se agrupan en un
   segmento. Si ese segmento dura menos de `MIN_CLOG_DURATION_S` (default
   1 s), se llama "burst"; si dura más, "clog". El "pico" que se grafica
   para cada segmento es el valor máximo de `dG_offline` (la señal cruda,
   no la envolvente) dentro de ese tramo.

Es un punto de partida razonable, no un algoritmo validado — los umbrales
(`SPIKE_K`, `MIN_CLOG_DURATION_S` en `scripts/make_figures.py`) están para
ajustarse mirando los datos reales.

## Qué significa cada gráfico

`python scripts/make_figures.py` deja un PNG por gráfico en `output/` (no
arma figuras compuestas con varios paneles). La cantidad exacta de
archivos depende de cuántas mediciones y cuántos grupos (`N_tot`
distintos) haya cargados en `Mediciones/` en el momento de correr el
script — con más sesiones no cambia el tipo de gráfico, solo se agregan
más `delta_hist_<grupo>.png` y se suma más data a los demás. Todos usan
`dG_offline` (o los eventos derivados de él, ver arriba) — es decir,
conductancia por encima de su línea de base, en microsiemens, no fuerza
calibrada.

- **`ccdf_forces_by_n.png`** — todas las muestras de `|dG_offline|` de
  todas las mediciones cargadas, una curva por cada `N_tot` detectado. El
  eje Y es "qué fracción de las lecturas fue igual o mayor a ese valor"
  (log-log). La recta negra es un ajuste exponencial sobre las mediciones
  activas combinadas: si los puntos de una curva se apartan por encima de
  esa recta, esa medición tuvo fuerzas grandes más seguido de lo que un
  decaimiento exponencial "limpio" predeciría.
- **`ccdf_bursts_vs_clogs.png`** — mismo tipo de curva, pero en vez de
  agrupar por `N_tot` agrupa por tipo de evento: el pico de cada burst
  contra el pico de cada clog, juntando los de todas las mediciones (ver
  sección anterior). Sirve para comparar si los clogs alcanzan picos más
  grandes que los bursts, y con qué frecuencia. Solo se genera si se
  detectó al menos un burst y un clog.
- **`qq_bursts_vs_clogs.png`** — los mismos dos grupos (picos de burst,
  picos de clog), comparados cuantil a cuantil en vez de acumulados. La
  diagonal punteada es "misma distribución, ambos ejes iguales"; que los
  puntos se despeguen por encima de esa diagonal en todo el rango dice que
  los clogs no son simplemente "bursts más grandes" — tienen su propia
  forma de distribución, sistemáticamente por encima.
- **`delta_hist_<grupo>.png`** — uno por cada `N_tot` (o "vacío")
  detectado automáticamente entre las mediciones cargadas — el nombre del
  grupo sale del propio archivo de medición, no está hardcodeado en el
  script. Histograma (eje Y log) de
  `δf(t) = dG_offline(t+2.5s) − dG_offline(t)`: cuánto cambió la señal en
  ventanas de 2.5 segundos. Un pico angosto y simétrico en 0 significa que
  la mayoría de los cambios son chicos y parejos para arriba/abajo; una
  cola larga hacia un lado significa que ese lado (subidas o bajadas
  grandes) es más común de lo que parece a simple vista en el centro del
  histograma.
- **`skewness_vs_dt.png`** — para cada medición, la asimetría (skewness)
  de esa misma distribución de `δf`, recalculada para distintos tamaños de
  ventana (`δt`, eje X, de 0.25 a 15 s). Un valor cercano a 0 (la línea gris
  de "vacío", si hay una corrida vacía cargada) significa cambios igual de
  probables para ambos lados a esa escala de tiempo; que una medición se
  aparte de 0 en alguna escala temporal marca en qué ventana de tiempo esa
  medición deja de comportarse como ruido simétrico.

## El firmware (Arduino) y su relación con este análisis

`Codigo/fsr_single_read/fsr_single_read.ino`, en su versión actual, hace
solo tres cosas en tiempo real:

1. **Muestrea el ADC** a alta frecuencia y promedia cada ventana de 50 ms
   (`WINDOW_MS`) → salida a 20 Hz. Es un filtro anti-aliasing (boxcar) que
   *tiene* que pasar en el Arduino, porque las muestras rápidas nunca se
   guardan.
2. **Calcula conductancia** (`gs = adcAvg * K_G_US`) a partir de ese
   promedio y de los parámetros fijos del circuito (`V_EXC`, `R_FEEDBACK`,
   `V_REF`).
3. **Suaviza esa misma conductancia** con una media móvil exponencial
   (`envG`, `ALPHA_ENV = 0.025`, constante de tiempo ≈ 2 s) y transmite los
   tres valores (`ADC_RAW`, `G`, `ENV`) por Teleplot, para poder ver la
   señal en vivo mientras se mide.

El `envG` es solo una versión suavizada de `G`, útil para mirar en vivo,
pero no es una línea de base utilizable para análisis (solo atenúa el ruido rápido). Todo el procesamiento
analítico (baseline, sigma, detección de eventos) vive exclusivamente en
Python, en `prepare_force_proxy` — pensado para post-procesado sobre la
sesión completa ya grabada, sin las limitaciones de memoria y tiempo real
del microcontrolador. Más detalle, con la historia de por qué el firmware
llegó a esta forma tan simple, en las secciones 2 y 6 de
[docs/METODOS.md](docs/METODOS.md).

`V_EXC = 0.7534` y `R_FEEDBACK = 12000` en el `.ino` son la fuente de
verdad del front-end analógico — `pressure_lab/config.py` los replica; si
cambian en el Arduino, hay que actualizarlos ahí también.

**Nota sobre el formato de los archivos**: no todas las mediciones bajo
`Mediciones/` van a tener las mismas columnas. Sesiones grabadas con
revisiones más viejas del firmware pueden traer, además de `adc_raw`, un
baseline y un sigma calculados on-device (`R_ohm, G_uS, G0_mon,
sigma_mon`) en formato CSV plano; el firmware actual solo transmite por
Teleplot (`>variable:tiempo:valor|tipo`), sin esas columnas extra. El
loader (`pressure_lab/io/loader.py`) parsea el formato CSV plano
directamente y llena lo que falte por su cuenta; si en el futuro se
registra por Teleplot a un archivo, hace falta escribir un parser distinto
para ese formato (no incluido todavía).

## Cómo extender

- **Nueva medición / sesión**: cae sola bajo `Mediciones/<fecha>/*.json`
  (en formato CSV plano), `discover_measurements()` la encuentra sin que
  haga falta tocar ningún código — no hay límite de cantidad de sesiones
  ni de archivos por sesión. El número de robots se parsea del nombre del
  archivo (`"... N Robots ..."` o `"Vacio"` para la línea de base); si el
  patrón no matchea, `n_bots` queda en `None` y se agrupa aparte.
- **Nuevo panel**: agregar una función en `plotting/figures.py` que reciba
  un `Axes` y devuelva ese mismo `Axes` (ver las funciones existentes como
  plantilla), y llamarla desde un script.
- **Calibración real**: una vez haya datos peso-vs-conductancia, ajustar y
  reemplazar `IDENTITY_CALIBRATION` en `calibration/convert.py`.
