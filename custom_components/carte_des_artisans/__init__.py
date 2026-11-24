"""Intégration Home Assistant de la Carte des artisans (cartedesartisans.fr).

Une entrée par métier et par lieu (maison ou lieu choisi) : capteurs « nombre
d'artisans dans le rayon » et « artisan le plus proche ». L'action
``carte_des_artisans.chercher_artisan`` (enregistrée une fois, indépendante
des entrées) renvoie les artisans d'un métier autour de la maison ou d'un
point donné. Labellisés d'abord, puis les plus proches ; aucun bloc
« Sponsorisé » ; la position ne quitte jamais Home Assistant.
"""

from __future__ import annotations

from typing import Any

try:
    import probatio
except ImportError:  # Home Assistant antérieur au passage à probatio
    import voluptuous as probatio

from homeassistant.const import Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, issue_registry as ir
from homeassistant.helpers.typing import ConfigType

from .const import (
    ACTION_CHERCHER,
    DOMAIN,
    NOMBRE_ACTION_DEFAUT,
    NOMBRE_ACTION_MAX,
    RAYON_DEFAUT,
    RAYONS,
)
from .coordinator import (
    ArtisansConfigEntry,
    CoordinateurArtisans,
    id_probleme,
    obtenir_source,
    position_maison,
)
from .donnees import DonneesIndisponibles
from .recherche import rechercher, trouver_rubrique

PLATFORMS: list[Platform] = [Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

CHAMP_METIER = "metier"
CHAMP_RAYON = "rayon"
CHAMP_LABELLISES = "labellises"
CHAMP_LATITUDE = "latitude"
CHAMP_LONGITUDE = "longitude"
CHAMP_NOMBRE = "nombre"

SCHEMA_ACTION = probatio.Schema(
    {
        probatio.Required(CHAMP_METIER): cv.string,
        probatio.Optional(CHAMP_RAYON, default=RAYON_DEFAUT): probatio.All(probatio.Coerce(int), probatio.In(RAYONS)),
        probatio.Optional(CHAMP_LABELLISES, default=False): cv.boolean,
        probatio.Inclusive(CHAMP_LATITUDE, "position"): cv.latitude,
        probatio.Inclusive(CHAMP_LONGITUDE, "position"): cv.longitude,
        probatio.Optional(CHAMP_NOMBRE, default=NOMBRE_ACTION_DEFAUT): probatio.All(
            probatio.Coerce(int), probatio.Range(min=1, max=NOMBRE_ACTION_MAX)
        ),
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Enregistre l'action, disponible même sans entrée configurée."""

    async def chercher_artisan(call: ServiceCall) -> ServiceResponse:
        return await _chercher_artisan(hass, call.data)

    hass.services.async_register(
        DOMAIN,
        ACTION_CHERCHER,
        chercher_artisan,
        schema=SCHEMA_ACTION,
        supports_response=SupportsResponse.ONLY,
    )
    return True


async def _chercher_artisan(hass: HomeAssistant, donnees: dict[str, Any]) -> ServiceResponse:
    """Réponse de l'action ``chercher_artisan``."""
    source = obtenir_source(hass)
    if CHAMP_LATITUDE in donnees:
        centre = (float(donnees[CHAMP_LATITUDE]), float(donnees[CHAMP_LONGITUDE]))
    elif (centre := position_maison(hass)) is None:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="position_inconnue")
    try:
        index = await source.index()
        rubrique = trouver_rubrique(index, donnees[CHAMP_METIER])
        if rubrique is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="metier_inconnu",
                translation_placeholders={"metier": donnees[CHAMP_METIER]},
            )
        r = await rechercher(
            source,
            rubrique=rubrique,
            centre=centre,
            rayon_km=donnees[CHAMP_RAYON],
            labellises=donnees[CHAMP_LABELLISES],
        )
    except DonneesIndisponibles as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="donnees_indisponibles",
            translation_placeholders={"erreur": str(err)},
        ) from err
    if r["etat"] != "ok":
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="metier_inconnu",
            translation_placeholders={"metier": donnees[CHAMP_METIER]},
        )
    return {
        "trouve": r["nombre"] > 0,
        "nombre": r["nombre"],
        "metier": r["titre"],
        "rayon_km": r["rayon_km"],
        "artisans": r["resultats"][: donnees[CHAMP_NOMBRE]],
        "lien_carte": r["lien_carte"],
    }


async def async_setup_entry(hass: HomeAssistant, entry: ArtisansConfigEntry) -> bool:
    """Crée le coordinateur de l'entrée et ses capteurs."""
    coordinateur = CoordinateurArtisans(hass, entry)
    await coordinateur.async_config_entry_first_refresh()
    entry.runtime_data = coordinateur
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ArtisansConfigEntry) -> bool:
    """Décharge les capteurs de l'entrée."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ArtisansConfigEntry) -> None:
    """Efface le problème « rubrique retirée » de l'entrée supprimée."""
    ir.async_delete_issue(hass, DOMAIN, id_probleme(entry))
