#include "HX711.h"

// Definimos los pines del Arduino que van al módulo
const int pinData = 2;   // Pin DT del HX711 al pin D2 del Arduino
const int pinClock = 3;  // Pin SCK del HX711 al pin D3 del Arduino

HX711 sensorPresion;

void setup() {
  Serial.begin(9600);
  
  // Inicializa el módulo usando el Canal A con la ganancia máxima (128)
  sensorPresion.begin(pinData, pinClock);
  
  Serial.println("Iniciando lecturas del HX711...");
}

void loop() {
  // Verificamos si el módulo tiene una lectura lista
  if (sensorPresion.is_ready()) {
    
    // read_average(10) toma 10 lecturas seguidas y te da el promedio.
    // Esto es excelente para eliminar el ruido eléctrico del USB.
    long lecturaPromedio = sensorPresion.read_average(10);
    
    Serial.print("Valor digital (24 bits): ");
    Serial.println(lecturaPromedio);
    
  } else {
    Serial.println("Error: No se detecta el módulo HX711. Revisá los cables.");
  }
  
  delay(250); // Espera un cuarto de segundo antes de la próxima medición
}
