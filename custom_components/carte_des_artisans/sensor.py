"""Capteurs d'une entrée : nombre d'artisans dans le rayon et artisan le plus proche.

« Le plus proche » suit l'ordre du site : labellisés (RGE, EPV, Maître
artisan) d'abord, puis du plus proche au plus loin.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_LABELLISES, DOMAIN, MAX_ATTRIBUTS, SITE
from .coordinator import ArtisansConfigEntry, CoordinateurArtisans, reglages

# Les capteurs ne font aucune requête : le coordinateur s'en charge
PARALLEL_UPDATES = 0

ATTRIBUTION = (
    "Données Sirene (Insee), répertoire des métiers (CMA), labels ADEME et DGE — Carte des artisans, site indépendant"
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ArtisansConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Capteurs de l'entrée."""
    coordinateur = entry.runtime_data
    async_add_entities([CapteurNombre(coordinateur), CapteurPlusProche(coordinateur)])


class CapteurArtisans(CoordinatorEntity[CoordinateurArtisans], SensorEntity):
    """Base commune : appareil de service de l'entrée, nom traduit, attribution."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinateur: CoordinateurArtisans, cle: str) -> None:
        """Capteur ``cle`` de l'entrée."""
        super().__init__(coordinateur)
        entry = coordinateur.config_entry
        self._attr_translation_key = cle
        self._attr_unique_id = f"{entry.entry_id}_{cle}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            entry_type=DeviceEntryType.SERVICE,
            name=entry.title,
            manufacturer="Carte des artisans",
            configuration_url=SITE,
        )


class CapteurNombre(CapteurArtisans):
    """Nombre d'artisans dans le rayon."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinateur: CoordinateurArtisans) -> None:
        """Capteur « nombre »."""
        super().__init__(coordinateur, "nombre")

    @property
    def native_value(self) -> int:
        """Nombre de résultats."""
        return self.coordinator.data["nombre"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Rubrique, rayon, filtre, lien vers la carte, date des données."""
        d = self.coordinator.data
        return {
            "rubrique": d["rubrique"],
            "rayon_km": d["rayon_km"],
            "labellises_seulement": reglages(self.coordinator.config_entry)[CONF_LABELLISES],
            "lien_carte": d["lien_carte"],
            "donnees_du": d.get("genere"),
        }


class CapteurPlusProche(CapteurArtisans):
    """Premier artisan de la liste (labellisés d'abord, puis le plus proche)."""

    # Liste détaillée : utile à l'écran, trop volumineuse pour l'historique
    _unrecorded_attributes = frozenset({"artisans"})

    def __init__(self, coordinateur: CoordinateurArtisans) -> None:
        """Capteur « plus_proche »."""
        super().__init__(coordinateur, "plus_proche")

    @property
    def native_value(self) -> str | None:
        """Nom du premier artisan, ou inconnu s'il n'y en a aucun."""
        resultats = self.coordinator.data["resultats"]
        return resultats[0]["nom"] if resultats else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Champs du premier artisan + les premiers résultats dans ``artisans``."""
        resultats = self.coordinator.data["resultats"]
        attributs: dict[str, Any] = dict(resultats[0]) if resultats else {}
        attributs["artisans"] = resultats[:MAX_ATTRIBUTS]
        return attributs
