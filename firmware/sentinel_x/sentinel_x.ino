/*
 * SENTINEL-X — Firmware du boîtier Edge (ESP32 DevKit V1)
 * =========================================================
 * Rôle : lire DHT22 / MQ-2 / PIR, publier la télémétrie en MQTTS vers
 * Mosquitto, exécuter les commandes du dashboard (alarme, LED de test)
 * et afficher l'état sur l'OLED.
 *
 * Contrat respecté : docs/INTEGRATION.md + SPECIFICATIONS.md §4-5
 *   publie  sentinel/sentinel-x-01/telemetry  (QoS 1, 1 msg/s, non retenu)
 *           sentinel/sentinel-x-01/status     (QoS 1, RETENU, Last Will offline)
 *           sentinel/sentinel-x-01/acks       (QoS 1, accusés de commandes)
 *   reçoit  sentinel/sentinel-x-01/commands   (QoS 1)
 *           sentinel/sentinel-x-01/receipts   (QoS 1, reçus de stockage du backend)
 *
 * Bibliothèques (Gestionnaire de bibliothèques Arduino IDE) :
 *   - "MQTT" par Joel Gaehwiler (arduino-mqtt)  >= 2.5  -> QoS 1 en publication
 *   - "ArduinoJson" par Benoit Blanchon           >= 7.0
 *   - "Adafruit SSD1306" (+ GFX, BusIO), "DHT sensor library" (+ Unified Sensor)
 * Carte : "DOIT ESP32 DEVKIT V1", paquet esp32 by Espressif >= 3.0
 *
 * Secrets : secrets.h (ignoré par Git), généré par scripts/firmware_secrets.py
 */

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <MQTT.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <DHT.h>
#include <esp_timer.h>
#include <esp_random.h>

#include "config.h"
#if __has_include("secrets.h")
#include "secrets.h"
#else
#error "secrets.h absent : lancer scripts/firmware_secrets.py (voir firmware/sentinel_x/README.md)"
#endif

#define TOPIC(name) "sentinel/" DEVICE_ID "/" name
static const char *T_TELEMETRY = TOPIC("telemetry");
static const char *T_STATUS    = TOPIC("status");
static const char *T_ACKS      = TOPIC("acks");
static const char *T_COMMANDS  = TOPIC("commands");
static const char *T_RECEIPTS  = TOPIC("receipts");

// =====================================================================
//  Types
// =====================================================================
enum SensorState : uint8_t { ST_OK, ST_ERROR, ST_STALE, ST_WARMING };
static const char *STATE_NAMES[] = {"ok", "error", "stale", "warming_up"};

// Mesure compacte (~48 octets) : 60 mesures = moins de 3 Ko de RAM.
struct Sample {
  bool used;
  uint32_t seq;
  uint64_t uptime;          // instant de capture (ms depuis le démarrage)
  float temp, hum;          // NAN si capteur non "ok"
  int16_t gas;              // -1 si capteur non "ok"
  int8_t presence;          // -1 si capteur non "ok", sinon 0/1
  uint32_t ageDht, ageMq2, agePir;
  uint8_t stDht, stMq2, stPir;
  uint16_t attempts;        // nombre d'envois MQTT
  uint32_t lastSentMs;
};

struct AckEntry {
  bool used;
  char id[65];
  bool executed;
  char reason[32];
};

// =====================================================================
//  Client TLS : on se connecte à l'IP du broker, mais on vérifie le nom
//  TLS_SERVER_NAME présent dans son certificat, et la chaîne jusqu'à
//  notre CA. Aucun setInsecure() : un faux broker est refusé.
// =====================================================================
class BrokerClient : public WiFiClientSecure {
 public:
  using WiFiClientSecure::connect;
  int connect(IPAddress ip, uint16_t port) override {
    _timeout = TLS_CONNECT_TIMEOUT_MS;
    return WiFiClientSecure::connect(ip, port, TLS_SERVER_NAME, MQTT_CA_CERT, nullptr, nullptr);
  }
};

// =====================================================================
//  Objets et état global
// =====================================================================
Adafruit_SSD1306 oled(128, 64, &Wire, -1);
DHT dht(PIN_DHT, DHT22);
BrokerClient net;
MQTTClient mqtt(MQTT_BUFFER_BYTES);
IPAddress brokerIp;

