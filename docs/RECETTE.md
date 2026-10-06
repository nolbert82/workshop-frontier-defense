# Recette finale et limites de validation

## Vérifications logicielles

- Tests automatisés dans `tests/test_system.py` : exécuter `python -m pytest -q`.
- Recette intégrée dans `scripts/smoke.py`, contre une API et un service vision réellement lancés : résultat sauvegardé seulement en cas de réussite complète.
- Compilation TypeScript et Vite : `pnpm build`.
- Modèle YOLO existant : inférence sur image synthétique possible sans caméra ; cette vérification ne mesure pas la performance USB stabilisée.
- Isolation Forest : `backend/ml/model.json` décrit les séquences séparées, le seuil et le nombre d'observations dépassant ce seuil. Les chiffres proviennent de données synthétiques ; ils ne prouvent pas une détection d'incident physique.

## Essais à réaliser et consigner sur le portable final

| Essai | Résultat attendu | Preuve à joindre |
|---|---|---|
| Internet désactivé après préparation | Dashboard, modèle, capteurs et caméra restent locaux | Capture + procédure de coupure |
| PostgreSQL et broker dans Compose | Services sains, 4 conteneurs, aucune exposition de la base | `compose ps`, capture réseau autorisée |
| Télémétrie réelle 1 Hz | Fraîcheur et acquisition visibles en moins de 2 s | Horodatages réception / affichage |
| Commande matérielle et doublon | Un seul effet physique ; accusé exact | Vidéo et journal command_id |
| Wi-Fi coupé 20 s | Hors ligne en 5 s, reprise sans doublon | Séquences avant / après + lignes base |
| Coupure > 60 s | Pertes comptées, aucune alerte ancienne actuelle | lost_count, replayed, SQL |
| Redémarrage ESP | Nouveau boot_id, anciennes commandes refusées | Journaux et test d'accusés |
| Capteur débranché | Valeur null, erreur E002, autres mesures présentes | Dashboard + payload réel |
| Personne dans le champ | Trois confirmations, résolution après départ | Flux annoté + épisode unique |
| Latence vision | Médiane et p95 < 100 ms si matériel suffisant | CPU, caméra, taille d'entrée, nombre de trames et mesures |
| Arrêt vision / MQTT / base / API | État dégradé et reprise ; aucun faux succès | Journaux séparés pour chaque panne |
| Redémarrage du PC | Hotspot, Docker, vision relancés, historique conservé | Chronologie réelle de démarrage |
| Client MQTT sans mot de passe / hors ACL | Connexion ou accès refusé | Log du broker |
| Mauvaise clé broker | ESP refuse TLS | Log firmware |
| Client web sans session / CSRF | Commandes, WS et vidéo refusés | Réponses HTTP / close WS |
| Ports depuis autre poste autorisé | 443 et 8883 uniquement ; 8090 refusé | Scan du réseau de l'équipe uniquement |
| Archive de rendu | Aucun secret, aucune donnée privée | Inspection du contenu ZIP |

Ne pas noter « validé » sans preuve réelle. Le pare-feu Windows, le hotspot, les tâches de démarrage et la politique de veille doivent être configurés par l'équipe sur le PC retenu. Docker Desktop nécessite souvent l'ouverture de session ; le consigner au lieu de promettre un démarrage autonome sans essai.

## Sécurité et audit croisé

Décrire TLS sur Wi-Fi et la terminaison Nginx/Mosquitto, les liaisons internes HTTP, les ACL, les privilèges et les secrets. Le certificat local est émis par une CA propre à l'équipe. L'export du code n'inclut aucune clé privée. Toute capture ou audit reste dans le périmètre autorisé par les encadrants. Le rapport d'audit doit préciser cible, créneau, constat, gravité, correction et retest ; aucun résultat offensif n'est fabriqué.

## Livrables pédagogiques à finaliser

Le code et la procédure de démarrage sont fournis. Le dossier final doit intégrer les preuves physiques, le schéma de câblage effectivement validé, les photos du boîtier et le rapport d'audit réel. La présentation et le poster doivent reprendre ces preuves. La vidéo verticale H.264 de moins de 60 s doit montrer le montage et être tournée au fond vert selon les consignes. `docs/SOUTENANCE.md` prépare le déroulé, sans remplacer le tournage ou les essais.
