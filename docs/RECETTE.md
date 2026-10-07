# Vérification sur la machine finale

Utiliser uniquement les capteurs et la webcam physiques. Vérifier le démarrage des cinq services Compose, le flux de télémétrie à 1 Hz, les graphiques, les accusés des commandes et la reprise après interruption. Confirmer TLS et les ports publiés 443/8883 depuis un poste autorisé.

Après 30 secondes de fonctionnement normal, cliquer sur le bouton de réentraînement. Vérifier le succès, le refus en cas de collecte insuffisante ou capteur invalide, et le rechargement du modèle après redémarrage du backend. Aucune performance industrielle n'est déduite de cette calibration courte.

Vérifier la webcam dans le conteneur : passage USB sous Linux ou flux local de capture sous Docker Desktop, annotation des personnes, événements et résolution. Vérifier les latences sur le matériel final. Tester l'arrêt puis la reprise des services sans effacer les volumes.

Contrôles logiciels : `.venv/Scripts/python.exe -m pytest -q` et `pnpm build` dans `frontend`. Consigner les preuves matérielles, réseau et de redémarrage dans le rapport final. Les scénarios fictifs et leur ancienne recette ont été retirés.