char bootId[9];
uint32_t sequence = 0;
uint32_t lostCount = 0;
uint32_t receiptsOk = 0, mqttConnects = 0;
uint32_t lastReceiptMs = 0;
bool oledOk = false;

// Capteurs
float dhtT = NAN, dhtH = NAN;
bool dhtEverOk = false, dhtLastFailed = false;
uint32_t dhtOkAt = 0;
int lastGasRaw = 0;
bool pirEverHigh = false;
uint32_t pirLastHigh = 0, pirLastSample = 0;

// Tampon de fiabilité
Sample buffer[BUFFER_SIZE];
uint32_t lastReplayMs = 0;

// Commandes
AckEntry ackCache[ACK_CACHE_SIZE];
uint8_t ackCacheNext = 0;
String cmdQueue[6];
uint8_t cmdHead = 0, cmdCount = 0;
AckEntry ackQueue[8];
uint8_t ackHead = 0, ackCount = 0;
char lastCmdText[22] = "-";

// Actionneurs
bool alarmOn = false, testLedOn = false;
uint32_t alarmUntil = 0, testLedUntil = 0;

// Horloges des tâches
uint32_t tPir = 0, tDht = 0, tTele = 0, tOled = 0, tLog = 0;

// =====================================================================
//  Utilitaires
// =====================================================================
uint64_t uptimeMs() { return (uint64_t)(esp_timer_get_time() / 1000); }
bool wifiUp() { return WiFi.status() == WL_CONNECTED; }
float round1(float v) { return roundf(v * 10.0f) / 10.0f; }
uint32_t clampAge(uint32_t v) { return v > 86400000UL ? 86400000UL : v; }

// =====================================================================
//  Capteurs
// =====================================================================
void samplePir() {
  if (digitalRead(PIN_PIR) == HIGH) {
    pirLastHigh = millis();
    pirEverHigh = true;
  }
  pirLastSample = millis();
}

// Anti-rebond : la présence reste vraie PIR_HOLD_MS après le dernier signal.
bool presenceNow() { return pirEverHigh && (millis() - pirLastHigh) < PIR_HOLD_MS; }

void readDht() {
  float t = dht.readTemperature(false, true);  // force une vraie lecture
  float h = dht.readHumidity();                 // même trame que la température
  if (!isnan(t) && !isnan(h) && t >= -40 && t <= 80 && h >= 0 && h <= 100) {
    dhtT = t;
    dhtH = h;
    dhtOkAt = millis();
    dhtEverOk = true;
    dhtLastFailed = false;
  } else {
    dhtLastFailed = true;
  }
}

int readMq2Raw() {
  long sum = 0;
  for (int i = 0; i < 8; i++) sum += analogRead(PIN_MQ2);  // 0-4095, ADC1 (compatible Wi-Fi)
  return (int)(sum / 8);
}

// Construit une mesure à l'instant présent (appelée 1 fois/s)
Sample acquire() {
  uint32_t now = millis();
  Sample s = {};
  s.used = true;
  s.seq = ++sequence;
  s.uptime = uptimeMs();

  // DHT22 : dernière valeur conservée avec son âge, périmée après 6 s
  uint32_t age = dhtEverOk ? now - dhtOkAt : now;
  if (dhtEverOk && age <= DHT_STALE_MS) s.stDht = ST_OK;
  else if (!dhtEverOk && now < 10000) s.stDht = ST_WARMING;
  else if (dhtLastFailed) s.stDht = ST_ERROR;
  else s.stDht = ST_STALE;
  s.ageDht = clampAge(age);
  s.temp = (s.stDht == ST_OK) ? round1(dhtT) : NAN;
  s.hum = (s.stDht == ST_OK) ? round1(dhtH) : NAN;

  // MQ-2 : valeur ADC brute, null pendant la chauffe
  lastGasRaw = readMq2Raw();
  if (now < MQ2_WARMUP_MS) s.stMq2 = ST_WARMING;
  else if (lastGasRaw <= MQ2_DISCONNECTED_RAW) s.stMq2 = ST_ERROR;  // santé du câblage, pas une alerte gaz
  else s.stMq2 = ST_OK;
  s.ageMq2 = 0;
  s.gas = (s.stMq2 == ST_OK) ? (int16_t)lastGasRaw : -1;

  // PIR : null pendant sa stabilisation
  s.stPir = (now < PIR_WARMUP_MS) ? ST_WARMING : ST_OK;
  s.agePir = clampAge(now - pirLastSample);
  s.presence = (s.stPir == ST_OK) ? (presenceNow() ? 1 : 0) : -1;
  return s;
}

