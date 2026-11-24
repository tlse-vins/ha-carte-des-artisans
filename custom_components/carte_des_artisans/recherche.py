"""Recherche d'artisans autour d'un point, avec les règles de la Carte des artisans.

Portage en Python de ``integration-gladys/src/recherche.js``, ``geo.js`` et
``service.js`` (sans Home Assistant ni aiohttp : module pur, testable seul).

Règles reprises du site :
  - résultats : établissements de la rubrique dans le rayon, labellisés
    (RGE, EPV, Maître artisan) d'abord, puis du plus proche au plus loin ;
  - aucun bloc « Sponsorisé » (décision du propriétaire pour Home Assistant :
    ``recommandes.js`` n'est jamais lu) ;
  - la position de la maison ne quitte jamais Home Assistant : les distances
    sont calculées ici et le lien vers la carte ne cite que la commune la plus
    proche ;
  - l'e-mail des fiches enrichies n'est jamais exposé.
"""

from __future__ import annotations

import asyncio
import math
import re
import unicodedata
from collections.abc import Awaitable, Callable, Iterable
from typing import Any, Protocol
from urllib.parse import quote

from .const import CAMPAGNE, RAYON_DEFAUT, RAYONS, SITE

RAYON_TERRE_KM = 6371
# Lectures simultanées de fichiers de l'export, comme Gladys
PARALLELE = 6

Point = tuple[float, float]

NOMS_LABELS = {
    "rge": "RGE",
    "epv": "Entreprise du patrimoine vivant",
    "ma": "Maître artisan",
}

_PETITS_MOTS = {
    "de",
    "du",
    "des",
    "la",
    "le",
    "les",
    "sur",
    "sous",
    "en",
    "et",
    "aux",
    "au",
    "lès",
}
# Équivalent de /(^|[\s'-])(\p{L}+)/gu : un mot de lettres précédé d'un séparateur
_MOT = re.compile(r"(^|[\s'-])([^\W\d_]+)")
_HTTPS = re.compile(r"^https://\S+$", re.IGNORECASE)


class Source(Protocol):
    """Ce que ``rechercher`` attend de la source de données (voir donnees.py)."""

    async def index(self) -> dict: ...

    async def lignes(self, index: dict, dep: str, code: str) -> list: ...

    async def communes(self, index: dict) -> list: ...

    async def fichier_admin(self, cle: str) -> dict: ...


# --- Distances ---------------------------------------------------------------


def distance_km(a: Point, b: Point) -> float:
    """Distance à vol d'oiseau entre deux points (lat, lon), en km."""
    d_lat = math.radians(b[0] - a[0])
    d_lon = math.radians(b[1] - a[1])
    h = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(a[0])) * math.cos(math.radians(b[0])) * math.sin(d_lon / 2) ** 2
    )
    return 2 * RAYON_TERRE_KM * math.asin(min(1.0, math.sqrt(h)))


def distance_emprise(point: Point, emprise: list[float]) -> float:
    """Distance du point au rectangle [latMin, lonMin, latMax, lonMax] (0 s'il est dedans)."""
    lat_min, lon_min, lat_max, lon_max = emprise
    proche = (
        min(max(point[0], lat_min), lat_max),
        min(max(point[1], lon_min), lon_max),
    )
    return distance_km(point, proche)


def _arrondi(x: float) -> int:
    # Math.round de JavaScript (0,5 vers le haut), pas l'arrondi bancaire de Python
    return math.floor(x + 0.5)


def formater_distance(km: float) -> str:
    """« 850 m », « 2,4 km », « 12 km »."""
    if km < 1:
        return f"{max(100, _arrondi(km * 1000 / 50) * 50)} m"
    if km < 10:
        return f"{_arrondi(km * 10) / 10:.1f}".replace(".", ",") + " km"
    return f"{_arrondi(km)} km"


# --- Textes et communes --------------------------------------------------------


def _sans_accents(texte: str) -> str:
    decompose = unicodedata.normalize("NFD", texte)
    return "".join(c for c in decompose if not 0x300 <= ord(c) <= 0x36F)


def _normaliser(texte: str) -> str:
    """Comparaison souple : minuscules, sans accents, espaces réduits."""
    return " ".join(_sans_accents(str(texte).lower()).split())


