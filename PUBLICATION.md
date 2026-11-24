# Publier l'intégration Home Assistant

Note pour le propriétaire (pas la documentation des utilisateurs, qui est le
`README.md`). Exigences relevées le 22/11/2026 sur :

- https://contributors.home-assistant.io/marketplace/guides/catalog/
- https://contributors.home-assistant.io/marketplace/reference/validation/
- https://contributors.home-assistant.io/marketplace/reference/hacs-json/
- https://www.hacs.xyz/docs/publish/include/ et /docs/publish/integration/

Depuis Home Assistant 2026.11, HACS est intégré à Home Assistant sous le nom
**Marketplace** ; le catalogue reste le dépôt `hacs/default`, avec les mêmes
règles.

## 1. Créer le dépôt GitHub

1. Sur github.com (compte `tlse-vins`) : **New repository**, nom
   `ha-carte-des-artisans`, **Public** (obligatoire), sans README ni licence
   (ils sont déjà dans le dossier).
2. Description (affichée par la Marketplace, exigée par le catalogue) :
   « Intégration Home Assistant : artisans d'un métier autour de la maison,
   données publiques de cartedesartisans.fr (Sirene, répertoire des métiers,
   labels RGE/EPV). Site indépendant. »
3. Website : `https://cartedesartisans.fr`.
4. Topics (exigés par le catalogue ; servent à la recherche) :
   `home-assistant`, `homeassistant`, `hacs`, `hacs-integration`,
   `home-assistant-custom-component`, `custom-integration`, `france`,
   `artisans`, `sirene`, `open-data`.
5. **Settings › General › Features** : laisser **Issues** coché (exigé).
6. **Settings › Actions › General › Workflow permissions** : « Read and write
   permissions » (le workflow Release pousse le commit de version et
   l'étiquette, puis crée la GitHub Release). Si une règle protège la branche
   `main`, autoriser GitHub Actions à la contourner.
7. **Settings › Security › Private vulnerability reporting** : activer (cité
   par `SECURITY.md`).
8. Envoyer le dossier `ha-carte-des-artisans` (depuis ce dossier) :

   ```powershell
   git init -b main
   git add .
   git commit -m "Première version"
   git remote add origin https://github.com/tlse-vins/ha-carte-des-artisans.git
   git push -u origin main
   ```

## 2. Vérifier les contrôles

Dans l'onglet **Actions**, après l'envoi, les trois workflows doivent être
verts :

- **Validate** (action HACS, sans `ignore`) : vérifie `hacs.json`, le logo
  (`brand/icon.png`), la description, les topics, les tickets activés, le
  README, les `categories` du manifest (facultatives : simple avertissement
  si absentes) ;
- **Hassfest** : vérifie le manifest, `services.yaml`, les traductions ;
- **Tests**.

Garder les liens de ces exécutions réussies : ils sont demandés dans la
demande d'inscription.

## 3. Première version

1. Vérifier la section `## [Unreleased]` de `CHANGELOG.md`.
2. **Actions › Release › Run workflow** ; choisir `major` : la première version publiée est la `1.0.0`
   (décision du propriétaire, 22/11/2026).
3. Le workflow écrit la version dans `manifest.json`, déplace le changelog,
   pousse l'étiquette `vX.Y.Z` et crée une **vraie GitHub Release** (le
   catalogue refuse une simple étiquette).

## 4. Essai comme dépôt personnalisé

Sur un Home Assistant 2026.3 ou plus récent :

1. Ouvrir le lien « My Home Assistant » du README (Marketplace), ou ajouter
   `https://github.com/tlse-vins/ha-carte-des-artisans` comme dépôt
   personnalisé de type **Intégration**.
2. Télécharger, redémarrer, ajouter l'intégration, vérifier les capteurs, le
   logo (clair et sombre), l'action dans Outils de développement › Actions.
3. Le dépôt est alors utilisable par tous ceux qui l'ajoutent à la main.

## 5. Demande d'inscription au catalogue (`hacs/default`)

Conditions (toutes vérifiées par un robot, puis par l'équipe) :

- dépôt public, non archivé, avec description, topics, tickets activés et
  README ;
- action HACS et hassfest qui passent, **sans aucun `ignore`** ;
- au moins une GitHub Release complète, créée après le passage des contrôles ;
- `brand/icon.png` présent ; `hacs.json` avec au moins `name` ; manifest avec
  `domain`, `documentation`, `issue_tracker`, `codeowners`, `name`, `version` ;
- licence présente ; demande faite par le propriétaire du dépôt (ou un
  contributeur important) ;
- pas de remplacement d'une intégration de Home Assistant, ni de domaine déjà
  pris (`carte_des_artisans` est libre à ce jour).

Étapes :

1. Forker https://github.com/hacs/default depuis le **compte personnel**
   `tlse-vins` (pas depuis une organisation : l'équipe doit pouvoir modifier
   la demande).
2. Créer une branche à partir de `master` (ne pas travailler sur `master`).
3. Dans le fichier `integration` (liste JSON), ajouter
   `"tlse-vins/ha-carte-des-artisans"` **à sa place alphabétique**, pas à la
   fin ; le fichier doit rester un JSON valide et trié.
4. Ouvrir la pull request vers `hacs/default` et remplir **tout** le modèle :
   cases à cocher, lien vers la dernière release, lien vers une exécution
   réussie de l'action HACS (sans `ignore`), lien vers une exécution réussie
   de hassfest.
5. Ne demander de revue à personne : une demande incomplète, inexacte ou une
   sollicitation de revue entraîne la fermeture sans préavis ; un petit
   problème la repasse en brouillon (corriger puis « Ready for review »).

Délai : l'équipe annonce **plusieurs mois** pour les nouveaux ajouts (file
d'attente visible dans le « backlog » du dépôt). Après fusion, le dépôt entre
dans le catalogue au scan suivant ; les utilisateurs le trouvent alors
directement dans la Marketplace, et le lien du README fonctionne sans étape
« dépôt personnalisé ».

## 6. Ensuite

- Chaque évolution : une ligne sous `## [Unreleased]`, puis
  **Actions › Release**. La Marketplace propose les dernières releases.
- Renommer ou transférer le dépôt : rien à faire, l'équipe met le catalogue à
  jour. Archiver le dépôt le retire du catalogue. **Ne jamais supprimer** un
  dépôt inscrit au catalogue (cela interdit toute inscription future) :
  demander d'abord le retrait par un ticket « Request for repository
  removal » dans `hacs/integration`.
- Si l'intégration devient un jour une intégration officielle de Home
  Assistant, retirer le dossier `brand/` et proposer les images au dépôt
  `home-assistant/brands`.