// =====================================================================
//  Tampon : on garde chaque mesure jusqu'au reçu de stockage du backend
// =====================================================================
void pushSample(const Sample &s) {
  int slot = -1;
  for (int i = 0; i < BUFFER_SIZE; i++)
    if (!buffer[i].used) { slot = i; break; }
  if (slot < 0) {  // plein : on abandonne la plus ancienne et on la compte
    uint32_t oldest = UINT32_MAX;
    for (int i = 0; i < BUFFER_SIZE; i++)
      if (buffer[i].seq < oldest) { oldest = buffer[i].seq; slot = i; }
    lostCount++;
  }
  buffer[slot] = s;
}

int bufferedCount() {
  int n = 0;
  for (int i = 0; i < BUFFER_SIZE; i++) n += buffer[i].used;
  return n;
}

bool publishSample(int idx, bool replayed) {
  Sample &s = buffer[idx];
  JsonDocument d;
  d["device_id"] = DEVICE_ID;
  d["boot_id"] = bootId;
  d["sequence"] = s.seq;
  d["uptime_ms"] = s.uptime;
  d["timestamp"] = nullptr;  // pas d'heure UTC fiable sur la table : null (autorisé par le contrat)
  if (s.stDht == ST_OK) { d["temperature"] = s.temp; d["humidity"] = s.hum; }
  else { d["temperature"] = nullptr; d["humidity"] = nullptr; }
  if (s.stMq2 == ST_OK) d["gas"] = s.gas; else d["gas"] = nullptr;
  if (s.stPir == ST_OK) d["presence"] = (s.presence == 1); else d["presence"] = nullptr;
  JsonObject ages = d["sensor_age_ms"].to<JsonObject>();
  ages["dht22"] = s.ageDht;
  ages["mq2"] = s.ageMq2;
  ages["pir"] = s.agePir;
  JsonObject st = d["sensor_status"].to<JsonObject>();
  st["dht22"] = STATE_NAMES[s.stDht];
  st["mq2"] = STATE_NAMES[s.stMq2];
  st["pir"] = STATE_NAMES[s.stPir];
  d["source"] = "physical";
  d["replayed"] = replayed;
  d["lost_count"] = lostCount;

  char out[640];
  size_t n = serializeJson(d, out, sizeof(out));
  uint32_t seq = s.seq;
  bool ok = mqtt.publish(T_TELEMETRY, out, (int)n, false, 1);
  // Un reçu a pu arriver pendant l'attente du PUBACK : on retrouve la case par son numéro.
  if (ok && buffer[idx].used && buffer[idx].seq == seq) {
    buffer[idx].attempts++;
    buffer[idx].lastSentMs = millis();
  }
  return ok;
}

void serviceBuffer() {
  if (!mqtt.connected()) return;
  uint32_t now = millis();
  uint64_t up = uptimeMs();

  // 1) Direct : mesures récentes jamais envoyées, la plus récente d'abord
  for (int guard = 0; guard < 3; guard++) {
    int idx = -1;
    uint32_t best = 0;
    for (int i = 0; i < BUFFER_SIZE; i++)
      if (buffer[i].used && buffer[i].attempts == 0 && up - buffer[i].uptime <= LIVE_MAX_AGE_MS && buffer[i].seq > best) {
        best = buffer[i].seq;
        idx = i;
      }
    if (idx < 0 || !publishSample(idx, false)) break;
  }

  // 2) Rejeu à débit limité : mesures sans reçu (ou capturées pendant une coupure),
  //    les plus récentes d'abord, toujours marquées replayed:true
  if (now - lastReplayMs < REPLAY_INTERVAL_MS) return;
  int idx = -1;
  uint32_t best = 0;
  for (int i = 0; i < BUFFER_SIZE; i++) {
    Sample &s = buffer[i];
    if (!s.used) continue;
    bool due = (s.attempts == 0) || (now - s.lastSentMs >= RECEIPT_TIMEOUT_MS);
    if (due && s.seq > best) { best = s.seq; idx = i; }
  }
  if (idx >= 0) {
    publishSample(idx, true);
    lastReplayMs = now;
  }
}