def titre(texte: Any) -> str:
    """« SAINT-ETIENNE-DU-ROUVRAY » → « Saint-Etienne-du-Rouvray » (comme titre() du site)."""

    def remplacer(m: re.Match[str]) -> str:
        sep, mot = m.group(1), m.group(2)
        if sep and mot in _PETITS_MOTS:
            return sep + mot
        return sep + mot[0].upper() + mot[1:]

    return _MOT.sub(remplacer, str(texte if texte is not None else "").lower())


def cle_commune(nom: str, dep: str) -> str:
    """Clé de commune du site : minuscules, sans accents, « - » et « ' » remplacés par des espaces."""
    n = re.sub(r"[-']", " ", _sans_accents(str(nom).lower()))
    return f"{n}|{dep}"


def commune_proche(communes: Iterable[list], point: Point) -> dict | None:
    """Commune dont le centre est le plus proche du point : {nom, dep, cle}."""
    meilleure: dict | None = None
    minimum = math.inf
    for nom, dep, lat, lon in communes:
        # Préfiltre grossier (≈ 50 km) avant le calcul exact
        if abs(lat - point[0]) > 0.5 or abs(lon - point[1]) > 0.7:
            continue
        d = distance_km(point, (lat, lon))
        if d < minimum:
            minimum = d
            meilleure = {"nom": nom, "dep": dep, "cle": cle_commune(nom, dep)}
    return meilleure


# --- Liens vers le site --------------------------------------------------------


def _encoder(texte: str) -> str:
    # Même résultat que encodeURIComponent de JavaScript
    return quote(texte, safe="-_.!~*'()")


def lien_fiche(siret: str) -> str:
    """Fiche du site ; la campagne distingue ces visites dans la mesure d'audience."""
    return f"{SITE}/fiche.html?siret={siret}&mtm_campaign={CAMPAGNE}"


def lien_carte(rubrique: str, commune: dict | None) -> str:
    """Carte du site pour la rubrique et la commune (jamais la position de la maison)."""
    ville = f"&ville={_encoder(commune['cle']).replace('%7C', '|')}" if commune else ""
    return f"{SITE}/carte.html?mtm_campaign={CAMPAGNE}#rub={_encoder(rubrique)}{ville}"


def lien_itineraire(lat: float, lon: float) -> str:
    """Itinéraire vers l'établissement (sa position, publique ; pas celle de la maison)."""
    return f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}"


# --- Recherche -----------------------------------------------------------------


async def chercher(
    *,
    index: dict,
    lire: Callable[[str, str], Awaitable[list[list]]],
    centre: Point,
    rayon_km: float,
    codes: Iterable[str],
    labellises_seulement: bool = False,
    maitres: dict | None = None,
) -> list[dict]:
    """Établissements des activités ``codes`` dans le rayon, labellisés d'abord puis par distance."""
    maitres = maitres or {}
    champs = {c: i for i, c in enumerate(index["champs"])}
    codes = list(codes)
    # Seuls les départements dont l'emprise touche le cercle sont lus
    fichiers: list[tuple[str, str]] = []
    for dep, info in index["departements"].items():
        if distance_emprise(centre, info["emprise"]) > rayon_km:
            continue
        for code in codes:
            if info["activites"].get(code):
                fichiers.append((dep, code))

    lus: list[tuple[str, str, list]] = []
    for i in range(0, len(fichiers), PARALLELE):
        lot = fichiers[i : i + PARALLELE]
        lignes = await asyncio.gather(*(lire(dep, code) for dep, code in lot))
        lus.extend((dep, code, liste) for (dep, code), liste in zip(lot, lignes, strict=True))

    resultats: list[dict] = []
    for dep, code, lignes in lus:
        for ligne in lignes:
            lat, lon = ligne[champs["lat"]], ligne[champs["lon"]]
            distance = distance_km(centre, (lat, lon))
            if distance > rayon_km:
                continue
            siret = ligne[champs["siret"]]
            lab = ligne[champs["labels"]] or ""
            labels = (
                (["rge"] if "r" in lab else []) + (["epv"] if "e" in lab else []) + (["ma"] if siret in maitres else [])
            )
            if labellises_seulement and not labels:
                continue
            resultats.append(
                {
                    "siret": siret,
                    "nom": ligne[champs["nom"]],
                    "enseigne": ligne[champs["enseigne"]],
                    "adresse": ligne[champs["adresse"]],
                    "cp": ligne[champs["cp"]],
                    "commune": ligne[champs["commune"]],
                    "dep": dep,
                    "activite": code,
                    "lat": lat,
                    "lon": lon,
                    "precis": ligne[champs["precis"]],
                    "labels": labels,
                    "distance": distance,
                }
            )
    # Tri stable : labellisés d'abord, puis du plus proche au plus loin
    resultats.sort(key=lambda e: (not e["labels"], e["distance"]))
    return resultats


