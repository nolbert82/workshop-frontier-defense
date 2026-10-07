/*
 * SENTINEL-X — Test 03 : DHT22 (température et humidité)
 * ------------------------------------------------------
 * Bibliothèques à installer : "DHT sensor library" (Adafruit) + accepter
 *                             "Adafruit Unified Sensor".
 *
 * Câblage testé : VCC -> rail 3,3 V ; GND -> GND ; DATA -> D4
 *                 (module 3 broches : résistance de tirage déjà intégrée)
 *
 * Résultat attendu : une mesure toutes les 2,5 s dans le moniteur série.
 *   Température ambiante ~18-28 °C, humidité ~30-70 %.
 * Test de réaction : souffler doucement sur le capteur -> l'humidité monte
 *   nettement ; le pincer entre les doigts -> la température monte lentement.
 *
 * Le DHT22 est LENT : il ne faut pas le lire plus d'une fois toutes les 2 s,
 * sinon il renvoie des erreurs (NaN = "Not a Number" = lecture ratée).
 */

#include <DHT.h>

const int PIN_DHT = 4;
DHT dht(PIN_DHT, DHT22);

const unsigned long PERIODE_MS = 2500;  // > 2 s, marge de sécurité
unsigned long nbLectures = 0;
unsigned long nbErreurs  = 0;

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n=== SENTINEL-X : test du DHT22 ===");
  dht.begin();
  delay(2000);  // le capteur a besoin d'un moment après la mise sous tension
}

void loop() {
  float humidite    = dht.readHumidity();
  float temperature = dht.readTemperature();   // en °C
  nbLectures++;

  if (isnan(humidite) || isnan(temperature)) {
    nbErreurs++;
    Serial.printf("ERREUR de lecture (%lu/%lu) : verifier DATA sur D4, VCC sur 3,3 V, GND\n",
                  nbErreurs, nbLectures);
  } else {
    Serial.printf("Temperature : %.1f C   |   Humidite : %.1f %%   (erreurs : %lu/%lu)\n",
                  temperature, humidite, nbErreurs, nbLectures);
  }

  // Une erreur isolée de temps en temps est normale ; des erreurs en continu = câblage.
  delay(PERIODE_MS);
}
