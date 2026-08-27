# Ecuaciones: la fórmula exacta de cada cálculo

Este documento es la referencia matemática pura — cada fórmula tal como
está implementada, con sus parámetros y de dónde viene. El *porqué* de
cada decisión (por qué esta fórmula y no otra) está en
[METODOS.md](METODOS.md); esto es solo "qué cuenta exactamente calcula
el código".

Notación: `x[i]` es una muestra en el instante `t[i]`; `fs` es la
frecuencia de muestreo en Hz (`≈ 20 Hz`, se mide como
`1 / mediana(diff(t))`); una "ventana centrada de N muestras en `i`" es
el conjunto `{x[j] : j ∈ [i − (N−1)/2, i + (N−1)/2]}`, con `N` siempre
impar. `N` sale de convertir una duración en segundos a muestras:

```
N = round(ventana_s · fs), forzado a impar (+1 si da par)
```
— [`seconds_to_samples`](../pressure_lab/analysis/offline.py)

## 1. Del ADC a conductancia

```
K_G = (V_REF · 1e6) / (ADC_FS · V_EXC · R_FEEDBACK)     [uS por cuenta de ADC]

G[i] = adc_raw[i] · K_G                                  [uS]
```

Constantes fijas por el circuito (el amplificador inversor de
transimpedancia): `V_REF = 3.3 V`, `V_EXC = 0.7534 V`,
`R_FEEDBACK = 12000 Ω`, `ADC_FS = 1023`.

- [`FrontEndParams.k_g_uS`](../pressure_lab/config.py), [`adc_to_conductance_uS`](../pressure_lab/calibration/convert.py)

Si un archivo ya trae `G_uS` calculada (algunas mediciones más viejas), se
usa esa columna directamente y este paso se salta.

## 2. Baseline centrado: mediana móvil

```
B0[i] = mediana( ventana centrada de N muestras de G, en i )
```

`N` sale de una ventana de **60 s** (`baseline_window_s`) — mucho más
ancha que un evento típico, para que la mediana no termine metida adentro
de un clog largo (ver METODOS.md, sección 2).

- [`centered_baseline`](../pressure_lab/analysis/offline.py) (con `robust=True`, el default)

## 3. Sigma centrado: MAD (desviación absoluta media)

```
resid[j] = |G[j] − B0[j]|

σ0[i] = 1.2533 · media( ventana centrada de N muestras de resid, en i )
```

El factor `1.2533` es la relación teórica entre la MAD y el desvío
estándar para una distribución gaussiana — así `σ0` queda en la misma
escala que un desvío estándar convencional, aunque se calcule con la
media absoluta en vez de la varianza.

- [`centered_sigma`](../pressure_lab/analysis/offline.py)

## 4. Refinamiento robusto (dos pasadas): `baseline_offline`, `sigma_offline`

Primera pasada: `B0`, `σ0` como en 2 y 3.

```
evento0[i] = (σ0[i] > 0) Y (|G[i] − B0[i]| > k · σ0[i])
```

Segunda pasada, excluyendo las muestras marcadas como evento de cada
ventana (en vez de solo ignorar su magnitud como hace la mediana sola):

```
G'[i] = G[i]  si no evento0[i],  si no NaN

B[i]  = mediana( { G'[j] : j en ventana(i, N), G'[j] ≠ NaN } )

resid'[j] = |G[j] − B[j]|  si no evento0[j],  si no NaN

σ[i]  = 1.2533 · media( { resid'[j] : j en ventana(i, N), resid'[j] ≠ NaN } )
```

(Si una ventana entera queda enmascarada, se rellena con el valor válido
más cercano hacia adelante/atrás.) `k = 4` por default (`event_k`).

`B` y `σ` de esta segunda pasada son `baseline_offline` y `sigma_offline`.

- [`centered_baseline_robust`](../pressure_lab/analysis/offline.py)

## 5. Señal de fuerza (sin calibrar): `dG_offline`

```
δG[i] = G[i] − B[i]     [uS]
```

Esta es la señal que usan CCDF, histogramas de incrementos y skewness —
punto a punto, sin suavizar.

