# Validation logicielle du 6 octobre 2026

Les résultats ci-dessous décrivent uniquement ce qui a été exécuté pendant l'implémentation, sous Windows.

| Contrôle | Résultat |
|---|---|
| Tests automatisés Python | 15 tests réussis ; un avertissement de dépréciation AnyIO/Starlette |
| Compilation React/TypeScript/Vite | Réussie ; bundle principal environ 563 Ko (169 Ko gzip) |
| API et tâches réellement lancées | FastAPI sur loopback, SQLite persistante, simulateur 1 Hz |
| Recette intégrée | Réussie : commandes, WebSocket, MJPEG, capteur invalide, coupure, intrusion, timeout, dérive et résolution |
| Navigateur bureau | Connexion, courbes, commande et historique vérifiés ; webcam réelle affichée en 640 × 480 avec badge « Direct » |
| Affichage mobile | 375 px de largeur utile, aucun débordement horizontal de la page principale |
| Poids YOLO26 existants | Chargés et utilisés sur une image noire synthétique ; zéro personne détectée |
| Webcam USB réelle | UGREEN Camera sélectionnée par nom ; capture 640 × 480 et MJPEG authentifié vérifiés, heartbeat réel accepté |
| YOLO sur webcam | Traitement stabilisé : environ 26 ms en médiane, 40 ms au p95 lors de l'essai ; latence d'affichage complète non mesurée |
| Compose | Syntaxe YAML et structure de quatre services vérifiées ; base et API sans publication de port |
| Scripts PowerShell | Syntaxe contrôlée avec le parseur PowerShell |
| Git | Aucune commande Git exécutée |

La recette détaillée en simulation est dans `validation-integration.json`. La webcam USB a ensuite été testée séparément avec YOLO, le flux MJPEG et le dashboard ; aucune image de cet essai n'a été enregistrée. Les tests ne prouvent pas le fonctionnement du boîtier, des capteurs et actionneurs physiques, de Docker Desktop, du hotspot ou du pare-feu sur le PC de démonstration. Docker n'est pas installé dans l'environnement d'exécution utilisé. Les mesures sur webcam ne remplacent pas une recette de performance prolongée.

Le modèle synthétique utilise 100 arbres et une graine 42. Sur le jeu normal réservé : 5 observations au-dessus du seuil sur 586. Sur le jeu de dérive réservé : 454 sur 586, y compris sa phase normale initiale. Ces nombres sont des comptages d'observations ; ils ne constituent pas des taux d'incidents détectés. Trois observations consécutives sont nécessaires pour ouvrir l'alerte ; dix observations normales pour la résoudre. Les données physiques nécessitent une calibration et une évaluation distinctes.

Les scénarios de recette restent dans l'historique. En particulier, E008 indique une commande d'essai sans confirmation : son exécution est restée inconnue. L'acquittement ne transforme pas cette commande en réussite.
