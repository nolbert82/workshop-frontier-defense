# Validation de la simplification du 7 octobre 2026

Les anciennes mesures de performance et la recette fictive ne décrivent plus la version actuelle. Voir README pour les commandes de contrôle et docs/RECETTE.md pour les vérifications matérielles.

Le modèle est calibré manuellement sur une référence physique de 30 secondes. Aucun résultat de détection industrielle ni de webcam en conteneur n'est annoncé sans essai réel sur la machine cible.

Contrôles exécutés : 25 tests Python réussis dans l'environnement unique `.venv` ; compilation TypeScript/Vite réussie. Avertissements conservés : dépréciation AnyIO/Starlette et taille du bundle frontend. Docker est absent de cet environnement : construction des images, démarrage Compose et accès webcam en conteneur non vérifiés ici.

Ajout de la capture USB automatique Windows et de la préparation des poids YOLO : 37 tests Python réussis, téléchargement réel de l'asset Ultralytics v8.4.0 et SHA-256 vérifiés, syntaxe PowerShell vérifiée. Les tests couvrent l'authentification de l'ingestion d'images, les tailles et formats refusés, la fraîcheur, la sélection de la caméra et les erreurs de téléchargement. L'essai physique de la webcam avec Docker Desktop reste à effectuer sur la machine cible.
