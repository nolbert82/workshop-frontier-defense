# SENTINEL-X

Surveillance locale avec capteurs physiques, FastAPI, React, PostgreSQL, MQTT TLS, YOLO26 et Isolation Forest. Aucun générateur de données ni scénario fictif. Cinq services Docker : `web`, `backend`, `postgres`, `mosquitto`, `vision`.

## Préparation

Sous Windows, installer uv et Docker Desktop, ouvrir Docker Desktop et brancher la webcam USB. Depuis le dossier du projet, une seule commande suffit :

```powershell
.\start.ps1
```

Le lanceur prépare Python 3.12.11 et l'unique `.venv` avec uv s'ils sont absents, installe les dépendances, prépare les secrets, construit les conteneurs et démarre la webcam. Il n'est pas nécessaire d'activer le venv. Garder ce terminal ouvert ; **Ctrl+C arrête la capture et les conteneurs**, sans effacer les données. Un second lancement simultané est refusé.

Le dashboard est à https://localhost ; compte `operateur`, mot de passe dans `secrets/operator.txt`. L'adresse serveur pour le boîtier est par défaut `192.168.50.1`. Si elle est différente, préparer les certificats avec `scripts/setup.py --ip ADRESSE_DU_SERVEUR` avant le premier lancement, après création du venv. Les secrets existants ne sont pas écrasés. Installer `secrets/ca.crt` comme autorité de confiance sur les postes de consultation. Seuls 443 (HTTPS) et 8883 (MQTTS) sont publiés sur le réseau.

Node.js et pnpm sont utiles uniquement pour modifier le frontend. L'unique `.venv` sert aux outils, aux tests et à la capture USB sous Windows. Les conteneurs installent leurs propres dépendances.

Les poids YOLO26-n sont téléchargés automatiquement depuis la version officielle Ultralytics v8.4.0 lors de la construction de l'image vision. Leur SHA-256 est vérifié et ils sont inclus dans l'image ; aucun fichier `.pt` n'est à copier après un clone. La première préparation nécessite Internet. Le démarrage des images déjà préparées fonctionne hors ligne. Un seul worker backend est utilisé.

## Vision en conteneur

Le service vision contient OpenCV et YOLO, utilise le CPU et expose MJPEG uniquement sur le réseau Docker. Le backend reçoit ses événements sur `http://backend:8000` et relaie sa vidéo depuis `http://vision:8090`, avec un secret distinct. Les heartbeats continuent si la caméra est absente ; le dashboard indique son indisponibilité.

Sous Linux avec Docker Engine et une webcam USB, utiliser le fichier complémentaire :

```sh
VISION_DEVICE=/dev/video0 VISION_GID=$(stat -c '%g' /dev/video0) docker compose --env-file secrets/compose.env -f compose.yaml -f compose.usb.yaml up --build -d --wait
```

Le périphérique est transmis au conteneur sans mode privilégié. Adapter son chemin et le groupe de permissions. Le sujet exige une webcam USB branchée sur le PC serveur : conserver cette webcam comme source.

Sous Windows, brancher la webcam USB et lancer `start.ps1`. Le lanceur active automatiquement `compose.windows.yaml`, démarre les conteneurs puis la capture USB depuis le même `.venv`. Aucune URL ni logiciel de capture supplémentaire n'est nécessaire.

La capture sélectionne la webcam configurée par nom si elle est présente, sinon l'unique caméra non intégrée détectée. Si plusieurs webcams sont présentes, préciser l'index avec `start.ps1 -Camera 1`. Elle utilise d'abord Media Foundation, sans transformations matérielles, puis DirectShow si nécessaire. Le format vidéo natif est conservé ; une ouverture bloquée est interrompue et retentée. En cas de débranchement, la capture réessaie automatiquement. Le terminal confirme « Webcam active » seulement après réception d'une image. Si les deux pilotes échouent, fermer les autres applications utilisant la caméra et vérifier l'autorisation des applications de bureau dans les paramètres de confidentialité Windows.

Windows lit seulement les images USB ; le conteneur effectue la détection YOLO et les annotations. Les images sont envoyées à un endpoint authentifié sur `127.0.0.1:8090`, inaccessible depuis le réseau Wi-Fi. Seule la dernière image est conservée, sans enregistrement. Le relais est nécessaire car [Docker Desktop ne propose pas de passage USB direct](https://docs.docker.com/desktop/troubleshoot-and-support/faqs/general/).

Sous macOS, la capture automatique n'est pas intégrée au lanceur PowerShell. Utiliser une source HTTP/MJPEG ou RTSP réelle avec `VISION_SOURCE` dans `secrets/compose.env`. Sous Windows, ce réglage n'est pas nécessaire et le lanceur privilégie la capture USB locale.

```powershell
docker compose --env-file secrets/compose.env ps
docker compose --env-file secrets/compose.env logs --tail 100 vision
docker compose --env-file secrets/compose.env stop
```

Sur Linux, conserver les deux options `-f` pour toutes les commandes. Sous Windows, utiliser le lanceur pour les démarrages ; une commande `up` manuelle doit également inclure `-f compose.yaml -f compose.windows.yaml`. Les données PostgreSQL et le modèle d'anomalie persistent dans des volumes séparés. `down -v` les efface.

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
