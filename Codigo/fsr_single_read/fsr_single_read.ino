// ============================================================================
// FSR RING - TOTAL PRESSURE ACQUISITION
// Non-blocking boxcar decimation + adaptive baseline tracking.
// Streams conductance (not resistance) for Teleplot.
// ============================================================================

// --- PIN CONFIGURATION ---
const uint8_t PIN_MUX_A = 11;
const uint8_t PIN_MUX_B = 12;
const uint8_t PIN_MUX_C = 13;
const uint8_t PIN_ADC   = A0;

// --- FRONT-END PARAMETERS ---
const float V_REF        = 3.3f;      // external AREF
const float V_EXC        = 0.7534f;   // excitation voltage
const float R_FEEDBACK   = 12000.0f;   // lowered from 12k: prevents clipping on peak events
const float ADC_FS       = 1023.0f;

// Transimpedance transfer: Vout = V_EXC * Rf * G  ->  G = Vout / (V_EXC * Rf)
// Conductance in microsiemens directly from raw ADC average:
const float K_G_US = (V_REF * 1.0e6f) / (ADC_FS * V_EXC * R_FEEDBACK);

// --- TIMING ---
const uint16_t WINDOW_MS = 50;        // decimation window -> 20 Hz output

// --- BASELINE TRACKER ---
const float ALPHA_BASE  = 0.0033f;    // tau ~ 15 s at 20 Hz (tracks creep/drift only)
const float ALPHA_DEV   = 0.0100f;    // tau ~ 5 s, mean-absolute-deviation estimator
const float ALPHA_ENV   = 0.0250f;    // tau ~ 2 s, activity envelope
const float EVENT_K     = 4.0f;       // detection threshold in sigma
const uint16_t SEED_MS  = 3000;       // baseline seeding period on boot

// --- STATE ---
uint32_t adcAccum = 0;
uint16_t adcCount = 0;
uint32_t windowStart = 0;
bool     clipped = false;

float gBase = 0.0f;
float madG  = 0.0f;
float envG  = 0.0f;
bool  seeded = false;

void setMuxChannel(uint8_t channel);

void setup() {
  Serial.begin(115200);

  pinMode(PIN_MUX_A, OUTPUT);
  pinMode(PIN_MUX_B, OUTPUT);
  pinMode(PIN_MUX_C, OUTPUT);
  setMuxChannel(0);

  analogReference(EXTERNAL);          // 3.3 V tied to AREF
  analogRead(PIN_ADC);                // discard first conversion after ref switch

  windowStart = millis();
}

void loop() {
  // Continuous free-running accumulation: no dead time, the boxcar spans the
  // entire window so it acts as a true anti-alias filter before decimation.
  uint16_t raw = analogRead(PIN_ADC);
  if (raw >= 1022) clipped = true;
  adcAccum += raw;
  adcCount++;

  uint32_t now = millis();
  if (now - windowStart < WINDOW_MS) return;

  float adcAvg = (float)adcAccum / (float)adcCount;
  adcAccum = 0;
  adcCount = 0;
  windowStart = now;

  float gs = adcAvg * K_G_US;         // sensor conductance [uS], proportional to load

  if (!seeded) {
    gBase = (gBase == 0.0f) ? gs : gBase + 0.05f * (gs - gBase);
    if (now > SEED_MS) seeded = true;
    return;                           // suppress output while baseline settles
  }

  float dG = gs - gBase;
  float sigma = 1.2533f * madG;       // Gaussian relation between MAD and sigma
  bool  isEvent = (sigma > 0.0f) && (fabs(dG) > EVENT_K * sigma);

  // Freeze baseline and noise estimators during events so transients are not
  // absorbed into the reference.
  if (!isEvent) {
    gBase += ALPHA_BASE * dG;
    madG  += ALPHA_DEV * (fabs(dG) - madG);
  }
  envG += ALPHA_ENV * (fabs(dG) - envG);

  // --- TELEPLOT OUTPUT ---
  // Explicit timestamps avoid jitter from USB buffering on the host side.
  Serial.print(F(">dG:"));   Serial.print(now); Serial.print(':');
  Serial.print(dG, 2);       Serial.println(F("|g"));

  Serial.print(F(">env:"));  Serial.print(now); Serial.print(':');
  Serial.print(envG, 2);     Serial.println(F("|g"));

  Serial.print(F(">G:"));    Serial.print(now); Serial.print(':');
  Serial.print(gs, 2);       Serial.println(F("|g"));

  Serial.print(F(">G0:"));   Serial.print(now); Serial.print(':');
  Serial.print(gBase, 2);    Serial.println(F("|g"));

  if (isEvent) {
    Serial.print(F(">evt:")); Serial.print(now); Serial.print(':');
    Serial.print(dG, 2);      Serial.println(F("|np"));
  }
  if (clipped) {
    Serial.print(F(">CLIP:")); Serial.print(now); Serial.println(F(":1|np"));
    clipped = false;
  }
}

// CD4051 channel select (0-7)
void setMuxChannel(uint8_t channel) {
  digitalWrite(PIN_MUX_A, bitRead(channel, 0));
  digitalWrite(PIN_MUX_B, bitRead(channel, 1));
  digitalWrite(PIN_MUX_C, bitRead(channel, 2));
}