- [`prepare_force_proxy`](../pressure_lab/analysis/pipeline.py)

## 6. Envolvente de actividad: `envelope_offline`

```
E[i] = media( ventana centrada de M muestras de |δG|, en i )
```

`M` sale de una ventana de **1.5 s** (`envelope_window_s`) — corta
respecto a un evento típico (no lo aplana), larga respecto al ruido de
muestra a muestra (lo filtra).

Después se le calcula su propio baseline y sigma, con las mismas fórmulas
2 y 3 (mediana + MAD centradas, **sin** el refinamiento de dos pasadas de
la sección 4), aplicadas a `E` en vez de a `G`, con la misma ventana ancha
`N` (60 s):

```
EB[i] = mediana( ventana centrada de N muestras de E, en i )        → envelope_baseline

Eσ[i] = 1.2533 · media( ventana centrada de N muestras de |E − EB|, en i )   → envelope_sigma
```

- [`activity_envelope`](../pressure_lab/analysis/offline.py), [`prepare_force_proxy`](../pressure_lab/analysis/pipeline.py)

## 7. Detección de eventos

Regla genérica (misma fórmula, se aplica sobre distintas señales según el
uso):

```
evento[i] = (σ[i] > 0) Y (|x[i] − base[i]| > k · σ[i])
```

En `scripts/make_figures.py` se aplica sobre la envolvente (sección 6):
`x = E`, `base = EB`, `σ = Eσ`, `k = SPIKE_K` (default 4) — para decidir
*cuándo* hay un burst o un clog (ver METODOS.md, sección 3, por qué sobre
la envolvente y no sobre `δG` directo).

- [`detect_spikes`](../pressure_lab/analysis/events.py)

## 8. Segmentación en bursts / clogs

Índices consecutivos con `evento[i] = True` se agrupan en segmentos
`[i_inicio, i_fin]`:

```
duración = t[i_fin] − t[i_inicio]

tipo = "clog"   si duración ≥ MIN_CLOG_DURATION_S  (default 1 s)
       "burst"  si no

pico = δG[j*],  j* = argmax_{j en el segmento} |δG[j]|
```

El pico se lee de la señal cruda `δG` (no de la envolvente `E`): la
envolvente decide *cuándo* hubo evento, la señal cruda dice *cuánto*.

- [`segment_bursts_and_clogs`](../pressure_lab/analysis/events.py)

## 9. CCDF (función de supervivencia empírica)

Con `x` ordenado ascendente (`x₍₁₎ ≤ x₍₂₎ ≤ ... ≤ x₍ₙ₎`):

```
P(X ≥ x₍ᵢ₎) = (n − i + 1) / n
```

- [`ccdf`](../pressure_lab/analysis/stats.py)

## 10. Ajuste exponencial de la cola

Se asume `P(X ≥ x) ≈ e^(b) · e^(−x/F0)`. Tomando logaritmo, es una recta:

```
ln P(X ≥ x) ≈ b − x / F0
```

Se ajusta por cuadrados mínimos (regresión lineal de grado 1) entre `x` y
`ln P(X ≥ x)`:

```
pendiente, b = polyfit(x, ln P, grado=1)

F0 = −1 / pendiente
```

`tail_quantile` (opcional) restringe el ajuste a la cola superior, usando
solo los puntos con `x ≥ cuantil(x, tail_quantile)`.

- [`exponential_tail_fit`](../pressure_lab/analysis/stats.py)

## 11. QQ plot (cuantiles emparejados)

Con `m` cuantiles (default 99):

```
q_j = j / (m + 1),  j = 1 .. m

qx_j = cuantil_{q_j}(X)
qy_j = cuantil_{q_j}(Y)
```

Se grafican los pares `(qx_j, qy_j)`.

- [`quantile_quantile`](../pressure_lab/analysis/stats.py)

## 12. Incrementos `δf`

```
δf[i] = δG[i + L] − δG[i],     L = round(δt · fs)  [muestras]
```

- [`delta_series`](../pressure_lab/analysis/stats.py)

## 13. Asimetría (skewness)

Momento estandarizado de tercer orden (definición de Fisher-Pearson, sin
corrección de sesgo muestral):

