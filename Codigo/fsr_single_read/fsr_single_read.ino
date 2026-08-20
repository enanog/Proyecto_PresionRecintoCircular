// ============================================================================
// PRUEBA SIMPLE DE SENSADO CON 1 CD4051 Y ADC ESTÁNDAR (10-BIT)
// ============================================================================

// --- CONFIGURACIÓN DE PINES ---
const int PIN_MUX_A = 11; // Dirección A (LSB)
const int PIN_MUX_B = 12; // Dirección B
const int PIN_MUX_C = 13; // Dirección C (MSB)

const int PIN_ADC = A0;   // Entrada analógica común desde la salida del op-amp

// --- PARÁMETROS DEL CIRCUITO ---
const float V_REF = 3.3;             // Voltaje de referencia de lectura del ADC (Volts)
const float V_EXC = 0.7534;            // Voltaje de excitación (Volts)
const float R_FEEDBACK = 10000.0;     // Resistencia de realimentación Rf (Ohms)
const float ADC_MAX_SCALE = 1023.0;  // Escala máxima ADC de 10 bits (2^10 - 1)
const float R_UNPRESSED = 2000000.0;   // Resistencia asignada si no hay presión

const int NUM_SAMPLES = 10;          // Número de muestras para promediar

// Prototipos de funciones
void setMuxChannel(uint8_t channel);
float calculateResistance(float rawADC);

void setup() {
  Serial.begin(115200);

  // Configurar pines del multiplexor como salida
  pinMode(PIN_MUX_A, OUTPUT);
  pinMode(PIN_MUX_B, OUTPUT);
  pinMode(PIN_MUX_C, OUTPUT);

  // Establecer canal 0 por defecto
  setMuxChannel(0);

  // Configurar la referencia analógica externa (Asegúrate de conectar 3.3V al pin AREF)
  analogReference(EXTERNAL);

  Serial.println(F("=============================================="));
  Serial.println(F("              INICIANDO PRUEBA                "));
  Serial.println(F("=============================================="));
}

const float Y_MIN = 120.0;    // Límite inferior (Ohms)
const float Y_MAX = 200.0; // Límite superior (Ohms)
float sensorFiltrado = 0.0;

void loop() {
  float adcSum = 0.0;

  for (int i = 0; i < NUM_SAMPLES; i++) {
    adcSum += analogRead(PIN_ADC);
    delay(2);
  }

  float adcAverage = adcSum / (float)NUM_SAMPLES;
  float sensorResistance = calculateResistance(adcAverage);
  float alpha = 0.3; // Factor de suavizado (0.01 a 1.0). Más chico = más suave
  sensorFiltrado = (alpha * sensorResistance) + ((1.0 - alpha) * sensorFiltrado);

  // --- TRUCO PARA FIJAR EL EJE Y ---
  /*
  Serial.print("Min:");
  Serial.print(Y_MIN);
  Serial.print(",");
  Serial.print("Max:");
  Serial.print(Y_MAX);
  Serial.print(",");*/
  Serial.print(">Resistencia_Ohms:");
  Serial.println(sensorFiltrado, 2);

  delay(30);
}

// Convierte la lectura promedio del ADC de 10 bits a la resistencia del FSR
float calculateResistance(float rawADC) {
  // Convertir lectura digital a voltaje de salida (Vout)
  float vOut = (rawADC * V_REF) / ADC_MAX_SCALE;

  // Umbral para evitar división por cero o ruido de pin flotante
  if (vOut < 0.02) {
    return R_UNPRESSED; // Resistencia alta por defecto (sensor no presionado)
  }

  // Transferencia del amplificador inversor: Rsensor = (Vexc * Rf) / Vout
  return (V_EXC * R_FEEDBACK) / vOut;
}

// Selección de canal del multiplexor CD4051 (Canales 0 a 7)
void setMuxChannel(uint8_t channel) {
  digitalWrite(PIN_MUX_A, bitRead(channel, 0));
  digitalWrite(PIN_MUX_B, bitRead(channel, 1));
  digitalWrite(PIN_MUX_C, bitRead(channel, 2));
}