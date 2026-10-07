# Firmware SENTINEL-X — boîtier Edge (ESP32 DevKit V1)

Firmware C++ (Arduino) du boîtier : lit le DHT22, le MQ-2 et le PIR, publie la télémétrie en **MQTT sur TLS (8883)** vers Mosquitto, exécute les commandes du dashboard et affiche l'état sur l'OLED. Il respecte le contrat de [`docs/INTEGRATION.md`](../../docs/INTEGRATION.md) et de `SPECIFICATIONS.md` §4-5. Seule différence avec ces documents : la carte réelle est un **ESP32**, pas un ESP8266.

## Fichiers

| Fichier | Rôle | Versionné |
|---|---|---|
| `sentinel_x.ino` | Programme principal | oui |
| `config.h` | Broches, rythmes, réglages non secrets | oui |
| `secrets.example.h` | Modèle des secrets | oui |
| `secrets.h` | Wi-Fi, mot de passe MQTT, CA du broker | **non** (`.gitignore`) |

## 1. Prérequis (Arduino IDE)

- Carte : **DOIT ESP32 DEVKIT V1**, paquet « esp32 by Espressif Systems » **version 3.x** (Outils → Type de carte → Gestionnaire de cartes).
- Bibliothèques (Croquis → Inclure une bibliothèque → Gérer les bibliothèques) :
  - **MQTT** par *Joel Gaehwiler* (version 2.5 ou plus) : attention, pas « PubSubClient », qui ne publie pas en QoS 1 ;
  - **ArduinoJson** par *Benoit Blanchon* (version 7.x) ;
  - déjà installées pour les tests : Adafruit SSD1306, Adafruit GFX, Adafruit BusIO, DHT sensor library, Adafruit Unified Sensor.

Versions validées par compilation : esp32 3.3.2, MQTT 2.5.3, ArduinoJson 7.4.2.

## 2. Générer `secrets.h`

Les secrets sont créés par `scripts/setup.py` sur le **PC serveur** (dossier `secrets/`, jamais versionné). Depuis la racine du dépôt, sur ce PC :

```powershell
python scripts/firmware_secrets.py --ssid "NOM_DU_WIFI_DE_LA_TABLE"
# si l'IP réelle du hotspot (ipconfig) diffère de celle passée à setup.py :
python scripts/firmware_secrets.py --ssid "NOM_DU_WIFI" --broker-ip 192.168.137.1
```

Le mot de passe Wi-Fi est demandé sans écho. Si le flashage se fait depuis un autre ordinateur, copiez **uniquement** `secrets/device.json` et `secrets/ca.crt` par clé USB, puis lancez la commande avec `--secrets-dir CHEMIN`. N'utilisez jamais une messagerie pour ça. `ca.key` et `server.key` ne quittent jamais le serveur.

## 3. Téléverser et vérifier

1. Ouvrir `firmware/sentinel_x/sentinel_x.ino`, choisir le port, téléverser.
2. Moniteur série à **115200 bauds**. Séquence attendue :
   ```
   === SENTINEL-X firmware 1.0.0 ===
   boot_id = 9f3a01bc
   [MQTT] connexion TLS a 192.168.137.1:8883 (verifie 'mosquitto')...
   [MQTT] connecte
   [ETAT] seq=12 T=23.4 H=45.1 gaz=812 pres=0 | wifi=1 mqtt=1 | tampon=0 perdu=0 recus=11 heap=...
   ```
   `recus` doit augmenter d'environ 1 par seconde : c'est la preuve que le backend a **stocké** les mesures en base, pas seulement que le broker les a reçues.
3. **LED bleue fixe** : chaîne complète OK. Dashboard : l'appareil `sentinel-x-01` apparaît en ligne.

Comportements normaux au démarrage : le PIR reste `warming_up` pendant 30 s et le MQ-2 pendant 2 min. Leurs valeurs sont alors `null` et le dashboard signale « capteur invalide » (E002) jusqu'à la fin de la chauffe.

## Signification des LEDs

