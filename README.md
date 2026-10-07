# SENTINEL-X

Surveillance locale avec capteurs physiques, FastAPI, React, PostgreSQL, MQTT TLS, YOLO26 et Isolation Forest. Aucun générateur de données ni scénario fictif. Cinq services Docker : `web`, `backend`, `postgres`, `mosquitto`, `vision`.

## Préparation

Python 3.12 et Docker avec Compose sont nécessaires. Node.js et pnpm sont utiles uniquement pour modifier le frontend. Un seul environnement Python local, `.venv`, sert aux outils et aux tests. Les conteneurs installent leurs propres dépendances.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe scripts/setup.py --ip 192.168.50.1
.\scripts\start-docker.ps1
```

Choisir l'adresse réelle du serveur avant la première préparation. Les secrets existants ne sont pas écrasés. Le dashboard est à https://localhost ou https://ADRESSE_DU_SERVEUR ; compte `operateur`, mot de passe dans `secrets/operator.txt`. Installer `secrets/ca.crt` comme autorité de confiance sur les postes de consultation. Ne pas partager les clés privées. Seuls 443 (HTTPS) et 8883 (MQTTS) sont publiés.

Les poids `vision/model/yolo26n.pt` doivent être présents avant le lancement. Les dépendances, images et poids se préparent avec Internet ; aucun modèle ne se télécharge au démarrage. Un seul worker backend est utilisé.

## Vision en conteneur

Le service vision contient OpenCV et YOLO, utilise le CPU et expose MJPEG uniquement sur le réseau Docker. Le backend reçoit ses événements sur `http://backend:8000` et relaie sa vidéo depuis `http://vision:8090`, avec un secret distinct. Les heartbeats continuent si la caméra est absente ; le dashboard indique son indisponibilité.

Sous Linux avec Docker Engine et une webcam USB, utiliser le fichier complémentaire :

```sh
VISION_DEVICE=/dev/video0 VISION_GID=$(stat -c '%g' /dev/video0) docker compose --env-file secrets/compose.env -f compose.yaml -f compose.usb.yaml up --build -d --wait
```

Le périphérique est transmis au conteneur sans mode privilégié. Adapter son chemin et le groupe de permissions. Le sujet exige une webcam USB branchée sur le PC serveur : conserver cette webcam comme source.

Sous Windows ou macOS, Docker Desktop ne transmet pas directement la webcam USB aux conteneurs. Fournir un flux HTTP/MJPEG ou RTSP depuis cette webcam via un outil de capture sur l'hôte, puis ajouter dans `secrets/compose.env`, par exemple :

```dotenv
VISION_SOURCE=http://host.docker.internal:8081/stream
```

Adapter l'URL au flux réel de l'outil choisi et limiter son accès au réseau Docker. Le traitement IA reste dans le conteneur ; seule l'acquisition webcam se fait sur l'hôte. USB/IP est une autre possibilité qui nécessite une configuration propre à Docker Desktop. [Documentation Docker](https://docs.docker.com/desktop/features/usbip/).

```powershell
docker compose --env-file secrets/compose.env ps
docker compose --env-file secrets/compose.env logs --tail 100 vision
docker compose --env-file secrets/compose.env stop
```

Sur Linux, conserver les deux options `-f` pour toutes les commandes. Les données PostgreSQL et le modèle persistent dans des volumes séparés. `down -v` les efface.

## Calibration du modèle d'anomalie

Au premier démarrage, aucun modèle d'anomalie n'est fourni. Brancher le boîtier `sentinel-x-01`, attendre 30 secondes de télémétrie physique valide à 1 Hz, puis cliquer sur **Réentraîner sur les 30 dernières secondes** dans le dashboard, en conditions normales.

L'API `POST /api/v1/model/retrain` exige une session opérateur et le jeton CSRF. Elle refuse les données manquantes, anciennes, rejouées, les capteurs invalides, les changements de démarrage et les interruptions. Une seule calibration peut être lancée à la fois. L'ancien modèle reste actif si l'entraînement ou la sauvegarde échoue. Le modèle est remplacé atomiquement et conservé dans le volume `models-data`.

Pour cette calibration courte, les variables sont température, humidité et gaz ; chaque mesure forme une observation. Isolation Forest utilise 100 arbres, graine 42 ; le seuil est le quantile 99,5 % des scores d'entraînement. Le score est calculé toutes les deux mesures ; trois dépassements consécutifs ouvrent une alerte et dix observations normales la résolvent. Le PIR est exclu. Les données invalides n'effacent pas un incident actif.

Trente secondes fournissent une référence courte, sans jeu de validation indépendant ni garantie de détection industrielle. Le score n'est pas une probabilité. Les anciens artefacts synthétiques sont ignorés ; les anciennes lignes fictives sont supprimées de la base à son initialisation, sans effacer les mesures physiques.

## Boîtier, sécurité et développement

Le contrat MQTT est décrit dans [docs/INTEGRATION.md](docs/INTEGRATION.md), le firmware dans `firmware/sentinel_x`. TLS, QoS 1, déduplication, reçus de stockage et confirmation des commandes sont conservés. Un timeout de commande signifie une exécution inconnue. Le service vision ne peut pas envoyer de commande opérateur.

```powershell
.venv\Scripts\python.exe -m pytest -q
cd frontend
pnpm build
```

Les tests automatisés vérifient les contrats logiciels ; aucune simulation n'est intégrée à l'application. Les essais matériels et Docker restent à effectuer sur la machine cible.

```powershell
.venv\Scripts\python.exe scripts/export.py --code-only
docker compose --env-file secrets/compose.env exec -T postgres pg_dump -U sentinel -d sentinel -f /tmp/sentinel.sql
docker compose --env-file secrets/compose.env cp postgres:/tmp/sentinel.sql output/sentinel.sql
```

L'archive de code exclut secrets, bases, journaux et environnements Python. Les journaux Docker sont limités à trois fichiers de 10 Mo.
