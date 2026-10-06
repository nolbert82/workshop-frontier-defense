# Trame de soutenance SENTINEL-X

## Déroulé local

**Introduction — 1 min.** « SENTINEL-X surveille une zone industrielle depuis un PC local : les signaux environnementaux et une webcam alimentent un tableau de bord sécurisé. Nous avons retenu l'architecture B du sujet, avec quatre services Docker et la vision directement sous Windows. » Présenter les membres et leurs rôles réels.

**Vidéo — 1 min maximum.** Format vertical 9:16, MP4 H.264, tournage au fond vert. Proposition de storyboard : 0–8 s problème et boîtier ; 8–20 s capteurs et connexion locale ; 20–35 s présence annotée ; 35–48 s dérive et alerte ; 48–56 s commande confirmée ; 56–60 s signature équipe. Signaler les démonstrations fictives par « SIMULATION » tant que le montage n'est pas terminé.

**Démonstration — 3 min.** Ouvrir la vue d'ensemble et expliquer les unités ADC. Montrer le bandeau simulation si présent. Tester buzzer ou LED, commenter pending puis executed. Déclencher une dérive suffisamment tôt pour disposer de la fenêtre de 30 s ; afficher le score, le seuil et l'alerte persistante. Présenter la caméra, la confirmation puis la résolution. Acquitter une alerte sans confondre cette action avec sa résolution. Couper une source et montrer l'indisponibilité et la reprise.

**Présentation et questions — 5 min.** Six diapositives recommandées : mission et limites ; architecture Windows/Docker/Wi-Fi ; flux et contrats de reprise ; IA locale et protocole d'évaluation ; sécurité et audit réellement exécuté ; résultats de recette et travaux restant à valider. Pour chaque chiffre, donner le matériel, la méthode et l'origine des données.

## Poster A3

Titre : « SENTINEL-X — Voir les signaux. Anticiper les écarts. » Trois colonnes : acquisition / traitement local / supervision sécurisée. Au centre, schéma réel du réseau et des frontières TLS. En bas, résultats mesurés et limites : pas de reconnaissance faciale, pas de diagnostic certifié, données fictives clairement distinguées. Ajouter photos du boîtier, groupe et campus uniquement après validation par l'équipe.
