"""Constantes de l'intégration Carte des artisans (aucun import de Home Assistant)."""

DOMAIN = "carte_des_artisans"

# Site et format de l'export (donnees/export/, generer_export.py : VERSION)
SITE = "https://cartedesartisans.fr"
VERSION_EXPORT = 1
AGENT = "CarteDesArtisans-HomeAssistant (+https://cartedesartisans.fr)"
# Campagne Matomo : distingue ces visites dans la mesure d'audience du site
CAMPAGNE = "homeassistant"

# Rayons proposés (km), comme le widget Gladys
RAYONS = [5, 10, 25, 50]
RAYON_DEFAUT = 10

# Délais de relecture (secondes) : l'export change une fois par mois,
# les fichiers de l'admin (maitres-artisans.js, enrichies.js) plus souvent
DELAI_INDEX = 12 * 3600
DELAI_ADMIN = 6 * 3600
INTERVALLE_MAJ = 6 * 3600

# Nombre d'artisans détaillés dans les attributs du capteur
MAX_ATTRIBUTS = 10
# Réponse de l'action : par défaut, et au plus
NOMBRE_ACTION_DEFAUT = 5
NOMBRE_ACTION_MAX = 50

# Clés de configuration (stockées par Home Assistant : ne jamais les renommer)
CONF_RUBRIQUE = "rubrique"
CONF_RAYON = "rayon"
CONF_LABELLISES = "labellises"
CONF_SUIVRE_MAISON = "suivre_maison"
CONF_POSITION = "position"  # {"latitude": ..., "longitude": ...}
# Titre de la rubrique à la création (titre de l'entrée sans le site)
CONF_TITRE = "titre"

# Action
ACTION_CHERCHER = "chercher_artisan"
