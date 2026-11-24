"""Source de données partagée et coordinateur de mise à jour d'une entrée.

- ``obtenir_source`` : une seule ``SourceDonnees`` pour toutes les entrées et
  pour l'action, rangée dans ``hass.data`` ; cache disque dans
  ``.cache/carte_des_artisans`` du dossier de configuration (dossier prévu par
  Home Assistant pour les données régénérables, exclu des sauvegardes).
- ``CoordinateurArtisans`` : relance la recherche de l'entrée toutes les
  ``INTERVALLE_MAJ`` secondes, autour de la maison (relue à chaque fois) ou du
  lieu choisi. Une rubrique retirée du site est signalée dans les réparations.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util.hass_dict import HassKey

from .const import (
    CONF_LABELLISES,
    CONF_POSITION,
    CONF_RAYON,
    CONF_RUBRIQUE,
    CONF_SUIVRE_MAISON,
    DOMAIN,
    INTERVALLE_MAJ,
    RAYON_DEFAUT,
)
from .donnees import DonneesIndisponibles, SourceDonnees
from .recherche import rechercher

_LOGGER = logging.getLogger(__name__)

CLE_SOURCE: HassKey[SourceDonnees] = HassKey(DOMAIN)

type ArtisansConfigEntry = ConfigEntry[CoordinateurArtisans]


def obtenir_source(hass: HomeAssistant) -> SourceDonnees:
    """Source de données commune, créée au premier besoin."""
    if (source := hass.data.get(CLE_SOURCE)) is None:
        source = SourceDonnees(
            async_get_clientsession(hass),
            hass.config.cache_path(DOMAIN),
            executer=hass.async_add_executor_job,
        )
        hass.data[CLE_SOURCE] = source
    return source


def position_maison(hass: HomeAssistant) -> tuple[float, float] | None:
    """Position de la maison, ou None si elle n'est pas renseignée (0, 0)."""
    lat, lon = hass.config.latitude, hass.config.longitude
    if lat is None or lon is None or (lat == 0 and lon == 0):
        return None
    return (float(lat), float(lon))


def reglages(entry: ConfigEntry) -> dict[str, Any]:
    """Réglages de l'entrée : la rubrique dans ``data``, le reste dans ``options``."""
    return {
        CONF_RUBRIQUE: entry.data[CONF_RUBRIQUE],
        CONF_RAYON: int(entry.options.get(CONF_RAYON, RAYON_DEFAUT)),
        CONF_LABELLISES: bool(entry.options.get(CONF_LABELLISES, False)),
        CONF_SUIVRE_MAISON: bool(entry.options.get(CONF_SUIVRE_MAISON, True)),
        CONF_POSITION: entry.options.get(CONF_POSITION),
    }


def centre_entree(hass: HomeAssistant, entry: ConfigEntry) -> tuple[float, float] | None:
    """Point de recherche de l'entrée : la maison (relue) ou le lieu choisi."""
    r = reglages(entry)
    if r[CONF_SUIVRE_MAISON]:
        return position_maison(hass)
    position = r[CONF_POSITION] or {}
    if "latitude" not in position or "longitude" not in position:
        return None
    return (float(position["latitude"]), float(position["longitude"]))


def id_probleme(entry: ConfigEntry) -> str:
    """Identifiant du problème « rubrique retirée » propre à l'entrée."""
    return f"rubrique_inconnue_{entry.entry_id}"


class CoordinateurArtisans(DataUpdateCoordinator[dict[str, Any]]):
    """Résultat de la recherche d'une entrée (format de ``recherche.rechercher``)."""

    config_entry: ArtisansConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ArtisansConfigEntry) -> None:
        """Coordinateur d'une entrée."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=timedelta(seconds=INTERVALLE_MAJ),
        )
        self.source = obtenir_source(hass)

    async def _async_update_data(self) -> dict[str, Any]:
        """Relance la recherche."""
        entry = self.config_entry
        r = reglages(entry)
        centre = centre_entree(self.hass, entry)
        if centre is None:
            raise UpdateFailed(translation_domain=DOMAIN, translation_key="position_inconnue")
        try:
            resultat = await rechercher(
                self.source,
                rubrique=r[CONF_RUBRIQUE],
                centre=centre,
                rayon_km=r[CONF_RAYON],
                labellises=r[CONF_LABELLISES],
            )
        except DonneesIndisponibles as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="donnees_indisponibles",
                translation_placeholders={"erreur": str(err)},
            ) from err

        if resultat["etat"] == "rubrique-inconnue":
            # Rubrique retirée du site : réparation visible, entités indisponibles
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                id_probleme(entry),
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key="rubrique_inconnue",
                translation_placeholders={"entree": entry.title, "rubrique": r[CONF_RUBRIQUE]},
            )
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="rubrique_inconnue",
                translation_placeholders={"rubrique": r[CONF_RUBRIQUE]},
            )
        ir.async_delete_issue(self.hass, DOMAIN, id_probleme(entry))
        return resultat