```
x̄  = media(x)
m2 = media( (x − x̄)² )
m3 = media( (x − x̄)³ )

skewness = m3 / m2^(3/2)
```

(`skewness = 0` si `m2 = 0`, para evitar dividir por cero en una serie
constante.)

- [`skewness`](../pressure_lab/analysis/stats.py)

## 14. Asimetría vs. tiempo de incremento

Para cada `δt` en una grilla de valores (0.25 s a 15 s, paso 0.5 s en
`scripts/make_figures.py`):

```
L = round(δt · fs)         [muestras]
δt_usado = L / fs           (δt ajustado a la grilla de muestreo)

skewness(δt) = skewness( δf con lag L, fórmulas 12 + 13 )
```

- [`skewness_vs_dt`](../pressure_lab/analysis/stats.py)

## 15. Calibración a fuerza real (todavía identidad)

```
fuerza = escala · δG + desplazamiento
```

Por default `escala = 1`, `desplazamiento = 0` (no calibrado, unidades
`uS`). El día que exista una curva peso↔conductancia, se reemplaza por
esos valores ajustados (o por una función no lineal, `fit_fn`, si hace
falta).

- [`Calibration`](../pressure_lab/calibration/convert.py)

## Anexo: el método causal (histórico, no corre hoy)

Reconstruido a partir de las columnas `G0_mon`/`sigma_mon` de algunas
mediciones más viejas — no es lo que calcula el firmware actual (ver
METODOS.md, secciones 2 y 6), pero se reimplementó en Python para poder
compararlo contra el método centrado (`scripts/compare_baselines.py`).

```
B[0] = G[0],  MAD[0] = 0

para i ≥ 1:
    d = G[i] − B[i−1]
    σ_prev = 1.2533 · MAD[i−1]
    evento = (σ_prev > 0) Y (|d| > k · σ_prev)      k = 4  (freeze_k)

    si evento:
        B[i]   = B[i−1]              (congelado)
        MAD[i] = MAD[i−1]            (congelado)
    si no:
        B[i]   = B[i−1] + α_base · d              α_base = 0.0033
        MAD[i] = MAD[i−1] + α_dev · (|d| − MAD[i−1])   α_dev = 0.0100

    σ[i] = 1.2533 · MAD[i]
```

A diferencia de las fórmulas 2-4 (centradas, miran para adelante y para
atrás), esta solo mira el pasado (`i−1`) — por eso reacciona con retraso
ante un cambio real, como se explica en METODOS.md.

- [`rolling_baseline_sigma`](../pressure_lab/analysis/events.py)

## Constantes, todas juntas

| Símbolo | Significado | Valor default | Dónde se define |
|---|---|---|---|
| `V_REF` | tensión de referencia del ADC | 3.3 V | `config.py` / `.ino` |
| `V_EXC` | tensión de excitación del sensor | 0.7534 V | `config.py` / `.ino` |
| `R_FEEDBACK` | resistencia de realimentación del ampli inversor | 12000 Ω | `config.py` / `.ino` |
| `ADC_FS` | escala del ADC (10 bits) | 1023 | `config.py` / `.ino` |
| `baseline_window_s` | ventana del baseline centrado (secciones 2, 4, 6) | 60 s | `pipeline.py` |
| `envelope_window_s` | ventana de suavizado de la envolvente (sección 6) | 1.5 s | `pipeline.py` |
| `event_k` | umbral del refinamiento robusto (sección 4) | 4 | `pipeline.py` |
| `SPIKE_K` | umbral de detección de eventos (sección 7) | 4 | `scripts/make_figures.py` |
| `MIN_CLOG_DURATION_S` | duración mínima para llamar "clog" (sección 8) | 1 s | `scripts/make_figures.py` |
| `DELTA_HIST_DT_S` | δt de los histogramas de incrementos (sección 12) | 2.5 s | `scripts/make_figures.py` |
| `1.2533` | factor MAD → sigma equivalente gaussiano | fijo | todo lo que calcula sigma |
| `α_base`, `α_dev`, `k` (anexo) | constantes del método causal histórico | 0.0033, 0.0100, 4 | `events.py` (reimplementación) |
