"""Tests de recherche.py (module pur) avec les faux fichiers du site de tests/site/."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from custom_components.carte_des_artisans.donnees import lire_variable
from custom_components.carte_des_artisans.recherche import (
    chercher,
    cle_commune,
    commune_proche,
    distance_emprise,
    distance_km,
    formater_distance,
    lien_carte,
    lien_fiche,
    lien_itineraire,
    options_rubriques,
    rechercher,
    resultat_public,
    titre,
    trouver_rubrique,
)

SITE = Path(__file__).parent / "site"
INDEX = json.loads((SITE / "index.json").read_text(encoding="utf-8"))
COMMUNES = json.loads((SITE / "communes.json").read_text(encoding="utf-8"))
MAITRES = lire_variable((SITE / "maitres-artisans.js").read_text(encoding="utf-8"), "MAITRES_ARTISANS")
ENRICHIES = lire_variable((SITE / "enrichies.js").read_text(encoding="utf-8"), "ENRICHIES")
MAISON = (43.6045, 1.444)  # Toulouse, Capitole


class FausseSource:
    """Même interface que SourceDonnees, lue dans tests/site/ ; garde les fichiers lus."""

    def __init__(self) -> None:
        self.lus: list[str] = []
        self.admin: list[str] = []

    async def index(self) -> dict:
        return INDEX

    async def lignes(self, index: dict, dep: str, code: str) -> list:
        self.lus.append(f"{dep}/{code}")
        fichier = SITE / dep / f"{code}.json"
        return json.loads(fichier.read_text(encoding="utf-8")) if fichier.is_file() else []

    async def communes(self, index: dict) -> list:
        return COMMUNES

    async def fichier_admin(self, cle: str) -> dict:
        self.admin.append(cle)
        return {"maitres": MAITRES, "enrichies": ENRICHIES}[cle]


async def _chercher(source: FausseSource, **options: Any) -> list[dict]:
    return await chercher(
        index=INDEX,
        lire=lambda dep, code: source.lignes(INDEX, dep, code),
        centre=MAISON,
        **{"rayon_km": 10, "codes": ["4322AZ"], "maitres": MAITRES, **options},
    )


def test_distances() -> None:
    assert abs(distance_km((48.8566, 2.3522), (43.6047, 1.4442)) - 588) < 5
    assert distance_emprise((43, 1), [42, 0, 44, 2]) == 0
    assert formater_distance(0.43) == "450 m"
    assert formater_distance(0.01) == "100 m"
    assert formater_distance(0.825) == "850 m"
    assert formater_distance(2.44) == "2,4 km"
    assert formater_distance(2.45) == "2,5 km"
    assert formater_distance(12.6) == "13 km"
    assert formater_distance(12.5) == "13 km"


def test_textes_et_communes() -> None:
    assert titre("SAINT-ETIENNE-DU-ROUVRAY") == "Saint-Etienne-du-Rouvray"
    assert titre("3 RUE D'ALSACE-LORRAINE") == "3 Rue D'Alsace-Lorraine"
    assert titre("2 RUE DE BALMA") == "2 Rue de Balma"
    assert titre(None) == ""
    assert cle_commune("L'ISLE-JOURDAIN", "32") == "l isle jourdain|32"
    assert cle_commune("SAINT-ÉTIENNE", "42") == "saint etienne|42"
    assert commune_proche(COMMUNES, (43.61, 1.49)) == {"nom": "BALMA", "dep": "31", "cle": "balma|31"}
    assert commune_proche(COMMUNES, (0, 0)) is None


async def test_rayon_emprise_tri() -> None:
    source = FausseSource()
    r = await _chercher(source)
    assert sorted(source.lus) == ["31/4322AZ", "81/4322AZ"], "la Corse (2A) n'est jamais lue"
    assert [e["nom"] for e in r] == ["ATELIER MAITRE", "DUPONT JEAN", "PLOMBERIE DU CAPITOLE"]
    assert r[0]["labels"] == ["ma"]
    assert r[1]["labels"] == ["rge"]
    assert r[2]["labels"] == []
    assert set(r[0]) == {
        "siret",
        "nom",
        "enseigne",
        "adresse",
        "cp",
        "commune",
        "dep",
        "activite",
        "lat",
        "lon",
        "precis",
        "labels",
        "distance",
    }
    assert r[1]["dep"] == "31" and r[1]["activite"] == "4322AZ"

    # Petit rayon : le Tarn n'est plus lu ; grand rayon : Albiac entre, après les labellisés
    source = FausseSource()
    assert len(await _chercher(source, rayon_km=5)) == 3
    assert source.lus == ["31/4322AZ"]
    r = await _chercher(FausseSource(), rayon_km=50)
    assert [e["nom"] for e in r][-1] == "MARTIN SARL"


async def test_labellises_seulement_et_maitres() -> None:
    r = await _chercher(FausseSource(), labellises_seulement=True)
    assert [e["nom"] for e in r] == ["ATELIER MAITRE", "DUPONT JEAN"]
    r = await _chercher(FausseSource(), labellises_seulement=True, maitres=None)
    assert [e["nom"] for e in r] == ["DUPONT JEAN"]


async def test_resultat_public() -> None:
    r = await _chercher(FausseSource())
    dupont = resultat_public(r[1], ENRICHIES, INDEX["activites"])
    assert dupont == {
        "nom": "DUPONT JEAN",
        "enseigne": "EAU CHAUDE 31",
        "activite": "Plomberie",
        "adresse": "2 Rue de Balma, 31130 Balma",
        "commune": "Balma",
        "distance_km": round(r[1]["distance"], 1),
        "distance": formater_distance(r[1]["distance"]),
        "labels": ["RGE"],
        "telephone": "05 61 00 00 00",
        "site": "https://exemple.fr",
        "position_approximative": False,
        "latitude": 43.611,
        "longitude": 1.499,
        "lien": "https://cartedesartisans.fr/fiche.html?siret=22222222200022&mtm_campaign=homeassistant",
        "itineraire": "https://www.google.com/maps/dir/?api=1&destination=43.611,1.499",
    }
    assert "x@exemple.fr" not in json.dumps(dupont), "jamais l'e-mail"

    capitole = resultat_public(r[2], ENRICHIES, {})
    assert capitole["site"] == "", "javascript: rejeté"
    assert capitole["telephone"] == ""
    assert capitole["activite"] == "4322AZ", "code si le libellé manque"
    maitre = resultat_public(r[0], {}, INDEX["activites"])
    assert maitre["labels"] == ["Maître artisan"]

    # Enseigne identique au nom (casse près) : vide ; position approximative
    e = {**r[2], "enseigne": "Plomberie du Capitole", "precis": 0, "labels": ["rge", "epv", "ma"]}
    public = resultat_public(e, {}, {})
    assert public["enseigne"] == ""
    assert public["position_approximative"] is True
    assert public["labels"] == ["RGE", "Entreprise du patrimoine vivant", "Maître artisan"]


def test_liens() -> None:
    assert lien_fiche("11111111100011") == (
        "https://cartedesartisans.fr/fiche.html?siret=11111111100011&mtm_campaign=homeassistant"
    )
    commune = {"nom": "L'ISLE-JOURDAIN", "dep": "32", "cle": "l isle jourdain|32"}
    assert lien_carte("maison-depannage.plombier", commune) == (
        "https://cartedesartisans.fr/carte.html?mtm_campaign=homeassistant"
        "#rub=maison-depannage.plombier&ville=l%20isle%20jourdain|32"
    )
    assert lien_carte("a.b", None).endswith("#rub=a.b")
    assert lien_itineraire(43.6, 1.44) == "https://www.google.com/maps/dir/?api=1&destination=43.6,1.44"


async def test_rechercher() -> None:
    source = FausseSource()
    r = await rechercher(source, rubrique="maison-depannage.plombier", centre=(43.6046, 1.4441), rayon_km=10)
    assert r["etat"] == "ok"
    assert r["titre"] == "Plombier" and r["categorie"] == "Dépannage maison"
    assert r["rayon_km"] == 10
    assert r["commune"] == {"nom": "TOULOUSE", "dep": "31", "cle": "toulouse|31"}
    assert r["nombre"] == 3 == len(r["resultats"])
    assert r["resultats"][0]["nom"] == "ATELIER MAITRE"
    assert r["lien_carte"] == (
        "https://cartedesartisans.fr/carte.html?mtm_campaign=homeassistant"
        "#rub=maison-depannage.plombier&ville=toulouse|31"
    )
    assert r["genere"] == "2026-11-21"
    assert sorted(source.admin) == ["enrichies", "maitres"], "recommandes.js jamais lu"
    # La position de la maison n'apparaît dans aucun lien
    liens = [r["lien_carte"]] + [x["lien"] for x in r["resultats"]]
    assert not any(re.search(r"43\.604|1\.444", lien) for lien in liens)

    r = await rechercher(
        FausseSource(),
        rubrique="maison-depannage.electricien",
        centre=MAISON,
        rayon_km="25",
        labellises=True,
    )
    assert r["rayon_km"] == 25
    assert [x["nom"] for x in r["resultats"]] == ["ELEC TOULOUSAINE"]
    assert r["resultats"][0]["labels"] == ["Entreprise du patrimoine vivant"]

    r = await rechercher(FausseSource(), rubrique="maison-depannage.plombier", centre=MAISON, rayon_km=7)
    assert r["rayon_km"] == 10, "rayon inconnu : rayon par défaut"

    assert await rechercher(FausseSource(), rubrique="disparue", centre=MAISON, rayon_km=10) == {
        "etat": "rubrique-inconnue",
        "rubrique": "disparue",
    }


def test_rubriques() -> None:
    assert trouver_rubrique(INDEX, "maison-depannage.plombier") == "maison-depannage.plombier"
    assert trouver_rubrique(INDEX, "PLOMBIER") == "maison-depannage.plombier"
    assert trouver_rubrique(INDEX, " electricien ") == "maison-depannage.electricien"
    assert trouver_rubrique(INDEX, "Dépannage maison › Électricien") == "maison-depannage.electricien"
    assert trouver_rubrique(INDEX, "menuisier") is None
    assert trouver_rubrique(INDEX, "") is None
    assert options_rubriques(INDEX) == [
        {"value": "maison-depannage.electricien", "label": "Dépannage maison › Électricien"},
        {"value": "maison-depannage.plombier", "label": "Dépannage maison › Plombier"},
    ]
