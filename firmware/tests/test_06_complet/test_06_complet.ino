/*
 * SENTINEL-X — Test 06 : tous les composants ensemble
 * ---------------------------------------------------
 * À lancer seulement quand les tests 01 à 05 sont OK séparément.
 * Bibliothèques : Adafruit SSD1306 (+ GFX, BusIO), DHT sensor library (+ Unified Sensor)
 *
 * Ce que fait ce test :
 *   - lit chaque capteur à SON rythme, sans jamais bloquer les autres (millis()) :
 *       PIR toutes les 50 ms, MQ-2 toutes les 1 s, DHT22 toutes les 2,5 s
 *   - affiche les mesures sur l'OLED (rafraîchi toutes les 0,5 s)
 *   - écrit une ligne CSV par seconde dans le moniteur série
 *     (copiable dans un fichier pour un premier coup d'œil aux données)
 *   - LEDs, POUR CE TEST UNIQUEMENT :
 *       rouge = recopie le PIR
 *       jaune = clignote pendant la chauffe du MQ-2 (3 min), puis s'éteint
 *       bleue = clignote 1 fois/s ("battement de cœur" : la boucle tourne)
 *     Dans le firmware final, la jaune sera commandée par le serveur
 *     (modèle prédictif), JAMAIS par un seuil codé ici.
 *
 * Résultat attendu : écran vivant, valeurs cohérentes, aucune LED figée,
 * et le PIR réagit instantanément même pendant une lecture du DHT22.
 */

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <DHT.h>

// ---------- Broches (cf. guide de câblage) ----------
const int PIN_SDA = 21, PIN_SCL = 22;   // OLED
const int PIN_DHT = 4;                  // DHT22 : température / humidité
const int PIN_PIR = 13;                 // PIR : présence
const int PIN_MQ2 = 34;                 // MQ-2 : gaz (via pont diviseur)
const int LED_ROUGE = 25, LED_JAUNE = 26, LED_BLEUE = 27;

const float RATIO_PONT = 2.0;
const unsigned long CHAUFFE_MQ2_MS = 180000;   // 3 min

// ---------- Objets ----------
Adafruit_SSD1306 ecran(128, 64, &Wire, -1);
DHT dht(PIN_DHT, DHT22);
bool ecranOK = false;

// ---------- Dernières mesures connues ----------
float temperature = NAN, humidite = NAN;
int   gazMvA0 = 0;
int   pir = 0;
unsigned long nbDetections = 0;

// ---------- Horloges : instant du dernier passage de chaque tâche ----------
unsigned long tPir = 0, tGaz = 0, tDht = 0, tEcran = 0, tCsv = 0, tCoeur = 0;

void lirePir() {
  int etat = digitalRead(PIN_PIR);
  if (etat == HIGH && pir == LOW) nbDetections++;   // front montant = nouvelle détection
  pir = etat;
  digitalWrite(LED_ROUGE, pir);
}

void lireGaz() {
  long somme = 0;
  for (int i = 0; i < 10; i++) somme += analogReadMilliVolts(PIN_MQ2);
  gazMvA0 = (somme / 10) * RATIO_PONT;   // tension réelle en sortie A0 du MQ-2
}

void lireDht() {
  float h = dht.readHumidity();
  float t = dht.readTemperature();
  // On garde l'ancienne valeur si la lecture échoue (évite les trous à l'écran)
  if (!isnan(h) && !isnan(t)) { humidite = h; temperature = t; }
}

void afficherEcran() {
  if (!ecranOK) return;
  ecran.clearDisplay();
  ecran.setCursor(0, 0);
  ecran.println("SENTINEL-X  test");
  ecran.drawLine(0, 9, 127, 9, SSD1306_WHITE);
  ecran.setCursor(0, 14);
  if (isnan(temperature)) ecran.println("Temp : --");
  else                    ecran.printf("Temp : %.1f C\n", temperature);
  if (isnan(humidite))    ecran.println("Hum  : --");
  else                    ecran.printf("Hum  : %.1f %%\n", humidite);
  ecran.printf("Gaz  : %d mV%s\n", gazMvA0, millis() < CHAUFFE_MQ2_MS ? " (chauffe)" : "");
  ecran.printf("PIR  : %s (%lu)\n", pir ? "MOUVEMENT" : "calme", nbDetections);
  ecran.printf("Up   : %lus\n", millis() / 1000);
  ecran.display();
}

void ecrireCsv() {
  // Format : temps_ms,temperature_C,humidite_pct,gaz_mV_A0,pir
  Serial.printf("%lu,%.1f,%.1f,%d,%d\n", millis(), temperature, humidite, gazMvA0, pir);
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n=== SENTINEL-X : test complet ===");

  pinMode(PIN_PIR, INPUT_PULLDOWN);
  pinMode(LED_ROUGE, OUTPUT);
  pinMode(LED_JAUNE, OUTPUT);
  pinMode(LED_BLEUE, OUTPUT);
  analogReadResolution(12);

  Wire.begin(PIN_SDA, PIN_SCL);
  ecranOK = ecran.begin(SSD1306_SWITCHCAPVCC, 0x3C);   // 0x3D si le test 02 l'a indiqué
  if (ecranOK) {
    ecran.setTextColor(SSD1306_WHITE);
    ecran.setTextSize(1);
  } else {
    Serial.println("Ecran non detecte : le test continue sans affichage.");
  }

  dht.begin();
  Serial.println("temps_ms,temperature_C,humidite_pct,gaz_mV_A0,pir");
}

void loop() {
  unsigned long maintenant = millis();

  // Chaque bloc ne s'exécute que si son intervalle est écoulé : rien ne bloque.
  if (maintenant - tPir   >= 50)   { tPir   = maintenant; lirePir(); }
  if (maintenant - tGaz   >= 1000) { tGaz   = maintenant; lireGaz(); }
  if (maintenant - tDht   >= 2500) { tDht   = maintenant; lireDht(); }
  if (maintenant - tEcran >= 500)  { tEcran = maintenant; afficherEcran(); }
  if (maintenant - tCsv   >= 1000) { tCsv   = maintenant; ecrireCsv(); }

  // Battement de cœur (bleue) + indicateur de chauffe (jaune), toutes les 500 ms
  if (maintenant - tCoeur >= 500) {
    tCoeur = maintenant;
    bool phase = (maintenant / 500) % 2;
    digitalWrite(LED_BLEUE, phase);
    digitalWrite(LED_JAUNE, (maintenant < CHAUFFE_MQ2_MS) ? phase : LOW);
  }
}