def _https(url: Any) -> str:
    return url if isinstance(url, str) and _HTTPS.match(url) else ""


def resultat_public(e: dict, enrichies: dict, activites: dict) -> dict:
    """Forme exposée à Home Assistant (attributs du capteur, réponse de l'action) ; jamais l'e-mail."""
    fiche = enrichies.get(e["siret"]) or {}
    nom = e["nom"] or ""
    enseigne = e["enseigne"] or ""
    if enseigne.lower() == nom.lower():
        enseigne = ""
    telephone = fiche.get("telephone")
    return {
        "nom": nom,
        "enseigne": enseigne,
        "activite": activites.get(e["activite"]) or e["activite"],
        "adresse": f"{titre(e['adresse'])}, {e['cp']} {titre(e['commune'])}",
        "commune": titre(e["commune"]),
        "distance_km": round(e["distance"], 1),
        "distance": formater_distance(e["distance"]),
        "labels": [NOMS_LABELS[cle] for cle in e["labels"]],
        "telephone": telephone if isinstance(telephone, str) else "",
        "site": _https(fiche.get("site")),
        "position_approximative": e["precis"] == 0,
        "latitude": e["lat"],
        "longitude": e["lon"],
        "lien": lien_fiche(e["siret"]),
        "itineraire": lien_itineraire(e["lat"], e["lon"]),
    }


def rayon_valide(valeur: Any) -> int:
    """Rayon accepté (nombre ou chaîne) ; sinon le rayon par défaut."""
    try:
        n = float(valeur)
    except (TypeError, ValueError):
        return RAYON_DEFAUT
    return int(n) if n in RAYONS else RAYON_DEFAUT


async def rechercher(
    source: Source,
    *,
    rubrique: str,
    centre: Point,
    rayon_km: Any,
    labellises: bool = False,
) -> dict:
    """Recherche complète autour de ``centre`` pour une rubrique de l'export."""
    index = await source.index()
    rub = index["rubriques"].get(rubrique)
    if not rub:
        return {"etat": "rubrique-inconnue", "rubrique": rubrique}
    rayon = rayon_valide(rayon_km)
    maitres, enrichies, communes = await asyncio.gather(
        source.fichier_admin("maitres"),
        source.fichier_admin("enrichies"),
        source.communes(index),
    )
    bruts = await chercher(
        index=index,
        lire=lambda dep, code: source.lignes(index, dep, code),
        centre=centre,
        rayon_km=rayon,
        codes=rub["codes"],
        labellises_seulement=labellises,
        maitres=maitres,
    )
    commune = commune_proche(communes, centre)
    activites = index.get("activites", {})
    return {
        "etat": "ok",
        "rubrique": rubrique,
        "titre": rub["titre"],
        "categorie": rub.get("categorie", ""),
        "rayon_km": rayon,
        "commune": commune,
        "nombre": len(bruts),
        "resultats": [resultat_public(e, enrichies, activites) for e in bruts],
        "lien_carte": lien_carte(rubrique, commune),
        "genere": index.get("genere"),
    }


# --- Rubriques -----------------------------------------------------------------


def _libelle(rub: dict) -> str:
    return f"{rub.get('categorie', '')} › {rub['titre']}"


def options_rubriques(index: dict) -> list[dict]:
    """Choix du formulaire : [{value: clé, label: « Catégorie › Titre »}], triés."""
    rubriques = sorted(
        index["rubriques"].items(),
        key=lambda kv: (_normaliser(kv[1].get("categorie", "")), _normaliser(kv[1]["titre"]), kv[0]),
    )
    return [{"value": cle, "label": _libelle(rub)} for cle, rub in rubriques]


def trouver_rubrique(index: dict, texte: str) -> str | None:
    """Clé exacte, ou titre (ou « Catégorie › Titre ») sans tenir compte de la casse ni des accents."""
    if not isinstance(texte, str):
        return None
    rubriques = index["rubriques"]
    if texte in rubriques:
        return texte
    voulu = _normaliser(texte)
    if not voulu:
        return None
    for option in options_rubriques(index):
        rub = rubriques[option["value"]]
        if voulu in (_normaliser(rub["titre"]), _normaliser(option["label"]), _normaliser(option["value"])):
            return option["value"]
    return None
