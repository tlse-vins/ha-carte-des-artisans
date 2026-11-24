"""Tests des capteurs : valeurs, attributs, ordre, indisponibilité."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.const import ATTR_ATTRIBUTION, ATTR_UNIT_OF_MEASUREMENT, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.carte_des_artisans.const import DOMAIN, SITE
from custom_components.carte_des_artisans.donnees import DonneesIndisponibles

from .conftest import PLOMBIER


async def _demarrer(hass: HomeAssistant, entree) -> tuple[str, str]:
    assert await hass.config_entries.async_setup(entree.entry_id)
    await hass.async_block_till_done()
    registre = er.async_get(hass)
    nombre = registre.async_get_entity_id("sensor", DOMAIN, f"{entree.entry_id}_nombre")
    proche = registre.async_get_entity_id("sensor", DOMAIN, f"{entree.entry_id}_plus_proche")
    assert nombre and proche
    return nombre, proche


async def test_valeurs(hass: HomeAssistant, site, creer_entree) -> None:
    """Plombiers à 10 km de Toulouse : labellisés d'abord, puis le plus proche."""
    entree = creer_entree()
    nombre, proche = await _demarrer(hass, entree)

    etat = hass.states.get(nombre)
    assert etat.state == "3"
    assert etat.attributes[ATTR_UNIT_OF_MEASUREMENT] == "craftsmen"
    assert etat.attributes["state_class"] == "measurement"
    assert etat.attributes["rubrique"] == PLOMBIER
    assert etat.attributes["rayon_km"] == 10
    assert etat.attributes["labellises_seulement"] is False
    assert etat.attributes["donnees_du"] == "2026-11-21"
    assert etat.attributes["lien_carte"].startswith(f"{SITE}/carte.html?mtm_campaign=homeassistant#rub=")
    assert "43.6" not in etat.attributes["lien_carte"]
    assert "Sirene" in etat.attributes[ATTR_ATTRIBUTION]
    assert etat.name == "Plombier · 10 km Craftsmen in the radius"

    etat = hass.states.get(proche)
    # Maître artisan à 170 m, puis RGE à 4,5 km, puis le non labellisé à 0 m
    assert etat.state == "ATELIER MAITRE"
    assert etat.attributes["labels"] == ["Maître artisan"]
    assert etat.attributes["lien"].endswith("siret=52530571000044&mtm_campaign=homeassistant")
    noms = [a["nom"] for a in etat.attributes["artisans"]]
    assert noms == ["ATELIER MAITRE", "DUPONT JEAN", "PLOMBERIE DU CAPITOLE"]
    dupont = etat.attributes["artisans"][1]
    assert dupont["telephone"] == "05 61 00 00 00"
    assert "email" not in dupont
    assert "x@exemple.fr" not in str(etat.attributes)

    # Appareil de service par entrée
    (appareil,) = dr.async_entries_for_config_entry(dr.async_get(hass), entree.entry_id)
    assert appareil.identifiers == {(DOMAIN, entree.entry_id)}
    assert appareil.entry_type is dr.DeviceEntryType.SERVICE
    assert appareil.name == "Plombier · 10 km"
    assert appareil.configuration_url == SITE


async def test_labellises_seulement(hass: HomeAssistant, site, creer_entree) -> None:
    """Filtre labellisés : le non labellisé disparaît."""
    nombre, _ = await _demarrer(hass, creer_entree(labellises=True))
    assert hass.states.get(nombre).state == "2"
    assert hass.states.get(nombre).attributes["labellises_seulement"] is True


async def test_aucun_resultat(hass: HomeAssistant, site, creer_entree) -> None:
    """Rien dans le rayon : 0 et état inconnu, liste vide."""
    entree = creer_entree(suivre_maison=False, position={"latitude": 45.0, "longitude": 1.0}, rayon=5)
    nombre, proche = await _demarrer(hass, entree)
    assert hass.states.get(nombre).state == "0"
    assert hass.states.get(proche).state == STATE_UNKNOWN
    assert hass.states.get(proche).attributes["artisans"] == []


async def test_artisans_non_enregistres(hass: HomeAssistant, site, creer_entree) -> None:
    """La liste détaillée n'entre pas dans l'historique."""
    entree = creer_entree()
    await _demarrer(hass, entree)
    capteur = next(e for e in hass.data["entity_components"]["sensor"].entities if e.unique_id.endswith("_plus_proche"))
    assert "artisans" in capteur._unrecorded_attributes


async def test_panne_puis_retour(hass: HomeAssistant, site, creer_entree) -> None:
    """Données illisibles : capteurs indisponibles, puis rétablis."""
    entree = creer_entree()
    nombre, proche = await _demarrer(hass, entree)
    coordinateur = entree.runtime_data

    with patch(
        "custom_components.carte_des_artisans.coordinator.rechercher",
        side_effect=DonneesIndisponibles("panne"),
    ):
        await coordinateur.async_refresh()
        await hass.async_block_till_done()
    assert hass.states.get(nombre).state == STATE_UNAVAILABLE
    assert hass.states.get(proche).state == STATE_UNAVAILABLE

    await coordinateur.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(nombre).state == "3"
    assert hass.states.get(proche).state == "ATELIER MAITRE"


async def test_maison_relue(hass: HomeAssistant, site, creer_entree) -> None:
    """La position de la maison est relue à chaque mise à jour."""
    entree = creer_entree()
    _, proche = await _demarrer(hass, entree)
    hass.config.latitude, hass.config.longitude = 43.9289, 2.1464
    await entree.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(proche).state == "PLOMBIER D'ALBI"