// =====================================================================
//  Commandes (dashboard -> backend -> MQTT -> ESP)
// =====================================================================
int findAck(const char *id) {
  for (int i = 0; i < ACK_CACHE_SIZE; i++)
    if (ackCache[i].used && strcmp(ackCache[i].id, id) == 0) return i;
  return -1;
}

void queueAck(const AckEntry &a) {
  if (ackCount == 8) { ackHead = (ackHead + 1) % 8; ackCount--; }  // file pleine : la plus ancienne saute
  ackQueue[(ackHead + ackCount) % 8] = a;
  ackCount++;
}

void handleCommand(const String &payload) {
  JsonDocument d;
  if (deserializeJson(d, payload)) { Serial.println("[CMD] JSON invalide, ignoré"); return; }
  const char *id = d["command_id"] | (const char *)nullptr;
  if (!id || strlen(id) == 0 || strlen(id) > 64) { Serial.println("[CMD] sans command_id, ignorée"); return; }

  // Doublon (QoS 1 peut livrer deux fois) : même accusé, sans refaire l'action
  int known = findAck(id);
  if (known >= 0) { queueAck(ackCache[known]); Serial.printf("[CMD] doublon %s : accusé renvoyé\n", id); return; }

  const char *reason = nullptr;
  const char *type = d["type"] | "";
  const char *target = d["target_boot_id"] | "";
  bool valid = d["target_boot_id"].is<const char *>() && d["expires_at_uptime_ms"].is<uint64_t>() &&
               d["value"].is<bool>() && d["duration_ms"].is<int>() &&
               (strcmp(type, "buzzer") == 0 || strcmp(type, "led") == 0);
  int duration = d["duration_ms"] | 0;
  if (valid && (duration < 100 || duration > 10000)) valid = false;

  if (!valid) reason = "commande invalide";
  else if (strcmp(target, bootId) != 0) reason = "autre demarrage";
  else if (uptimeMs() > d["expires_at_uptime_ms"].as<uint64_t>()) reason = "commande expiree";

  if (!reason) {
    bool value = d["value"].as<bool>();
    if (strcmp(type, "buzzer") == 0) { alarmOn = value; alarmUntil = millis() + duration; }
    else { testLedOn = value; testLedUntil = millis() + duration; }
    snprintf(lastCmdText, sizeof(lastCmdText), "%s %s OK", type, value ? "ON" : "OFF");
  } else {
    snprintf(lastCmdText, sizeof(lastCmdText), "rejet: %.13s", reason);
  }

  AckEntry a = {};
  a.used = true;
  strlcpy(a.id, id, sizeof(a.id));
  a.executed = (reason == nullptr);
  strlcpy(a.reason, reason ? reason : "", sizeof(a.reason));
  ackCache[ackCacheNext] = a;
  ackCacheNext = (ackCacheNext + 1) % ACK_CACHE_SIZE;
  queueAck(a);
  Serial.printf("[CMD] %s type=%s -> %s %s\n", id, type, a.executed ? "executed" : "rejected", a.reason);
}

void processCommands() {
  while (cmdCount > 0) {
    String p = cmdQueue[cmdHead];
    cmdQueue[cmdHead] = "";
    cmdHead = (cmdHead + 1) % 6;
    cmdCount--;
    handleCommand(p);
  }
}

void flushAcks() {
  while (ackCount > 0 && mqtt.connected()) {
    AckEntry &a = ackQueue[ackHead];
    JsonDocument d;
    d["command_id"] = a.id;
    d["boot_id"] = bootId;
    d["result"] = a.executed ? "executed" : "rejected";
    if (a.executed) d["reason"] = nullptr; else d["reason"] = a.reason;
    char out[200];
    size_t n = serializeJson(d, out, sizeof(out));
    if (!mqtt.publish(T_ACKS, out, (int)n, false, 1)) return;  // on réessaiera au prochain tour
    ackHead = (ackHead + 1) % 8;
    ackCount--;
  }
}

void handleReceipt(const String &payload) {
  JsonDocument d;
  if (deserializeJson(d, payload)) return;
  const char *b = d["boot_id"] | "";
  if (strcmp(b, bootId) != 0 || !(d["stored"] | false)) return;
  uint32_t seq = d["sequence"] | 0;
  for (int i = 0; i < BUFFER_SIZE; i++)
    if (buffer[i].used && buffer[i].seq == seq) { buffer[i].used = false; break; }
  receiptsOk++;
  lastReceiptMs = millis();
}

