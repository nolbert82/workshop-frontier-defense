# SENTINEL-X — Frontier Defense

Prototype de surveillance autonome pour micro-centrale isolée (Workshop EPSI Bac+4 « Mission Sentinel-X », sujet complet dans [`sujet.pdf`](sujet.pdf)). Un boîtier ESP32 mesure température, humidité, gaz et présence, et envoie ses mesures en **MQTT chiffré (TLS)** à un PC serveur Windows. Ce PC fait tourner cinq services Docker (`web`, `backend`, `postgres`, `mosquitto`, `vision`), analyse la webcam USB avec YOLO26-n et détecte les anomalies des capteurs avec un Isolation Forest. Un dashboard web sécurisé affiche tout en temps réel et permet de piloter les LEDs du boîtier.

Aucun générateur de données ni scénario fictif : toutes les données viennent des capteurs et de la webcam physiques.

## Contenu du dépôt

| Dossier / fichier | Rôle |
|---|---|
| `start.ps1` | Lanceur Windows : prépare Python, construit et démarre les conteneurs, lance la capture webcam |
| `compose.yaml` (+ `compose.windows.yaml`, `compose.usb.yaml`) | Définition des cinq services Docker (complément Windows ou Linux pour la webcam) |
| `backend/` | API FastAPI, client MQTT, stockage PostgreSQL, modèle d'anomalie (`backend/ml`) |
| `frontend/` | Dashboard React / TypeScript, servi par Nginx (`nginx/`) |
| `vision/` | Détection de personnes YOLO26-n (conteneur) et capture USB Windows (`camera_bridge.py`) |
| `mosquitto/` | Configuration du broker MQTT : TLS, comptes, droits par topic (ACL) |
| `firmware/sentinel_x/` | Firmware C++ du boîtier ESP32 ([README dédié](firmware/sentinel_x/README.md)) |
| `firmware/tests/` | Sketches de test du câblage, un par composant |
| `scripts/` | Génération des secrets et certificats, secrets du firmware, export du code |
| `docs/` | Contrat MQTT boîtier / backend ([INTEGRATION.md](docs/INTEGRATION.md)), recette, soutenance |
| `tests/` | Tests automatisés Python (`pytest`) |
| `SPECIFICATIONS.md` | Spécification fonctionnelle et technique |

## Lancer le projet

Tout tourne sur **un seul PC portable Windows** (option B du sujet) : point d'accès Wi-Fi de la table, conteneurs Docker, webcam, et flashage de l'ESP32. Une fois flashé, le boîtier se connecte seul à ce PC par le Wi-Fi.

Les étapes 1 à 4 se font **une seule fois**. Ensuite, à chaque démo : étapes 5 et 6.

### Prérequis (à installer avec Internet)

