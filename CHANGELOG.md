# Changelog

Toutes les évolutions notables de l'intégration sont décrites ici. Format
[Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), versions
[sémantiques](https://semver.org/lang/fr/).

Chaque évolution s'ajoute sous `## [Unreleased]` ; le workflow Release déplace
cette section sous la version publiée, et elle devient le texte de la GitHub
Release.

## [Unreleased]

### Added

- Configuration par l'interface : métier (rubrique du site), rayon de 5, 10,
  25 ou 50 km, entreprises labellisées seulement, position de la maison ou
  lieu choisi sur une carte ; plusieurs entrées possibles.
- Capteur « Artisans dans le rayon » (nombre d'artisans).
- Capteur « Premier artisan » (labellisés d'abord, puis le plus proche), avec les 10 premiers résultats en
  attributs (nom, activité, adresse, distance, labels, téléphone, liens).
- Action `carte_des_artisans.chercher_artisan` avec réponse, utilisable dans
  les automatisations, les scripts et par Assist.
- Ordre du site : entreprises labellisées (RGE, EPV, Maître artisan) d'abord,
  puis les plus proches.
- Données publiques de cartedesartisans.fr téléchargées seulement pour les
  départements à portée du rayon ; la position n'est jamais envoyée.
- Traductions française et anglaise ; logo de l'intégration (`brand/`).
