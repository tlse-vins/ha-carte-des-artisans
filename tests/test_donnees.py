"""Tests de donnees.py : faux site local (aiohttp.web) servant tests/site/, aucun accès réseau réel."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import aiohttp
import pytest

from custom_components.carte_des_artisans.donnees import (
    DonneesIndisponibles,
    FormatNonPrisEnCharge,
    SourceDonnees,
    lire_variable,
)

SITE = Path(__file__).parent / "site"
INDEX = json.loads((SITE / "index.json").read_text(encoding="utf-8"))


class _Reponse:
    def __init__(self, status: int, contenu: bytes = b"") -> None:
        self.status = status
        self._contenu = contenu

    async def __aenter__(self) -> _Reponse:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def text(self) -> str:
        return self._contenu.decode("utf-8")

    async def json(self, content_type: str | None = "application/json") -> Any:
        return json.loads(self._contenu)


class FauxSite:
    """Fausse session aiohttp servant tests/site/ aux adresses du site ; garde les chemins demandés.

    Les tests de Home Assistant bloquent les sockets : aucun vrai serveur ici.
    """

    url = "https://site.test"

    def __init__(self) -> None:
        self.appels: list[str] = []
        self.panne: bool | str = False
        self.index: Any = INDEX
        self.agents: set[str] = set()
        self.delais: set[Any] = set()
        self.session = self

    def get(self, url: str, *, headers: dict[str, str], timeout: Any) -> _Reponse:
        chemin = url.removeprefix(self.url + "/")
        self.appels.append(chemin)
        self.agents.add(headers.get("User-Agent", ""))
        self.delais.add(timeout.total)
        if self.panne == "connexion":
            raise aiohttp.ClientConnectionError("réseau coupé")
        if self.panne:
            return _Reponse(503)
        if chemin == "donnees/export/index.json":
            return _Reponse(200, json.dumps(self.index).encode())
        if chemin.startswith("donnees/export/"):
            fichier = SITE / chemin.removeprefix("donnees/export/")
        elif chemin.startswith("donnees/"):
            fichier = SITE / chemin.removeprefix("donnees/")
        else:
            return _Reponse(404)
        if not fichier.is_file():
            return _Reponse(404)
        return _Reponse(200, fichier.read_bytes())


@pytest.fixture
def faux_site() -> FauxSite:
    return FauxSite()


async def _executer(fonction, *args):
    # Exécuteur synchrone : évite les fils d'exécution dans les tests
    return fonction(*args)


def _source(site: FauxSite, dossier: str | None, horloge: list[float] | None = None) -> SourceDonnees:
    horloge = horloge if horloge is not None else [0.0]
    return SourceDonnees(
        site.session,
        dossier,
        site=site.url,
        executer=_executer,
        maintenant=lambda: horloge[0],
    )


def test_lire_variable() -> None:
    assert lire_variable('// x\nwindow.A = {"b":1};\r\nwindow.B = [2];\n', "B") == [2]
    with pytest.raises(ValueError, match="introuvable"):
        lire_variable("rien", "A")


async def test_index_et_fichiers_en_memoire(faux_site: FauxSite) -> None:
    horloge = [0.0]
    source = _source(faux_site, None, horloge)
    index = await source.index()
    await source.index()
    assert len(await source.lignes(index, "31", "4322AZ")) == 4
    await source.lignes(index, "31", "4322AZ")
    assert faux_site.appels == ["donnees/export/index.json", "donnees/export/31/4322AZ.json"]
    assert faux_site.agents == {"CarteDesArtisans-HomeAssistant (+https://cartedesartisans.fr)"}

    horloge[0] = 13 * 3600
    await source.index()
    await source.lignes(index, "31", "4322AZ")
    assert len(faux_site.appels) == 3, "index relu ; mêmes données : fichiers gardés"


async def test_fichier_absent(faux_site: FauxSite) -> None:
    source = _source(faux_site, None)
    index = await source.index()
    assert await source.lignes(index, "2A", "4322AZ") == []
    assert await source.lignes(index, "31", "ABSENT") == []


async def test_cache_disque_et_purge(faux_site: FauxSite, tmp_path: Path) -> None:
    dossier = str(tmp_path / "cache")
    source = _source(faux_site, dossier)
    index = await source.index()
    await source.lignes(index, "31", "4322AZ")
    await source.communes(index)
    assert sorted(os.listdir(dossier)) == ["2026-11-21", "index.json"]
    # Un reste d'un ancien mois, et un fichier temporaire oublié
    (tmp_path / "cache" / "2026-10-13").mkdir()
    (tmp_path / "cache" / "2026-10-13" / "x.json").write_text("[]", encoding="utf-8")

    # Redémarrage, site en panne : le disque suffit
    faux_site.panne = True
    source = _source(faux_site, dossier)
    index = await source.index()
    assert index["genere"] == "2026-11-21"
    assert len(await source.lignes(index, "31", "4322AZ")) == 4
    assert len(await source.communes(index)) == 3
    with pytest.raises(DonneesIndisponibles):
        await source.lignes(index, "81", "4322AZ")

    # Mois suivant : fichiers relus, anciens mois purgés
    faux_site.panne = False
    faux_site.index = {**INDEX, "genere": "2026-12-21T06:00:00"}
    faux_site.appels.clear()
    source = _source(faux_site, dossier)
    index = await source.index()
    await source.lignes(index, "31", "4322AZ")
    assert "donnees/export/31/4322AZ.json" in faux_site.appels
    assert sorted(os.listdir(dossier)) == ["2026-12-21T06_00_00", "index.json"]


async def test_format_inconnu(faux_site: FauxSite, tmp_path: Path) -> None:
    faux_site.index = {**INDEX, "version": 2}
    with pytest.raises(FormatNonPrisEnCharge):
        await _source(faux_site, None).index()

    # Une copie valide existe : elle est gardée, avec une erreur au journal
    horloge = [0.0]
    faux_site.index = INDEX
    source = _source(faux_site, str(tmp_path), horloge)
    await source.index()
    faux_site.index = {**INDEX, "version": 2, "genere": "2027-01-21"}
    horloge[0] = 13 * 3600
    assert (await source.index())["genere"] == "2026-11-21"
    # Même chose après un redémarrage (copie sur le disque)
    assert (await _source(faux_site, str(tmp_path)).index())["genere"] == "2026-11-21"


async def test_site_injoignable_sans_copie(faux_site: FauxSite) -> None:
    faux_site.panne = True
    with pytest.raises(DonneesIndisponibles) as erreur:
        await _source(faux_site, None).index()
    assert not isinstance(erreur.value, FormatNonPrisEnCharge)


async def test_erreur_reseau_copie_gardee(faux_site: FauxSite) -> None:
    horloge = [0.0]
    source = _source(faux_site, None, horloge)
    index = await source.index()
    await source.lignes(index, "31", "4322AZ")
    assert await source.fichier_admin("maitres")
    faux_site.panne = "connexion"
    horloge[0] = 13 * 3600
    assert await source.index() is index
    assert len(await source.lignes(index, "31", "4322AZ")) == 4
    assert list(await source.fichier_admin("maitres")) == ["52530571000044"]
    assert faux_site.delais == {30}

    # Aucune copie : erreur claire
    vide = _source(faux_site, None)
    with pytest.raises(DonneesIndisponibles):
        await vide.index()
    assert await vide.fichier_admin("maitres") == {}


async def test_fichiers_admin(faux_site: FauxSite) -> None:
    horloge = [0.0]
    source = _source(faux_site, None, horloge)
    assert list(await source.fichier_admin("maitres")) == ["52530571000044"]
    enrichies = await source.fichier_admin("enrichies")
    assert enrichies["22222222200022"]["telephone"] == "05 61 00 00 00"
    await source.fichier_admin("maitres")
    assert faux_site.appels.count("donnees/maitres-artisans.js") == 1
    assert "donnees/recommandes.js" not in faux_site.appels

    # Panne après 7 h : dernière copie gardée
    faux_site.panne = True
    horloge[0] = 7 * 3600
    assert list(await source.fichier_admin("maitres")) == ["52530571000044"]
    assert faux_site.appels.count("donnees/maitres-artisans.js") == 2


async def test_fichier_admin_absent(faux_site: FauxSite, tmp_path: Path) -> None:
    source = _source(faux_site, None)
    source.site = faux_site.url + "/ailleurs"
    assert await source.fichier_admin("enrichies") == {}


async def test_executeur_par_defaut(faux_site: FauxSite, tmp_path: Path) -> None:
    source = SourceDonnees(faux_site.session, str(tmp_path), site=faux_site.url)
    index = await source.index()
    assert len(await source.lignes(index, "31", "4321A")) == 1
    assert (tmp_path / "2026-11-21" / "31" / "4321A.json").is_file()
