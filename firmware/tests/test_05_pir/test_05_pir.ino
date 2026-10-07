/*
 * SENTINEL-X — Test 05 : PIR HC-SR501 (présence / intrusion)
 * ----------------------------------------------------------
 * Aucune bibliothèque nécessaire.
 *
 * Câblage testé : VCC -> rail 5 V ; OUT -> D13 ; GND -> GND
 *                 + LED rouge sur D25 (déjà testée au test 01) qui recopie le PIR
 * Réglages du module : cavalier en H, potentiomètre Tx au minimum, Sx au milieu.
 *
 * Un message "etat actuel" s'affiche toutes les 5 s, même sans mouvement.
 * Un caractère bizarre (losange avec "?") au démarrage est normal : bruit du reset.
 *
 * Résultats attendus :
 *   - Pendant ~60 s après la mise sous tension : déclenchements possibles
 *     sans raison (stabilisation), c'est normal.
 *   - Ensuite : passer la main ou marcher devant -> "MOUVEMENT DETECTE",
 *     LED rouge allumée ; quelques secondes après l'arrêt -> "fin de mouvement".
 *   - Après chaque fin de mouvement, le PIR est "aveugle" ~3 s : normal.
 *
 * Si rien ne se passe jamais : vérifier VCC sur le 5 V (pas le 3,3 V !) et OUT sur D13.
 * Si ça se déclenche tout seul après 60 s : éloigner le PIR de l'antenne de
 * l'ESP32, d'une fenêtre ou d'un radiateur, ou baisser Sx.
 */

const int PIN_PIR   = 13;
const int LED_ROUGE = 25;
const unsigned long STABILISATION_MS = 60000;

int etatPrecedent = LOW;
unsigned long debutMouvement = 0;
unsigned long nbDetections = 0;
unsigned long dernierEtatAffiche = 0;   // pour le message périodique

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n=== SENTINEL-X : test du PIR ===");

  // INPUT_PULLDOWN : si le fil OUT est débranché, la broche lit 0 au lieu de "flotter"
  pinMode(PIN_PIR, INPUT_PULLDOWN);
  pinMode(LED_ROUGE, OUTPUT);
  digitalWrite(LED_ROUGE, LOW);

  Serial.println("Stabilisation du PIR pendant 60 s : ne pas bouger devant si possible.");
}

void loop() {
  int etat = digitalRead(PIN_PIR);      // HIGH (1) = mouvement, LOW (0) = rien
  digitalWrite(LED_ROUGE, etat);        // la LED rouge recopie l'état du PIR

  // On n'affiche que les CHANGEMENTS d'état (sinon le moniteur déborde)
  if (etat != etatPrecedent) {
    unsigned long t = millis();
    const char* note = (t < STABILISATION_MS) ? "  (stabilisation, a ignorer)" : "";

    if (etat == HIGH) {
      nbDetections++;
      debutMouvement = t;
      Serial.printf("[%6.1fs] MOUVEMENT DETECTE (#%lu)%s\n", t / 1000.0, nbDetections, note);
    } else {
      Serial.printf("[%6.1fs] fin de mouvement (sortie restee haute %.1f s)%s\n",
                    t / 1000.0, (t - debutMouvement) / 1000.0, note);
    }
    etatPrecedent = etat;
  }

  // Message toutes les 5 s, même sans mouvement : prouve que le programme tourne
  // (sinon le moniteur reste vide tant que personne ne bouge devant le PIR)
  if (millis() - dernierEtatAffiche >= 5000) {
    dernierEtatAffiche = millis();
    Serial.printf("[%6.1fs] etat actuel : %s  |  detections : %lu\n",
                  millis() / 1000.0, etat == HIGH ? "MOUVEMENT" : "calme", nbDetections);
  }

  delay(50);   // 20 lectures par seconde, largement suffisant pour un PIR
}
