#pragma once
/*
 * SENTINEL-X — Réglages NON secrets du firmware.
 * Les mots de passe, l'IP du broker et le certificat sont dans secrets.h
 * (fichier ignoré par Git, généré par scripts/firmware_secrets.py).
 */

// ---------- Identité (doit correspondre aux ACL Mosquitto et au backend) ----------
#define DEVICE_ID        "sentinel-x-01"
#define FIRMWARE_VERSION "1.0.0"

// ---------- Broches (cf. guide de câblage, identiques aux sketches de test) ----------
#define PIN_SDA        21   // OLED I2C
#define PIN_SCL        22
#define OLED_ADDR      0x3C
#define PIN_DHT        4    // DHT22 : température / humidité
#define PIN_PIR        13   // PIR HC-SR501 : présence
#define PIN_MQ2        34   // MQ-2 : gaz (ADC1, via pont diviseur 10k/10k)
#define LED_ROUGE      25   // Alarme : commande "buzzer" (+ réflexe local PIR)
#define LED_JAUNE      26   // LED de test : commande "led"
#define LED_BLEUE      27   // LED système : fixe = prêt, clignote = dégradé

// Buzzer optionnel : passer HAS_BUZZER à 1 si un buzzer ACTIF est branché sur le GPIO 33.
#define HAS_BUZZER     0
#define PIN_BUZZER     33

// Réflexe local "edge" : la LED rouge s'allume fixe pendant un mouvement PIR,
// même si le réseau est coupé. Mettre à 0 pour la réserver aux commandes.
#define LOCAL_PIR_REFLEX 1

// ---------- TLS ----------
// Nom vérifié dans le certificat du broker. Le certificat généré par
// scripts/setup.py contient le nom DNS "mosquitto" : on se connecte à l'IP
// du broker mais on vérifie ce nom, ce qui reste valable même si l'IP du
// hotspot change. Le certificat doit être signé par la CA de secrets.h.
#define TLS_SERVER_NAME "mosquitto"

// ---------- Rythmes (ms) — cf. SPECIFICATIONS.md §4 et docs/INTEGRATION.md ----------
#define TELEMETRY_PERIOD_MS   1000   // 1 message par seconde
#define DHT_PERIOD_MS         2000   // DHT22 lu toutes les 2 s (minimum du capteur)
#define DHT_STALE_MS          6000   // au-delà : mesure "stale" (périmée)
#define PIR_PERIOD_MS         50     // échantillonnage PIR
#define PIR_HOLD_MS           2000   // anti-rebond : présence maintenue 2 s après le dernier signal
#define PIR_WARMUP_MS         30000  // stabilisation du HC-SR501 après mise sous tension
#define MQ2_WARMUP_MS         120000 // chauffe du MQ-2 : valeurs null pendant 2 min
#define MQ2_DISCONNECTED_RAW  5      // ADC <= 5 en continu : capteur débranché (santé, pas une alerte gaz)

// ---------- Fiabilité (tampon et reprise) ----------
#define BUFFER_SIZE           60     // mesures conservées en RAM en attendant le reçu du backend
#define RECEIPT_TIMEOUT_MS    5000   // sans reçu après 5 s : la mesure sera renvoyée (replayed:true)
#define LIVE_MAX_AGE_MS       3000   // mesure plus vieille : jamais envoyée comme "direct"
#define REPLAY_INTERVAL_MS    250    // débit de rejeu limité : 4 mesures/s maximum
#define ACK_CACHE_SIZE        20     // résultats de commandes mémorisés (doublons)

// ---------- Connexion ----------
#define MQTT_KEEPALIVE_S      10     // Last Will publié ~15 s après une coupure brutale
#define MQTT_BACKOFF_MAX_MS   10000  // reconnexion progressive plafonnée à 10 s
#define TLS_CONNECT_TIMEOUT_MS 5000
#define TLS_HANDSHAKE_TIMEOUT_S 10
#define MQTT_BUFFER_BYTES     1024   // télémétrie ~450 octets (défaut de la lib : 128)
