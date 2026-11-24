"""Fixtures communes : intégrations personnalisées, faux site, maison à Toulouse."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.carte_des_artisans.const import (
    CONF_LABELLISES,
    CONF_RAYON,
    CONF_RUBRIQUE,
    CONF_SUIVRE_MAISON,
    CONF_TITRE,
    DOMAIN,
    SITE,
)

DOSSIER_SITE = Path(__file__).parent / "site"
TOULOUSE = (43.6045, 1.4440)
PLOMBIER = "maison-depannage.plombier"
ELECTRICIEN = "maison-depannage.electricien"

# Fichier annoncé par index.json mais absent du site : 404
ABSENTS = ["donnees/export/2A/4322AZ.json"]


def _fichiers_site() -> dict[str, bytes]:
    """Chemin sur le vrai site → contenu, d'après tests/site/."""
    fichiers: dict[str, bytes] = {}
    for f in DOSSIER_SITE.rglob("*"):
        if not f.is_file():
            continue
        relatif = f.relative_to(DOSSIER_SITE).as_posix()
        prefixe = "donnees/" if f.suffix == ".js" else "donnees/export/"
        fichiers[prefixe + relatif] = f.read_bytes()
    return fichiers


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Charge custom_components/ dans tous les tests."""


@pytest.fixture(autouse=True)
def maison(hass: HomeAssistant, tmp_path: Path) -> None:
    """Maison à Toulouse ; configuration (donc cache disque) dans un dossier temporaire."""
    hass.config.latitude, hass.config.longitude = TOULOUSE
    hass.config.config_dir = str(tmp_path)


def servir_site(aioclient_mock: AiohttpClientMocker) -> None:
    """Enregistre les réponses du faux site."""
    for chemin, contenu in _fichiers_site().items():
        aioclient_mock.get(f"{SITE}/{chemin}", content=contenu)
    for chemin in ABSENTS:
        aioclient_mock.get(f"{SITE}/{chemin}", status=404)


def couper_site(aioclient_mock: AiohttpClientMocker) -> None:
    """Toute requête vers le site échoue (réseau coupé)."""
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{SITE}/donnees/export/index.json", exc=aiohttp.ClientError())


@pytest.fixture
def site(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """Faux site servi par le simulateur aiohttp de Home Assistant."""
    servir_site(aioclient_mock)
    return aioclient_mock


@pytest.fixture
def creer_entree(hass: HomeAssistant) -> Callable[..., MockConfigEntry]:
    """Fabrique d'entrée (plombier, 10 km, maison par défaut)."""

    def fabriquer(rubrique: str = PLOMBIER, titre: str = "Plombier", **options: Any) -> MockConfigEntry:
        reglages = {CONF_RAYON: 10, CONF_LABELLISES: False, CONF_SUIVRE_MAISON: True, **options}
        entree = MockConfigEntry(
            domain=DOMAIN,
            title=f"{titre} · {reglages[CONF_RAYON]} km",
            data={CONF_RUBRIQUE: rubrique, CONF_TITRE: titre},
            options=reglages,
            unique_id=f"{rubrique}|maison",
        )
        entree.add_to_hass(hass)
        return entree

    return fabriquer


@pytest.fixture
def sans_setup() -> Iterator[None]:
    """Empêche la mise en route de l'entrée créée par un parcours de configuration."""
    with patch("custom_components.carte_des_artisans.async_setup_entry", return_value=True):
        yield
