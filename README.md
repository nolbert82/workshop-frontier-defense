# SENTINEL-X

Prototype local de surveillance industrielle : **FastAPI, React/TypeScript, PostgreSQL, MQTT TLS, YOLO26 et Isolation Forest**. Les capteurs, le boîtier et les actionneurs sont remplacés par `simulator-01` tant que le montage n'est pas terminé. Aucun appel cloud, CDN ou téléchargement de modèle au démarrage.

## Démarrage rapide sous Windows

Prérequis : Python 3.12, Node.js 22 et pnpm 11.25.0. Une connexion Internet est nécessaire pour préparer les dépendances ; elle n'est plus nécessaire pendant la démonstration.

```powershell
python -m venv .venv-dev
.venv-dev\Scripts\python.exe -m pip install -r requirements-local.lock.txt
cd frontend
pnpm install --frozen-lockfile
pnpm build
cd ..
.venv-dev\Scripts\python.exe scripts/setup.py --ip 192.168.50.1
.venv-dev\Scripts\python.exe -m backend.ml.train
.\scripts\start-local.ps1
```

Le dashboard est à **http://127.0.0.1:8000**. Le compte `operateur` et son mot de passe aléatoire sont dans **`secrets/operator.txt`**. La configuration déjà générée n'est jamais écrasée. Ctrl+C arrête le serveur et son service vision.

Le mode rapide utilise **SQLite et HTTP sur loopback**, pour travailler sans Docker. Il conserve les données dans `data/sentinel.db`. Le mode de démonstration réseau ci-dessous utilise PostgreSQL, HTTPS et MQTTS. Ne pas exposer le mode rapide au réseau. Les cookies Secure sont désactivés uniquement par le lanceur local, pas par défaut.

La webcam USB réelle est activée par défaut ; les capteurs et actionneurs restent simulés. Pour une démonstration entièrement fictive, lancer `.\scripts\start-local.ps1 -SimulatedCamera` : la vidéo affiche alors « SIMULATION ». Le menu des scénarios pilote une dérive progressive, une présence fictive, une panne DHT22, une coupure de boîtier ou une commande sans confirmation. Le modèle nécessite 30 secondes de mesures valides après démarrage ou interruption. Les commandes passent par `pending`, puis `executed`, `rejected` ou `timeout`. Un timeout signifie que l'exécution est inconnue.

## Démonstration réseau avec Docker Desktop

1. Installer Docker Desktop avec les conteneurs Linux et préparer un réseau Wi-Fi local 2,4 GHz. Vérifier l'adresse IP effective avec `ipconfig` : le hotspot Windows n'utilise pas forcément `192.168.50.1`.
2. Exécuter `scripts/setup.py --ip ADRESSE_REELLE` **avant la première préparation**. L'IP doit figurer dans le certificat et les origines autorisées. Pour changer une installation existante, sauvegarder les secrets et les remplacer consciemment ; le script refuse de les écraser.
3. Installer `secrets/ca.crt` dans les autorités de confiance des postes de démonstration. Sur ce PC, pour l'utilisateur courant : `certutil -user -addstore Root secrets/ca.crt`. Cette opération modifie la confiance Windows : elle est laissée à l'équipe. Ne jamais distribuer `ca.key`, `server.key` ou le dossier `secrets`.
4. Exécuter le lanceur :

```powershell
.\scripts\start-docker.ps1
# Vidéo fictive, sans webcam :
.\scripts\start-docker.ps1 -SimulatedCamera
```

Lance quatre services (`web`, `backend`, `postgres`, `mosquitto`) et la vision sous Windows. Le dashboard est à **https://localhost** ou **https://ADRESSE_REELLE**. Le service vision écoute TCP 8090 pour être accessible depuis Docker Desktop via `host.docker.internal`. **Limiter ce port au réseau Docker dans le pare-feu Windows** ; il ne doit pas être autorisé pour les autres appareils Wi-Fi. Il exige en complément le secret du service vision. N'autoriser que 443 et 8883 depuis le sous-réseau de l'équipe. Aucun port PostgreSQL ou FastAPI n'est publié.

```powershell
docker compose --env-file secrets/compose.env ps
docker compose --env-file secrets/compose.env logs --tail 100
docker compose --env-file secrets/compose.env stop
```

Les volumes survivent à un arrêt ou redémarrage. Ne pas utiliser `down -v` pour arrêter la démo : cette option effacerait les données. Les journaux Docker tournent sur 3 × 10 Mo. Un seul worker FastAPI doit être conservé.

## Webcam USB et performances

Le fichier existant `vision/model/yolo26n.pt` est utilisé localement. Pour la webcam réelle, installer les dépendances supplémentaires :

```powershell
.venv-dev\Scripts\python.exe -m pip install -r requirements.txt
.\scripts\start-local.ps1
```

La sélection enregistrée dans `vision/camera.json` est **UGREEN Camera**. Le service retrouve son index par son nom à chaque ouverture ; si elle est débranchée, il signale son absence et réessaie sans basculer vers la caméra intégrée. Modifier ce fichier pour une autre webcam. Le lanceur choisit automatiquement l'environnement `.venv` équipé de YOLO, puis l'environnement du backend s'il contient les dépendances nécessaires. `-VisionPython CHEMIN` permet de préciser un autre interpréteur.

