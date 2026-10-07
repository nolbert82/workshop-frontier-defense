/*
 * SENTINEL-X — Test 04 : MQ-2 (gaz et fumées) + pont diviseur
 * -----------------------------------------------------------
 * Aucune bibliothèque nécessaire.
 *
 * Câblage testé : VCC -> rail 5 V ; GND -> GND ; D0 non branchée
 *                 A0 -> R4 10k -> rangée de jonction -> R5 10k -> GND
 *                 rangée de jonction -> D34
 *
 * Ce que le programme affiche chaque seconde :
 *   - brut      : valeur du convertisseur, de 0 à 4095 (12 bits)
 *   - mV_D34    : tension réellement présente sur la broche D34
 *   - mV_A0     : tension de sortie du MQ-2 = mV_D34 x 2 (à cause du pont)
 *
 * Résultats attendus :
 *   - Pendant les premières minutes : valeurs hautes qui DESCENDENT doucement
 *     (le capteur chauffe). Attendre au moins 3-5 min avant de juger.
 *   - Air propre, capteur chaud : valeur stable, mV_A0 typiquement 300-1500 mV
 *     (dépend du réglage du module : ce qui compte, c'est la stabilité).
 *   - Test : gaz de briquet SANS FLAMME, 1-2 s à quelques cm, pièce aérée
 *     -> la valeur monte fortement en quelques secondes puis redescend.
 *
 * SÉCURITÉ : si mV_D34 dépasse 3000 mV, le programme affiche une alerte.
 * Cela voudrait dire que le pont diviseur est mal câblé -> débrancher l'USB.
 */

const int   PIN_MQ2    = 34;     // ADC1 : fonctionne même avec le Wi-Fi actif
const float RATIO_PONT = 2.0;    // R4 = R5 -> la tension est divisée par 2
const int   NB_ECHANTILLONS = 20;            // moyenne pour lisser le bruit de l'ADC
const unsigned long DUREE_CHAUFFE_S = 180;   // 3 min de chauffe minimum

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n=== SENTINEL-X : test du MQ-2 ===");
  analogReadResolution(12);   // 12 bits : 0..4095
  // Atténuation par défaut de l'ESP32 = 11 dB -> mesure possible jusqu'à ~3,1 V
  Serial.println("Le capteur chauffe : valeurs peu fiables pendant ~3 min.");
}

void loop() {
  // Moyenne de plusieurs lectures : l'ADC de l'ESP32 est un peu bruité
  long sommeBrut = 0;
  long sommeMv   = 0;
  for (int i = 0; i < NB_ECHANTILLONS; i++) {
    sommeBrut += analogRead(PIN_MQ2);
    sommeMv   += analogReadMilliVolts(PIN_MQ2);  // valeur calibrée en usine, en mV
    delay(5);
  }
  int brut  = sommeBrut / NB_ECHANTILLONS;
  int mvD34 = sommeMv   / NB_ECHANTILLONS;
  int mvA0  = mvD34 * RATIO_PONT;

  unsigned long secondes = millis() / 1000;
  const char* etat = (secondes < DUREE_CHAUFFE_S) ? "CHAUFFE" : "pret";

  Serial.printf("[%4lus %-7s] brut=%4d   mV_D34=%4d   mV_A0=%4d\n",
                secondes, etat, brut, mvD34, mvA0);

  if (mvD34 > 3000) {
    Serial.println("!!! ALERTE : tension trop haute sur D34. Verifier le pont R4/R5, debrancher l'USB !!!");
  }
  if (brut == 0) {
    Serial.println("    (valeur nulle : A0 non branchee, R4 absente ou D34 reliee a GND ?)");
  }

  delay(1000);
}