// Appelé par la bibliothèque MQTT. Pas de publish ici (la lib n'est pas réentrante) :
// les commandes sont mises en file et traitées dans loop().
void onMqttMessage(String &topic, String &payload) {
  if (topic == T_RECEIPTS) {
    handleReceipt(payload);
  } else if (topic == T_COMMANDS) {
    if (cmdCount == 6) { Serial.println("[CMD] file pleine, commande ignorée"); return; }
    cmdQueue[(cmdHead + cmdCount) % 6] = payload;
    cmdCount++;
  }
}

// =====================================================================
//  Réseau : Wi-Fi + MQTTS avec reconnexion progressive (max 10 s)
// =====================================================================
void ensureWifi() {
  static uint32_t lastTry = 0;
  if (wifiUp()) return;
  if (millis() - lastTry > 15000) {
    Serial.println("[WIFI] reconnexion...");
    WiFi.disconnect();
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    lastTry = millis();
  }
}

void ensureMqtt() {
  static uint32_t nextTry = 0, backoff = 1000;
  if (mqtt.connected() || !wifiUp()) return;
  if ((int32_t)(millis() - nextTry) < 0) return;

  Serial.printf("[MQTT] connexion TLS a %s:%d (verifie '%s')...\n", MQTT_BROKER_IP, MQTT_PORT, TLS_SERVER_NAME);
  if (mqtt.connect(DEVICE_ID, MQTT_USER, MQTT_PASSWORD)) {
    backoff = 1000;
    mqttConnects++;
    mqtt.subscribe(T_COMMANDS, 1);
    mqtt.subscribe(T_RECEIPTS, 1);
    char status[96];
    snprintf(status, sizeof(status), "{\"state\":\"online\",\"boot_id\":\"%s\",\"firmware\":\"%s\"}", bootId, FIRMWARE_VERSION);
    mqtt.publish(T_STATUS, status, true, 1);  // retenu
    Serial.println("[MQTT] connecte");
  } else {
    char tlsErr[100] = "";
    net.lastError(tlsErr, sizeof(tlsErr));
    Serial.printf("[MQTT] echec : lwmqtt=%d retour=%d tls='%s' -> nouvel essai dans %lus\n",
                  (int)mqtt.lastError(), (int)mqtt.returnCode(), tlsErr, (unsigned long)(backoff / 1000));
    nextTry = millis() + backoff;
    backoff = min<uint32_t>(backoff * 2, MQTT_BACKOFF_MAX_MS);
  }
}

// =====================================================================
//  LEDs et écran
// =====================================================================
void updateOutputs() {
  uint32_t now = millis();
  if (alarmOn && (int32_t)(now - alarmUntil) >= 0) alarmOn = false;
  if (testLedOn && (int32_t)(now - testLedUntil) >= 0) testLedOn = false;

  // Rouge : alarme = clignotement rapide ; sinon réflexe local PIR (fixe)
  bool red = false;
  if (alarmOn) red = (now / 100) % 2;
  else if (LOCAL_PIR_REFLEX && now >= PIR_WARMUP_MS && presenceNow()) red = true;
  digitalWrite(LED_ROUGE, red);
#if HAS_BUZZER
  digitalWrite(PIN_BUZZER, alarmOn);
#endif

  // Jaune : LED de test pilotée à distance
  digitalWrite(LED_JAUNE, testLedOn);

  // Bleue : LED système. Fixe = Wi-Fi + MQTT + reçus du backend.
  // Clignote lentement = réseau OK mais broker/backend absent ; vite = pas de Wi-Fi.
  bool ready = wifiUp() && mqtt.connected() && lastReceiptMs && (now - lastReceiptMs) < 5000;
  bool blue;
  if (ready) blue = true;
  else if (wifiUp()) blue = (now / 500) % 2;
  else blue = (now / 125) % 2;
  digitalWrite(LED_BLEUE, blue);
}

