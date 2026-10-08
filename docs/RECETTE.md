# Vérification sur la machine finale

Utiliser uniquement les capteurs et la webcam physiques. Vérifier le démarrage des cinq services Compose, le flux de télémétrie à 1 Hz, les graphiques, les accusés des commandes et la reprise après interruption. Confirmer TLS et les ports publiés 443/8883 depuis un poste autorisé.

Après 30 secondes de fonctionnement normal, cliquer sur le bouton de réentraînement. Vérifier le succès, le refus en cas de collecte insuffisante ou capteur invalide, et le rechargement du modèle après redémarrage du backend. Aucune performance industrielle n'est déduite de cette calibration courte.

Sur une installation neuve, vérifier que la construction de l'image télécharge les poids YOLO officiels avec contrôle SHA-256, sans copie manuelle. Sous Windows, brancher la webcam et lancer `start.ps1` : capture USB automatique, aucune URL à configurer. Vérifier le flux annoté, le débranchement/rebranchement, les événements et leur résolution. Sous Linux, vérifier le passage USB au conteneur. Vérifier les latences sur le matériel final. Tester l'arrêt puis la reprise des services sans effacer les volumes.

## Mesures déjà relevées (installation de test, 7 octobre 2026)

- Webcam physique UGREEN Camera, 640 × 480 via Media Foundation : ouverture en 0,28 s, première image en 0,74 s.
- Inférence YOLO26-n dans le conteneur vision, sur CPU : **médiane 21 ms, p95 31 ms** par image, sous l'exigence de 100 ms du sujet. Résultat valable pour cette machine, à remesurer sur le PC serveur final.
- `start.ps1` : dépendances préparées avec uv, cinq services sains, `/health` à `camera=true` et `model=true`, flux `/api/v1/video` fonctionnel. Ctrl+C arrête la capture et les cinq conteneurs sans effacer les volumes.

Restent à valider : préparation complète sur un PC vierge et essais avec le boîtier physique.

## Contrôles logiciels

Lancer `.venv/Scripts/python.exe -m pytest -q` et `pnpm build` dans `frontend`. Consigner les preuves matérielles, réseau et de redémarrage dans le rapport final. Les scénarios fictifs et leur ancienne recette ont été retirés.
