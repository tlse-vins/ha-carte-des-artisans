"""Diagnostics d'une entrée : réglages (position masquée) et résumé du dernier résultat."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_POSITION
from .coordinator import ArtisansConfigEntry

A_MASQUER = {CONF_POSITION, "latitude", "longitude", "lien_carte"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ArtisansConfigEntry) -> dict[str, Any]:
    """Réglages sans la position ; nombre de résultats sans les artisans."""
    coordinateur = entry.runtime_data
    d = coordinateur.data or {}
    return {
        "data": async_redact_data(dict(entry.data), A_MASQUER),
        "options": async_redact_data(dict(entry.options), A_MASQUER),
        "derniere_mise_a_jour_reussie": coordinateur.last_update_success,
        "resultat": {
            "etat": d.get("etat"),
            "rubrique": d.get("rubrique"),
            "rayon_km": d.get("rayon_km"),
            "nombre": d.get("nombre"),
            "donnees_du": d.get("genere"),
        },
    }
