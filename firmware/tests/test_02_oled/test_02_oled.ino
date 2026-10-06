/*
 * SENTINEL-X — Test 02 : écran OLED I2C 0,96" (affichage local)
 * -------------------------------------------------------------
 * Bibliothèques à installer : "Adafruit SSD1306" (accepter l'installation des
 *                             dépendances : Adafruit GFX, Adafruit BusIO).
 *
 * Câblage testé : VCC -> rail 3,3 V ; GND -> GND ; SDA -> D21 ; SCL -> D22
 *
 * Étape 1 : le programme SCANNE le bus I2C et affiche dans le moniteur série
 *           l'adresse de chaque périphérique trouvé (écran : 0x3C en général).
 * Étape 2 : il affiche "SENTINEL-X" et un compteur qui augmente chaque seconde.
 *
 * Dépannage :
 *  - "Aucun peripherique" : fils VCC/GND/SDA/SCL, ou SDA et SCL inversés.
 *  - Texte écrasé ou seulement la moitié de l'écran : mettre HAUTEUR à 32.
 *  - Image décalée / pixels parasites : l'écran est peut-être un SH1106
 *    (pas un SSD1306) -> nous prévenir, on changera de bibliothèque.
 */

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

#define PIN_SDA 21
#define PIN_SCL 22
#define LARGEUR 128
#define HAUTEUR 64   // 128x64 le plus souvent ; mettre 32 pour un écran 128x32

// -1 = pas de broche RESET câblée sur ce module
Adafruit_SSD1306 ecran(LARGEUR, HAUTEUR, &Wire, -1);

// Parcourt les 126 adresses I2C possibles et renvoie celle de l'écran (0 si absent)
uint8_t scannerI2C() {
  uint8_t adresseEcran = 0;
  int nb = 0;
  Serial.println("Scan du bus I2C...");
  for (uint8_t adr = 1; adr < 127; adr++) {
    Wire.beginTransmission(adr);
    if (Wire.endTransmission() == 0) {          // 0 = le périphérique a répondu
      Serial.printf("  Peripherique trouve a l'adresse 0x%02X\n", adr);
      nb++;
      if (adr == 0x3C || adr == 0x3D) adresseEcran = adr;  // adresses typiques d'un OLED
    }
  }
  if (nb == 0) {
    Serial.println("  Aucun peripherique : verifier VCC, GND, SDA (D21), SCL (D22).");
  }
  return adresseEcran;
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n=== SENTINEL-X : test de l'ecran OLED ===");

  Wire.begin(PIN_SDA, PIN_SCL);   // démarre le bus I2C sur D21 / D22

  uint8_t adresse = scannerI2C();
  if (adresse == 0) {
    Serial.println("ECHEC : aucun ecran OLED detecte. Arret du test.");
    while (true) delay(1000);
  }

  // SSD1306_SWITCHCAPVCC = l'écran fabrique lui-même sa haute tension interne
  if (!ecran.begin(SSD1306_SWITCHCAPVCC, adresse)) {
    Serial.println("ECHEC : initialisation de l'ecran impossible.");
    while (true) delay(1000);
  }

  ecran.clearDisplay();
  ecran.setTextColor(SSD1306_WHITE);
  ecran.setTextSize(1);            // taille 1 = 6x8 pixels par caractère
  ecran.setCursor(0, 0);
  ecran.println("SENTINEL-X");
  ecran.println("Test OLED : OK");
  ecran.display();                 // rien ne s'affiche tant qu'on n'appelle pas display()

  Serial.printf("OK : ecran initialise a l'adresse 0x%02X\n", adresse);
}

void loop() {
  static unsigned long compteur = 0;

  // On efface seulement la zone du compteur, puis on la redessine
  ecran.fillRect(0, 24, LARGEUR, 16, SSD1306_BLACK);
  ecran.setCursor(0, 24);
  ecran.setTextSize(2);            // gros chiffres, 12x16 pixels
  ecran.print(compteur++);
  ecran.setTextSize(1);
  ecran.display();

  delay(1000);
}
