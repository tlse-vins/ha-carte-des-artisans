"""Tests du parcours de configuration et des options."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.carte_des_artisans.const import (
    CONF_LABELLISES,
    CONF_POSITION,
    CONF_RAYON,
    CONF_RUBRIQUE,
    CONF_SUIVRE_MAISON,
    CONF_TITRE,
    DOMAIN,
)

from .conftest import ELECTRICIEN, PLOMBIER, couper_site

ALBI = {"latitude": 43.9289, "longitude": 2.1464}


async def _demarrer(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})


async def test_maison(hass: HomeAssistant, site, sans_setup) -> None:
    """Métier autour de la maison : une seule étape."""
    resultat = await _demarrer(hass)
    assert resultat["type"] is FlowResultType.FORM
    assert resultat["step_id"] == "user"
    # Les rubriques du site sont proposées, « Catégorie › Titre »
    options = resultat["data_schema"].schema[CONF_RUBRIQUE].config["options"]
    assert {"value": PLOMBIER, "label": "Dépannage maison › Plombier"} in options

    resultat = await hass.config_entries.flow.async_configure(
        resultat["flow_id"],
        {CONF_RUBRIQUE: PLOMBIER, CONF_RAYON: "10", CONF_LABELLISES: False, CONF_SUIVRE_MAISON: True},
    )
    assert resultat["type"] is FlowResultType.CREATE_ENTRY
    assert resultat["title"] == "Plombier · 10 km"
    assert resultat["data"] == {CONF_RUBRIQUE: PLOMBIER, CONF_TITRE: "Plombier"}
    assert resultat["options"] == {CONF_RAYON: 10, CONF_LABELLISES: False, CONF_SUIVRE_MAISON: True}
    assert resultat["result"].unique_id == f"{PLOMBIER}|maison"


async def test_lieu_choisi(hass: HomeAssistant, site, sans_setup) -> None:
    """Sans la maison : étape de choix du lieu, titre « · lieu choisi » en français."""
    hass.config.language = "fr"
    resultat = await _demarrer(hass)
    resultat = await hass.config_entries.flow.async_configure(
        resultat["flow_id"],
        {CONF_RUBRIQUE: ELECTRICIEN, CONF_RAYON: "25", CONF_LABELLISES: True, CONF_SUIVRE_MAISON: False},
    )
    assert resultat["type"] is FlowResultType.FORM
    assert resultat["step_id"] == "position"

    resultat = await hass.config_entries.flow.async_configure(
        resultat["flow_id"], {CONF_POSITION: {**ALBI, "radius": 100}}
    )
    assert resultat["type"] is FlowResultType.CREATE_ENTRY
    assert resultat["title"] == "Électricien · 25 km · lieu choisi"
    assert resultat["options"] == {
        CONF_RAYON: 25,
        CONF_LABELLISES: True,
        CONF_SUIVRE_MAISON: False,
        CONF_POSITION: ALBI,
    }
    assert resultat["result"].unique_id == f"{ELECTRICIEN}|43.929,2.146"


async def test_deja_configure(hass: HomeAssistant, site, creer_entree, sans_setup) -> None:
    """Même métier, même lieu : abandon."""
    creer_entree()
    resultat = await _demarrer(hass)
    resultat = await hass.config_entries.flow.async_configure(
        resultat["flow_id"],
        {CONF_RUBRIQUE: PLOMBIER, CONF_RAYON: "50", CONF_LABELLISES: True, CONF_SUIVRE_MAISON: True},
    )
    assert resultat["type"] is FlowResultType.ABORT
    assert resultat["reason"] == "already_configured"


async def test_site_injoignable(hass: HomeAssistant, aioclient_mock, sans_setup) -> None:
    """Site injoignable et aucune copie : abandon propre."""
    couper_site(aioclient_mock)
    resultat = await _demarrer(hass)
    assert resultat["type"] is FlowResultType.ABORT
    assert resultat["reason"] == "cannot_connect"


async def test_maison_sans_position(hass: HomeAssistant, site, sans_setup) -> None:
    """Maison non localisée : erreur, puis lieu choisi accepté."""
    hass.config.latitude = hass.config.longitude = 0
    resultat = await _demarrer(hass)
    saisie = {CONF_RUBRIQUE: PLOMBIER, CONF_RAYON: "10", CONF_LABELLISES: False, CONF_SUIVRE_MAISON: True}
    resultat = await hass.config_entries.flow.async_configure(resultat["flow_id"], saisie)
    assert resultat["type"] is FlowResultType.FORM
    assert resultat["errors"] == {"base": "maison_sans_position"}

    resultat = await hass.config_entries.flow.async_configure(
        resultat["flow_id"], {**saisie, CONF_SUIVRE_MAISON: False}
    )
    assert resultat["step_id"] == "position"
    # Lieu proposé : le centre de la France
    defaut = resultat["data_schema"].schema
    cle = next(k for k in defaut if k == CONF_POSITION)
    assert cle.default() == {"latitude": 46.6, "longitude": 2.4}
    resultat = await hass.config_entries.flow.async_configure(resultat["flow_id"], {CONF_POSITION: ALBI})
    assert resultat["type"] is FlowResultType.CREATE_ENTRY


async def test_options(hass: HomeAssistant, site, creer_entree) -> None:
    """Rayon modifié : options, titre et rechargement."""
    entree = creer_entree()
    assert await hass.config_entries.async_setup(entree.entry_id)
    await hass.async_block_till_done()

    resultat = await hass.config_entries.options.async_init(entree.entry_id)
    assert resultat["type"] is FlowResultType.FORM
    assert resultat["step_id"] == "init"
    resultat = await hass.config_entries.options.async_configure(
        resultat["flow_id"], {CONF_RAYON: "50", CONF_LABELLISES: True, CONF_SUIVRE_MAISON: True}
    )
    await hass.async_block_till_done()
    assert resultat["type"] is FlowResultType.CREATE_ENTRY
    assert entree.options == {CONF_RAYON: 50, CONF_LABELLISES: True, CONF_SUIVRE_MAISON: True}
    assert entree.title == "Plombier · 50 km"
    assert entree.state is config_entries.ConfigEntryState.LOADED
    # Rechargée : le coordinateur applique les nouveaux réglages
    assert entree.runtime_data.data["rayon_km"] == 50


async def test_options_lieu_choisi(hass: HomeAssistant, site, creer_entree) -> None:
    """Passage à un lieu choisi : étape de position, identifiant mis à jour ; titre renommé gardé."""
    entree = creer_entree()
    hass.config_entries.async_update_entry(entree, title="Mon plombier")
    assert await hass.config_entries.async_setup(entree.entry_id)
    await hass.async_block_till_done()

    resultat = await hass.config_entries.options.async_init(entree.entry_id)
    resultat = await hass.config_entries.options.async_configure(
        resultat["flow_id"], {CONF_RAYON: "10", CONF_LABELLISES: False, CONF_SUIVRE_MAISON: False}
    )
    assert resultat["step_id"] == "position"
    resultat = await hass.config_entries.options.async_configure(resultat["flow_id"], {CONF_POSITION: ALBI})
    await hass.async_block_till_done()
    assert resultat["type"] is FlowResultType.CREATE_ENTRY
    assert entree.options[CONF_POSITION] == ALBI
    assert entree.unique_id == f"{PLOMBIER}|43.929,2.146"
    assert entree.title == "Mon plombier"
    # Autour d'Albi : le plombier d'Albi
    assert entree.runtime_data.data["resultats"][0]["nom"] == "PLOMBIER D'ALBI"


async def test_options_deja_configure(hass: HomeAssistant, site, creer_entree, sans_setup) -> None:
    """Options qui reprendraient le lieu d'une autre entrée du même métier : abandon."""
    creer_entree()
    autre = creer_entree(suivre_maison=False, position=ALBI)
    hass.config_entries.async_update_entry(autre, unique_id=f"{PLOMBIER}|43.929,2.146")

    resultat = await hass.config_entries.options.async_init(autre.entry_id)
    resultat = await hass.config_entries.options.async_configure(
        resultat["flow_id"], {CONF_RAYON: "10", CONF_LABELLISES: False, CONF_SUIVRE_MAISON: True}
    )
    assert resultat["type"] is FlowResultType.ABORT
    assert resultat["reason"] == "already_configured"
    assert autre.options[CONF_POSITION] == ALBI
