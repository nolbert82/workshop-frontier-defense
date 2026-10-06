#pragma once
/*
 * MODÈLE — copier en "secrets.h" (ignoré par Git) et remplir.
 * Le plus simple : python3 scripts/firmware_secrets.py (voir firmware/sentinel_x/README.md)
 */

// Wi-Fi de la table (2,4 GHz obligatoire)
#define WIFI_SSID       "CHANGE_ME"
#define WIFI_PASSWORD   "CHANGE_ME"

// Broker Mosquitto (IP du PC serveur sur le Wi-Fi de la table) — secrets/device.json
#define MQTT_BROKER_IP  "192.168.137.1"
#define MQTT_PORT       8883
#define MQTT_USER       "sentinel-x-01"
#define MQTT_PASSWORD   "CHANGE_ME"

// Autorité de certification locale (contenu de secrets/ca.crt, public)
static const char MQTT_CA_CERT[] = R"PEM(
-----BEGIN CERTIFICATE-----
CHANGE_ME
-----END CERTIFICATE-----
)PEM";