| LED | Commande / état | Comportement |
|---|---|---|
| Bleue (système) | Automatique, non pilotable à distance | Fixe = Wi-Fi + MQTTS + reçus du backend ; clignote lentement = Wi-Fi OK mais broker ou backend absent ; clignote vite = pas de Wi-Fi |
| Rouge (alarme) | Commande `buzzer` du dashboard | Clignote rapidement pendant la durée demandée. Hors alarme, s'allume fixe pendant un mouvement PIR (réflexe local, fonctionne sans réseau ; désactivable : `LOCAL_PIR_REFLEX 0`) |
| Jaune (test) | Commande `led` du dashboard | Allumée pendant la durée demandée |

Pas de buzzer sur la maquette : la commande `buzzer` du contrat pilote l'alarme visuelle rouge. Si un buzzer **actif** est ajouté sur le GPIO 33, passer `HAS_BUZZER` à 1 dans `config.h`.

## Diagnostic

| Symptôme dans le moniteur série | Cause probable |
|---|---|
| Reste bloqué avant `[MQTT] connexion` | Mauvais SSID/mot de passe, ou Wi-Fi en 5 GHz uniquement |
| `tls='... Certificate verification failed'` | `secrets.h` ne contient pas le `ca.crt` du serveur actuel (setup.py relancé ?) : régénérer `secrets.h` |
| `tls=''` et `lwmqtt=-3` | Port 8883 fermé par le pare-feu Windows, mauvaise IP, ou conteneur `mosquitto` arrêté |
| `retour=5` (not authorized) | Mot de passe MQTT différent de `secrets/mqtt-passwords.txt` |
| `mqtt=1` mais `recus` reste à 0 | Backend arrêté, ou télémétrie refusée : regarder `docker compose ... logs backend` |
| `perdu` augmente | Coupure plus longue que le tampon (60 s) : comportement prévu, visible (E009) |

## Choix techniques à défendre à l'oral

- **MQTTS avec vérification du serveur.** L'ESP vérifie que le certificat du broker est signé par notre CA locale **et** qu'il porte le nom `mosquitto`. `setInsecure()` n'est jamais utilisé. On se connecte par IP mais on vérifie le nom, ce qui résiste à un changement d'IP du hotspot. Un faux broker (pentest jeudi) est refusé. Côté horloge, l'ESP32 ne vérifie pas les dates de validité du certificat (mbedTLS est compilé sans `MBEDTLS_HAVE_TIME_DATE`) : un NTP n'est donc pas nécessaire sur un réseau sans Internet. C'est un compromis assumé et documenté.
- **Authentification et cloisonnement.** Identifiant MQTT propre au boîtier, avec des ACL Mosquitto : il ne peut publier que `telemetry`, `status` et `acks`, et ne peut lire que `commands` et `receipts`.
- **Zéro perte silencieuse.** Chaque mesure reste dans un tampon RAM de 60 cases jusqu'au **reçu applicatif** du backend (`receipts`), envoyé après validation en base. Sans reçu en 5 s, la mesure est renvoyée avec `replayed:true` (historique sans fausse alerte), à 4 mesures/s maximum, les plus récentes d'abord. En cas de débordement, la plus ancienne est abandonnée et `lost_count` est incrémenté (alerte E009). Le backend déduplique par `(device_id, boot_id, sequence)`.
- **Commandes sûres.** Chaque commande est vérifiée avant toute action : `boot_id` (un ordre destiné à un ancien démarrage est rejeté) et échéance `expires_at_uptime_ms` (un ordre trop vieux est rejeté). Les 20 derniers résultats sont mémorisés, ce qui permet de renvoyer le même accusé à un doublon QoS 1 sans rejouer l'action. La session MQTT est « propre » : aucune commande n'est rejouée après une reconnexion.
- **Pas de seuil statique.** Le firmware ne décide d'aucune alerte environnementale. Il envoie les valeurs brutes (gaz en ADC 0-4095) et c'est l'Isolation Forest du backend qui juge. Les seuls tests côté ESP portent sur la **santé des capteurs** (lecture DHT ratée, ADC à 0 = MQ-2 débranché) et l'anti-rebond du PIR (2 s).
- **Non bloquant.** Chaque capteur a son rythme (PIR 50 ms, DHT22 2 s, télémétrie 1 s) basé sur `millis()`. Seule la connexion TLS peut bloquer quelques secondes, avec une reconnexion progressive plafonnée à 10 s.
- **Last Will.** Le broker publie lui-même `{"state":"offline"}` (retenu) si le boîtier disparaît sans prévenir (keepalive 10 s).
