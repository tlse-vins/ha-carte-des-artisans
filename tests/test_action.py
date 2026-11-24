"""Tests de l'action carte_des_artisans.chercher_artisan."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.setup import async_setup_component

from custom_components.carte_des_artisans.const import ACTION_CHERCHER, DOMAIN

try:
    from probatio import Invalid
except ImportError:  # Home Assistant antérieur au passage à probatio
    from voluptuous import Invalid

# Champs refusés par le schéma de l'action
REFUS = (Invalid, ServiceValidationError)


@pytest.fixture
async def integration(hass: HomeAssistant, site) -> None:
    """Intégration chargée sans entrée : l'action existe quand même."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()


async def _appeler(hass: HomeAssistant, **champs):
    return await hass.services.async_call(DOMAIN, ACTION_CHERCHER, champs, blocking=True, return_response=True)


async def test_reponse(hass: HomeAssistant, integration) -> None:
    """Réponse complète autour de la maison."""
    r = await _appeler(hass, metier="maison-depannage.plombier")
    assert r["trouve"] is True
    assert r["nombre"] == 3
    assert r["metier"] == "Plombier"
    assert r["rayon_km"] == 10
    assert [a["nom"] for a in r["artisans"]] == ["ATELIER MAITRE", "DUPONT JEAN", "PLOMBERIE DU CAPITOLE"]
    assert r["lien_carte"].endswith("&ville=toulouse|31")
    # Site non https : jamais exposé
    assert r["artisans"][2]["site"] == ""


@pytest.mark.parametrize("metier", ["Électricien", "electricien", "ÉLECTRICIEN", "Dépannage maison › Électricien"])
async def test_metier_par_nom(hass: HomeAssistant, integration, metier: str) -> None:
    """Le nom du métier, avec ou sans accents ni majuscules."""
    r = await _appeler(hass, metier=metier)
    assert r["metier"] == "Électricien"
    assert r["artisans"][0]["labels"] == ["Entreprise du patrimoine vivant"]


async def test_metier_inconnu(hass: HomeAssistant, integration) -> None:
    """Métier inconnu : erreur de validation traduite."""
    with pytest.raises(ServiceValidationError) as err:
        await _appeler(hass, metier="Astronaute")
    assert err.value.translation_key == "metier_inconnu"
    assert err.value.translation_domain == DOMAIN


async def test_nombre_plafonne(hass: HomeAssistant, integration) -> None:
    """Le nombre d'artisans renvoyés est limité, le total reste exact."""
    r = await _appeler(hass, metier="Plombier", nombre=1, rayon="50")
    assert r["nombre"] == 4
    assert r["rayon_km"] == 50
    assert len(r["artisans"]) == 1
    with pytest.raises(REFUS):
        await _appeler(hass, metier="Plombier", nombre=51)


async def test_coordonnees(hass: HomeAssistant, integration) -> None:
    """Coordonnées fournies : recherche autour d'Albi, pas de la maison."""
    r = await _appeler(hass, metier="Plombier", latitude=43.9289, longitude=2.1464, rayon=5)
    assert [a["nom"] for a in r["artisans"]] == ["PLOMBIER D'ALBI"]
    assert r["lien_carte"].endswith("&ville=albi|81")
    # Latitude sans longitude : refusé
    with pytest.raises(REFUS):
        await _appeler(hass, metier="Plombier", latitude=43.9)


async def test_aucun_resultat(hass: HomeAssistant, integration) -> None:
    """Rien dans le rayon."""
    r = await _appeler(hass, metier="Plombier", latitude=45.0, longitude=1.0, rayon=5)
    assert r["trouve"] is False
    assert r["nombre"] == 0
    assert r["artisans"] == []


async def test_labellises(hass: HomeAssistant, integration) -> None:
    """Labellisés seulement."""
    r = await _appeler(hass, metier="Plombier", labellises=True)
    assert r["nombre"] == 2


async def test_position_manquante(hass: HomeAssistant, integration) -> None:
    """Maison non localisée et pas de coordonnées : erreur traduite."""
    hass.config.latitude = hass.config.longitude = 0
    with pytest.raises(ServiceValidationError) as err:
        await _appeler(hass, metier="Plombier")
    assert err.value.translation_key == "position_inconnue"
