# Validation de la simplification du 7 octobre 2026

Les anciennes mesures de performance et la recette fictive ne décrivent plus la version actuelle. Voir README pour les commandes de contrôle et docs/RECETTE.md pour les vérifications matérielles.

Le modèle est calibré manuellement sur une référence physique de 30 secondes. Aucun résultat de détection industrielle ni de webcam en conteneur n'est annoncé sans essai réel sur la machine cible.

Contrôles exécutés : 25 tests Python réussis dans l'environnement unique `.venv` ; compilation TypeScript/Vite réussie. Avertissements conservés : dépréciation AnyIO/Starlette et taille du bundle frontend. Docker est absent de cet environnement : construction des images, démarrage Compose et accès webcam en conteneur non vérifiés ici.
