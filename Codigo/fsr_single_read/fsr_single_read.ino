// ============================================================================
// FSR RING - AD_RAW, CONDUCTANCE & ENVELOPE ONLY
// Streams raw average ADC, conductance, and envelope for Teleplot.
// ============================================================================

// --- PIN CONFIGURATION ---
const uint8_t PIN_ADC = A0;

// --- FRONT-END PARAMETERS ---
const float V_REF      = 3.3f;       // external AREF
const float V_EXC      = 0.7534f;    // excitation voltage
const float R_FEEDBACK = 12000.0f;   // feedback resistor
const float ADC_FS     = 1023.0f;

// Conductance in microsiemens directly from raw ADC average:
const float K_G_US = (V_REF * 1.0e6f) / (ADC_FS * V_EXC * R_FEEDBACK);

// --- TIMING & FILTERING ---
const uint16_t WINDOW_MS = 50;       // 20 Hz output rate
const float ALPHA_ENV    = 0.0250f;  // activity envelope tracking factor

// --- STATE ---
uint32_t adcAccum = 0;
uint16_t adcCount = 0;
uint32_t windowStart = 0;

float envG = 0.0f;

void setup() {
  Serial.begin(115200);

  analogReference(EXTERNAL);         // 3.3 V tied to AREF
  analogRead(PIN_ADC);               // discard first conversion after ref switch

  windowStart = millis();
}

void loop() {
  // Continuous free-running accumulation
  adcAccum += analogRead(PIN_ADC);
  adcCount++;

  uint32_t now = millis();
  if (now - windowStart < WINDOW_MS) return;

  float adcAvg = (float)adcAccum / (float)adcCount;
  adcAccum = 0;
  adcCount = 0;
  windowStart = now;

  // Conductance calculation [uS]
  float gs = adcAvg * K_G_US;

  // Envelope tracking
  envG += ALPHA_ENV * (fabs(gs) - envG);

  // --- TELEPLOT OUTPUT ---
  Serial.print(F(">ADC_RAW:")); Serial.print(now); Serial.print(':');
  Serial.print(adcAvg, 2);      Serial.println(F("|g"));

  Serial.print(F(">G:"));       Serial.print(now); Serial.print(':');
  Serial.print(gs, 2);          Serial.println(F("|g"));

  Serial.print(F(">ENV:"));     Serial.print(now); Serial.print(':');
  Serial.print(envG, 2);        Serial.println(F("|g"));
}