| Logiciel | Pourquoi |
|---|---|
| [Git](https://git-scm.com/download/win) | Récupérer le dépôt |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | Installe Python 3.12.11 et les dépendances dans `.venv` |
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Conteneurs (mode Linux / WSL2). Il doit être **ouvert** avant chaque lancement |
| [Arduino IDE 2](https://www.arduino.cc/en/software) | Flasher l'ESP32 (étape 7) |

Matériel : webcam USB branchée sur ce PC, câble USB **de données** pour l'ESP32 (beaucoup de câbles ne font que la charge).

Le premier lancement télécharge les images Docker, PyTorch et les poids YOLO : il faut Internet. Ensuite, tout fonctionne hors ligne.

### 1. Allumer le point d'accès Wi-Fi (2,4 GHz)

1. *Paramètres › Réseau et Internet › Point d'accès mobile › Modifier* : choisir la bande **2,4 GHz** (l'ESP32 ne voit pas le 5 GHz), noter le nom et le mot de passe du Wi-Fi.
2. Activer le point d'accès, puis relever l'IP du PC sur ce réseau :
   ```powershell
   ipconfig
   ```
   Chercher la carte « Connexion au réseau local\* » : son **Adresse IPv4** (presque toujours `192.168.137.1`) est l'IP du serveur, utilisée aux étapes 3 et 7.

Si Windows refuse d'activer le point d'accès faute de connexion à partager, garder le PC connecté en même temps à une autre source (Ethernet ou partage de connexion d'un téléphone).

Désactiver aussi la mise en veille pendant la démo (*Paramètres › Système › Alimentation*).

### 2. Récupérer le code

```powershell
git clone https://github.com/nolbert82/workshop-frontier-defense.git
cd workshop-frontier-defense
```

Toutes les commandes suivantes se tapent dans PowerShell, depuis ce dossier.

### 3. Préparer Python et générer les secrets

```powershell
uv venv --python 3.12.11 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
.venv\Scripts\python.exe scripts\setup.py --ip 192.168.137.1
```

Remplacer `192.168.137.1` par l'IP relevée à l'étape 1. **Cette étape doit être faite avant le premier `start.ps1`** : sinon le lanceur génère les secrets avec l'IP par défaut `192.168.50.1`, et le dashboard ouvert depuis un autre appareil ainsi que le boîtier ne trouveront pas le serveur.

`setup.py` crée le dossier `secrets\` : mots de passe aléatoires, autorité de certification locale, certificats TLS, compte du dashboard. Ce dossier est exclu de Git et ne doit jamais être envoyé par messagerie. Le script ne remplace jamais une configuration existante.

> **IP erronée ou changée ?** Arrêter le système, supprimer le dossier `secrets\`, relancer la commande `setup.py` avec la bonne IP, puis **regénérer `secrets.h` et reflasher l'ESP32** (étape 7) : les mots de passe et certificats ont changé.

### 4. Ouvrir le pare-feu, uniquement pour le Wi-Fi de la table

Dans un PowerShell **administrateur** : seuls le dashboard (443) et le broker MQTT chiffré (8883) sont accessibles, et seulement depuis le sous-réseau du point d'accès.

```powershell
New-NetFirewallRule -DisplayName "Sentinel HTTPS+MQTTS" -Direction Inbound `
  -Protocol TCP -LocalPort 443,8883 -RemoteAddress 192.168.137.0/24 -Action Allow
```

Adapter `192.168.137.0/24` si l'IP de l'étape 1 est différente.

### 5. Démarrer le système

Avant : point d'accès allumé, Docker Desktop ouvert, webcam branchée.

```powershell
.\start.ps1
```

Le lanceur installe ce qui manque, construit les images (plusieurs minutes la première fois), démarre les cinq conteneurs puis la capture webcam. **Garder ce terminal ouvert** : il fait tourner la webcam. **Ctrl+C** arrête la capture et les conteneurs sans effacer les données. Un second lancement simultané est refusé.

La webcam est choisie par son nom dans `vision\camera.json` (actuellement « UGREEN Camera »), sinon l'unique webcam externe détectée. Avec plusieurs webcams : `.\start.ps1 -Camera 1`.

### 6. Ouvrir le dashboard

- Sur le PC serveur : <https://localhost>. Depuis un autre appareil connecté au Wi-Fi de la table : `https://192.168.137.1`.
- Identifiants : fichier `secrets\operator.txt`.
- Avertissement de certificat : il vient de notre autorité locale. Pour le faire disparaître, installer `secrets\ca.crt` comme autorité de confiance sur le poste de consultation (sur le PC serveur : `certutil -user -addstore Root secrets\ca.crt`).

Tant que l'ESP32 n'est pas flashé et connecté, le boîtier `sentinel-x-01` apparaît hors ligne : c'est normal.

### 7. Flasher le boîtier ESP32 (une fois, puis si le firmware ou les secrets changent)

1. **Arduino IDE** : paquet de cartes *esp32 by Espressif Systems* 3.x, carte **DOIT ESP32 DEVKIT V1**. Bibliothèques : *MQTT* (Joel Gaehwiler, pas PubSubClient), *ArduinoJson* (Benoit Blanchon), *Adafruit SSD1306*, *Adafruit GFX*, *Adafruit BusIO*, *DHT sensor library*, *Adafruit Unified Sensor*.
2. **Générer `secrets.h`** (Wi-Fi, mot de passe MQTT, certificat de la CA locale) :
   ```powershell
   .venv\Scripts\python.exe scripts\firmware_secrets.py --ssid "NOM_DU_WIFI"
   ```
   Le mot de passe Wi-Fi est demandé sans affichage. Le fichier `firmware\sentinel_x\secrets.h` est exclu de Git. Ajouter `--force` pour remplacer un `secrets.h` existant.
3. Ouvrir `firmware\sentinel_x\sentinel_x.ino`, choisir le port COM, téléverser. Moniteur série à **115200 bauds** : `[MQTT] connecte` puis le compteur `recus` qui augmente d'environ 1 par seconde.
4. **LED bleue fixe** = chaîne complète OK (Wi-Fi + MQTTS + mesures stockées par le backend).

Au démarrage, le PIR est en chauffe 30 s et le MQ-2 2 min : leurs valeurs sont `null` et le dashboard signale « capteur invalide » jusqu'à la fin de la chauffe. Détails, signification des LEDs et diagnostic : [firmware/sentinel_x/README.md](firmware/sentinel_x/README.md).

**Si le port COM n'apparaît pas** : vérifier le câble (données, pas charge seule), puis installer le pilote USB de la carte selon la puce près du port : CP210x (Silicon Labs) ou CH340 (WCH). **« Accès refusé » sur le port COM** : un autre programme l'utilise (moniteur série ouvert, deuxième IDE…) ; le fermer ou débrancher/rebrancher la carte. **Bloqué sur `Connecting...`** : maintenir le bouton BOOT pendant le début du téléversement.

### 8. Calibrer le modèle d'anomalie

Au premier démarrage, aucun modèle d'anomalie n'existe. Une fois le boîtier connecté et les capteurs sortis de chauffe, laisser tourner **30 secondes en conditions normales**, puis cliquer sur **Réentraîner sur les 30 dernières secondes** dans le dashboard. Le modèle est conservé dans un volume Docker : inutile de recommencer à chaque démarrage.

### Commandes utiles

```powershell
docker compose --env-file secrets/compose.env -f compose.yaml -f compose.windows.yaml ps
docker compose --env-file secrets/compose.env -f compose.yaml -f compose.windows.yaml logs --tail 100 backend
docker compose --env-file secrets/compose.env -f compose.yaml -f compose.windows.yaml stop
```

Utiliser `start.ps1` pour démarrer : une commande `up` manuelle doit inclure les deux options `-f`. Les données PostgreSQL et le modèle d'anomalie persistent dans des volumes séparés ; `down -v` les **efface**.

## Architecture

Seuls les ports 443 (HTTPS : dashboard, API, WebSocket, vidéo) et 8883 (MQTTS) sont publiés sur le réseau. PostgreSQL, FastAPI et le service vision ne sont joignables que sur le réseau interne Docker. Le contrat MQTT (topics, payloads JSON, reçus, commandes) est décrit dans [docs/INTEGRATION.md](docs/INTEGRATION.md) ; TLS, QoS 1, déduplication, reçus de stockage et confirmation des commandes sont implémentés. Un timeout de commande signifie une exécution inconnue. Le service vision ne peut pas envoyer de commande opérateur.

### Vision

Le service vision contient OpenCV et YOLO26-n, utilise le CPU et expose son flux MJPEG uniquement sur le réseau Docker. Il envoie ses événements au backend avec un secret distinct, et le backend relaie la vidéo au dashboard après vérification de la session. Les poids YOLO26-n sont téléchargés depuis la version officielle Ultralytics v8.4.0 lors de la construction de l'image, avec vérification SHA-256 (`vision/weights.py`) : aucun fichier `.pt` n'est versionné ni à copier.

Docker Desktop ne permet pas de passer une webcam USB à un conteneur ([FAQ Docker](https://docs.docker.com/desktop/troubleshoot-and-support/faqs/general/)). Sous Windows, `start.ps1` lance donc `vision.camera_bridge` dans `.venv` : il lit seulement les images USB (Media Foundation, puis DirectShow en secours) et les envoie au conteneur sur un endpoint authentifié en `127.0.0.1:8090`, inaccessible depuis le Wi-Fi. Seule la dernière image est conservée, sans enregistrement ; la détection YOLO et les annotations se font dans le conteneur. En cas de débranchement, la capture réessaie automatiquement. Si les deux pilotes échouent, fermer les autres applications qui utilisent la caméra et vérifier l'autorisation des applications de bureau dans les paramètres de confidentialité Windows.

Sous Linux (Docker Engine), la webcam est transmise directement au conteneur, sans mode privilégié :

```sh
VISION_DEVICE=/dev/video0 VISION_GID=$(stat -c '%g' /dev/video0) docker compose --env-file secrets/compose.env -f compose.yaml -f compose.usb.yaml up --build -d --wait
```

### Modèle d'anomalie

L'API `POST /api/v1/model/retrain` exige une session opérateur et le jeton CSRF. Elle refuse les données manquantes, anciennes, rejouées, les capteurs invalides, les redémarrages du boîtier et les interruptions. Une seule calibration peut tourner à la fois ; l'ancien modèle reste actif si l'entraînement échoue, et le nouveau est remplacé atomiquement dans le volume `models-data`.

Variables : température, humidité et gaz ; chaque mesure forme une observation. Isolation Forest à 100 arbres, graine 42 ; le seuil est le quantile 99,5 % des scores d'entraînement. Le score est calculé toutes les deux mesures ; trois dépassements consécutifs ouvrent une alerte et dix observations normales la résolvent. Le PIR est exclu. Les données invalides n'effacent pas un incident actif.

Trente secondes fournissent une référence courte, sans jeu de validation indépendant ni garantie de détection industrielle. Le score n'est pas une probabilité.

## Tests, sécurité et export

```powershell
.venv\Scripts\python.exe -m pytest -q
cd frontend
pnpm install
pnpm build
```

Node.js et pnpm ne servent qu'à modifier le frontend ; les conteneurs installent leurs propres dépendances. Les tests automatisés vérifient les contrats logiciels ; les essais matériels se font sur la machine cible (voir [docs/RECETTE.md](docs/RECETTE.md)).

Aucun secret n'est versionné : `secrets/`, `.env` et `firmware/sentinel_x/secrets.h` sont exclus par `.gitignore`. Seuls des modèles sans valeur (`secrets.example.json`, `secrets.example.h`) sont fournis. `ca.key` et `server.key` ne quittent jamais le PC serveur.

Archive du code sans secrets, bases, journaux ni environnements Python, et sauvegarde de la base :

```powershell
.venv\Scripts\python.exe scripts\export.py --code-only
docker compose --env-file secrets/compose.env exec -T postgres pg_dump -U sentinel -d sentinel -f /tmp/sentinel.sql
docker compose --env-file secrets/compose.env cp postgres:/tmp/sentinel.sql output/sentinel.sql
```

Les journaux Docker sont limités à trois fichiers de 10 Mo.
