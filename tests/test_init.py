"""Tests de la mise en route, du déchargement et du problème « rubrique retirée »."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from custom_components.carte_des_artisans.const import DOMAIN
from custom_components.carte_des_artisans.diagnostics import async_get_config_entry_diagnostics

from .conftest import couper_site


async def test_setup_et_unload(hass: HomeAssistant, site, creer_entree) -> None:
    """L'entrée se charge, crée ses deux capteurs, puis se décharge."""
    entree = creer_entree()
    assert await hass.config_entries.async_setup(entree.entry_id)
    await hass.async_block_till_done()
    assert entree.state is ConfigEntryState.LOADED
    assert len(hass.states.async_entity_ids("sensor")) == 2

    assert await hass.config_entries.async_unload(entree.entry_id)
    await hass.async_block_till_done()
    assert entree.state is ConfigEntryState.NOT_LOADED


async def test_cache_disque(hass: HomeAssistant, site, creer_entree) -> None:
    """Le cache des fichiers est rangé dans .cache/ du dossier de configuration."""
    entree = creer_entree()
    assert await hass.config_entries.async_setup(entree.entry_id)
    await hass.async_block_till_done()
    assert await hass.async_add_executor_job(
        lambda: __import__("os").path.isfile(hass.config.cache_path(DOMAIN, "index.json"))
    )


async def test_site_injoignable(hass: HomeAssistant, aioclient_mock, creer_entree) -> None:
    """Site injoignable au démarrage : nouvel essai plus tard."""
    couper_site(aioclient_mock)
    entree = creer_entree()
    await hass.config_entries.async_setup(entree.entry_id)
    await hass.async_block_till_done()
    assert entree.state is ConfigEntryState.SETUP_RETRY


async def test_rubrique_retiree(hass: HomeAssistant, site, creer_entree, issue_registry) -> None:
    """Rubrique disparue du site : réparation signalée, effacée avec l'entrée."""
    entree = creer_entree(rubrique="maison-depannage.disparue", titre="Disparue")
    await hass.config_entries.async_setup(entree.entry_id)
    await hass.async_block_till_done()
    assert entree.state is ConfigEntryState.SETUP_RETRY
    probleme = issue_registry.async_get_issue(DOMAIN, f"rubrique_inconnue_{entree.entry_id}")
    assert probleme is not None
    assert probleme.severity is ir.IssueSeverity.ERROR
    assert probleme.translation_placeholders["rubrique"] == "maison-depannage.disparue"

    await hass.config_entries.async_remove(entree.entry_id)
    await hass.async_block_till_done()
    assert issue_registry.async_get_issue(DOMAIN, f"rubrique_inconnue_{entree.entry_id}") is None


async def test_diagnostics(hass: HomeAssistant, site, creer_entree) -> None:
    """Diagnostics : position masquée."""
    entree = creer_entree(suivre_maison=False, position={"latitude": 43.6, "longitude": 1.44})
    assert await hass.config_entries.async_setup(entree.entry_id)
    await hass.async_block_till_done()
    diag = await async_get_config_entry_diagnostics(hass, entree)
    assert diag["options"]["position"] == "**REDACTED**"
    assert diag["resultat"]["nombre"] == 3
    assert "43.6" not in str(diag)