Une seule instance de vision doit accéder à la webcam. Fermer `camera_test.py` avant de lancer le service. Pour lancer la vision manuellement, `python -m vision.service --camera 1 --url http://127.0.0.1:8000` choisit explicitement un index ; `--imgsz 320` est la taille d'inférence initiale, capture et affichage en 640 × 480. Le service analyse la dernière image à 5 Hz, classe `person`, seuil 0,60. Il confirme après trois analyses positives et résout après trois secondes sans confirmation. Les transitions sont réessayées avec le même identifiant ; aucune image ni vidéo n'est enregistrée par défaut.

Les latences médiane et p95 sont exposées dans le dashboard. La simulation mesure seulement le rendu synthétique. Un essai réel avec la UGREEN sur ce PC a mesuré environ **26 ms en médiane et 40 ms au p95**, après chauffe ; ces valeurs couvrent le traitement, pas la latence complète d'affichage. Vérifier de nouveau les performances sur le PC final. Le premier chargement du modèle est plus lent. Le système détecte une personne, sans identification ni intention.

## Raccordement futur du boîtier

Les documents fournis parlent d'**ESP8266** ; l'équipe mentionne maintenant un **ESP32**. Aucun firmware ni câblage définitif n'est inventé. Le backend accepte les deux via le contrat MQTT décrit dans [docs/INTEGRATION.md](docs/INTEGRATION.md). Confirmer la carte, ses broches et la plage ADC avant la partie matérielle.

MQTT utilise TLS sur 8883, QoS 1, identifiants propres et ACL. Le compte du boîtier se trouve dans `secrets/device.json`. L'appareil utilise `sentinel-x-01` et `source: physical` ; la simulation utilise `simulator-01` et ne publie jamais de commande sur les topics matériels. La clé publique du broker pour l'ESP8266 est `secrets/broker-public.pem` ; sa vérification est obligatoire, `setInsecure()` interdit. Sur ESP32, utiliser une validation de certificat et une stratégie d'horloge adaptées et vérifiées.

Le mode simulation peut être désactivé avec `SENTINEL_SIMULATION=false` pour le backend. Le modèle livré est **entraîné sur données synthétiques** : collecter des séquences physiques normales distinctes, recalibrer le seuil et produire des tests réservés avant d'annoncer une performance réelle.

Le formateur accepte aussi quatre jeux JSONL séparés avec le manifeste `backend/ml/sequences.example.json`. Chaque fichier contient des télémétries dans l'ordre de capture ; les interruptions, reprises et valeurs invalides interrompent les fenêtres. Utiliser des acquisitions distinctes, viser au moins 20 minutes de fonctionnement normal pour l'entraînement, puis vérifier les épisodes détectés et les fausses alertes sur les jeux réservés. Un même fichier est refusé s'il appartient à plusieurs jeux.

```powershell
.venv-dev\Scripts\python.exe -m backend.ml.train --manifest data/sequences.json --output backend/ml/physical-model.joblib
# Après validation, sélectionner l'artefact figé au démarrage :
$env:SENTINEL_MODEL_PATH = "backend/ml/physical-model.joblib"
```

## Tests, recette et sauvegarde

```powershell
.venv-dev\Scripts\python.exe -m pip install pytest==8.3.5
.venv-dev\Scripts\python.exe -m pytest -q
# Avec le mode local et sa vision simulée déjà lancés :
.venv-dev\Scripts\python.exe scripts/smoke.py
```

`scripts/smoke.py` change temporairement les scénarios, puis revient au fonctionnement normal. La recette dure environ 90 secondes. Elle produit `docs/validation-integration.json` uniquement après réussite. Les tests couvrent les sessions, CSRF, WebSocket, permissions du service vision, identité MQTT, déduplication, données rejouées, persistance, capteurs invalides, anomalies temporelles et confirmation des commandes.

```powershell
# SQLite local : export des mesures, alertes et commandes + archive de code
.venv-dev\Scripts\python.exe scripts/export.py
# PostgreSQL dans Docker : sauvegarde logique UTF-8
docker compose --env-file secrets/compose.env exec -T postgres pg_dump -U sentinel -d sentinel -f /tmp/sentinel.sql
docker compose --env-file secrets/compose.env cp postgres:/tmp/sentinel.sql output/sentinel.sql
# Archive du code uniquement, sans environnement privé :
.venv-dev\Scripts\python.exe scripts/export.py --code-only
```

L'archive exclut les secrets, les bases, les logs, les environnements virtuels, les dépendances installées et les métadonnées Git. Aucune commande Git n'est nécessaire ni exécutée par les scripts.

## Organisation

- `backend/app/` : API, sécurité, transactions, MQTT et moteur de supervision.
- `backend/ml/` : extraction temporelle, entraînement hors ligne, modèle et métadonnées synthétiques.
- `frontend/` : dashboard français responsive, courbes, vidéo, journal et commandes.
- `simulator/` : signaux reproductibles et scénarios fictifs.
- `vision/service.py` : webcam USB / scène synthétique, YOLO, MJPEG, heartbeat et événements.
- `compose.yaml`, `nginx/`, `mosquitto/` : déploiement et chiffrement.
- `scripts/` : préparation, lancement, recette et export.
- `docs/` : contrat d'intégration, recette finale et supports de soutenance à finaliser.

Les essais physiques, la recette Docker, le hotspot, le pare-feu et le redémarrage complet restent à réaliser sur la machine de démonstration. Le boîtier, le montage électronique, le tournage au fond vert et l'audit croisé nécessitent le travail réel de l'équipe. Les documents de recette distinguent ces essais des vérifications logicielles réalisées.
