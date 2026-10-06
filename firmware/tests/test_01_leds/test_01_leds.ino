/*
 * SENTINEL-X — Test 01 : LEDs (alertes et statut)
 * ------------------------------------------------
 * But : vérifier le câblage des 3 LEDs ET toute la chaîne de téléversement
 *       (driver USB, carte, IDE). C'est le test le plus simple : à faire en premier.
 *
 * Câblage testé :  D25 -> R1 220/150 ohms -> LED rouge (+) ; (-) -> GND
 *                  D26 -> R2 -> LED jaune ; D27 -> R3 -> LED bleue
 *
 * Résultat attendu : rouge, jaune, bleue s'allument 1 s chacune, puis les 3
 *                    ensemble, en boucle. Le moniteur série (115200) indique
 *                    quelle LED DEVRAIT être allumée.
 * Si une LED reste éteinte : la retourner (grande patte côté résistance),
 *                    vérifier que ses 2 pattes sont dans 2 rangées différentes.
 */

// Numéros GPIO (sérigraphie D25 = GPIO 25 ; dans le code on écrit juste 25)
const int LED_ROUGE = 25;  // Alerte intrusion
const int LED_JAUNE = 26;  // Alerte environnement
const int LED_BLEUE = 27;  // Statut connexion

const int LEDS[]   = {LED_ROUGE, LED_JAUNE, LED_BLEUE};
const char* NOMS[] = {"ROUGE (D25)", "JAUNE (D26)", "BLEUE (D27)"};

void toutEteindre() {
  for (int i = 0; i < 3; i++) digitalWrite(LEDS[i], LOW);
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n=== SENTINEL-X : test des LEDs ===");

  // Les broches des LEDs sont des SORTIES : l'ESP32 envoie 3,3 V (HIGH) ou 0 V (LOW)
  for (int i = 0; i < 3; i++) pinMode(LEDS[i], OUTPUT);
  toutEteindre();
}

void loop() {
  // 1) Chaque LED seule, l'une après l'autre
  for (int i = 0; i < 3; i++) {
    Serial.printf("LED %s allumee\n", NOMS[i]);
    digitalWrite(LEDS[i], HIGH);
    delay(1000);
    digitalWrite(LEDS[i], LOW);
  }

  // 2) Les 3 ensemble (vérifie qu'aucune ne baisse quand les autres s'allument)
  Serial.println("Les 3 LEDs allumees");
  for (int i = 0; i < 3; i++) digitalWrite(LEDS[i], HIGH);
  delay(1000);
  toutEteindre();

  Serial.println("--- tour termine ---");
  delay(1000);
}