void drawOled() {
  if (!oledOk) return;
  uint32_t now = millis();
  oled.clearDisplay();
  oled.setCursor(0, 0);
  oled.printf("SENTINEL-X  %s\n", bootId);
  if (wifiUp()) oled.printf("WiFi OK %ddBm .%d\n", (int)WiFi.RSSI(), WiFi.localIP()[3]);
  else oled.println("WiFi : connexion...");
  if (mqtt.connected()) oled.printf("MQTTS OK  recus %lu\n", (unsigned long)receiptsOk);
  else oled.println("MQTTS : hors ligne");
  if (dhtEverOk && now - dhtOkAt <= DHT_STALE_MS) oled.printf("T %.1fC  H %.1f%%\n", dhtT, dhtH);
  else oled.println("T/H : --");
  if (now < MQ2_WARMUP_MS) oled.printf("Gaz %d chauffe %lus\n", lastGasRaw, (unsigned long)((MQ2_WARMUP_MS - now) / 1000));
  else oled.printf("Gaz %d (ADC)\n", lastGasRaw);
  if (now < PIR_WARMUP_MS) oled.printf("PIR init %lus\n", (unsigned long)((PIR_WARMUP_MS - now) / 1000));
  else oled.println(presenceNow() ? "PIR : MOUVEMENT" : "PIR : calme");
  oled.printf("seq%lu buf%d perdu%lu\n", (unsigned long)sequence, bufferedCount(), (unsigned long)lostCount);
  oled.printf("cmd %s", lastCmdText);
  oled.display();
}

// =====================================================================
//  setup / loop
// =====================================================================
void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("\n=== SENTINEL-X firmware " FIRMWARE_VERSION " ===");

  pinMode(PIN_PIR, INPUT);
  pinMode(LED_ROUGE, OUTPUT);
  pinMode(LED_JAUNE, OUTPUT);
  pinMode(LED_BLEUE, OUTPUT);
#if HAS_BUZZER
  pinMode(PIN_BUZZER, OUTPUT);
#endif
  analogReadResolution(12);

  Wire.begin(PIN_SDA, PIN_SCL);
  oledOk = oled.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR);
  if (oledOk) {
    oled.setTextSize(1);
    oled.setTextColor(SSD1306_WHITE);
    oled.clearDisplay();
    oled.setCursor(0, 0);
    oled.println("SENTINEL-X");
    oled.println("demarrage...");
    oled.display();
  } else {
    Serial.println("[OLED] introuvable (0x3C) : on continue sans ecran");
  }
  dht.begin();

  // Wi-Fi d'abord : le générateur aléatoire matériel est alors alimenté par la radio
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  snprintf(bootId, sizeof(bootId), "%08lx", (unsigned long)esp_random());
  Serial.printf("boot_id = %s\n", bootId);

  if (!brokerIp.fromString(MQTT_BROKER_IP)) Serial.println("[MQTT] MQTT_BROKER_IP invalide dans secrets.h");
  net.setHandshakeTimeout(TLS_HANDSHAKE_TIMEOUT_S);
  mqtt.begin(brokerIp, MQTT_PORT, net);
  mqtt.setOptions(MQTT_KEEPALIVE_S, true, 2000);  // session propre : pas de vieilles commandes rejouées
  mqtt.setWill(T_STATUS, "{\"state\":\"offline\"}", true, 1);
  mqtt.onMessage(onMqttMessage);

  tTele = millis();
}

void loop() {
  uint32_t now = millis();

  if (now - tPir >= PIR_PERIOD_MS) { tPir = now; samplePir(); }
  if (now - tDht >= DHT_PERIOD_MS) { tDht = now; readDht(); }
  if (now - tTele >= TELEMETRY_PERIOD_MS) {
    tTele += TELEMETRY_PERIOD_MS;
    if (now - tTele >= TELEMETRY_PERIOD_MS) tTele = now;  // retard (ex. handshake TLS) : on se recale
    pushSample(acquire());
  }

  ensureWifi();
  ensureMqtt();
  mqtt.loop();          // lit les messages entrants (reçus, commandes) et entretient la connexion
  processCommands();
  flushAcks();
  serviceBuffer();

  updateOutputs();
  if (now - tOled >= 500) { tOled = now; drawOled(); }

  if (now - tLog >= 5000) {
    tLog = now;
    Serial.printf("[ETAT] seq=%lu T=%.1f H=%.1f gaz=%d pres=%d | wifi=%d mqtt=%d | tampon=%d perdu=%lu recus=%lu heap=%lu\n",
                  (unsigned long)sequence, dhtT, dhtH, lastGasRaw, presenceNow(), wifiUp(), mqtt.connected(),
                  bufferedCount(), (unsigned long)lostCount, (unsigned long)receiptsOk, (unsigned long)ESP.getFreeHeap());
  }
}
