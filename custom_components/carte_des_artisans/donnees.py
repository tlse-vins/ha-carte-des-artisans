"""Lecture des données publiques de la Carte des artisans (cartedesartisans.fr).

Portage en Python de ``integration-gladys/src/donnees.js``. Deux familles de
fichiers :
  - l'export mensuel (``donnees/export/``) : ``index.json``, ``communes.json``
    et un fichier par département × activité. Il ne change qu'une fois par
    mois : gardé en mémoire (300 fichiers au plus, les moins utilisés partent
    d'abord) et sur le disque (``dossier_cache`` : ``index.json`` + un
    sous-dossier par valeur de ``genere``, les anciens mois purgés), relu
    seulement quand ``index.json`` annonce de nouvelles données ;
  - les petits fichiers de l'espace d'administration (``maitres-artisans.js``,
    ``enrichies.js``), qui changent plus souvent : relus toutes les 6 heures.
    ``recommandes.js`` n'est jamais lu (pas de bloc « Sponsorisé » ici).

Rien d'autre n'est envoyé au site que ces lectures (aucune position, aucun
identifiant) ; en cas d'erreur réseau, la dernière copie connue est gardée.
Les accès disque passent par ``executer`` (``hass.async_add_executor_job``
dans Home Assistant) pour ne jamais bloquer la boucle d'événements.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import shutil
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp

from .const import AGENT, DELAI_ADMIN, DELAI_INDEX, SITE, VERSION_EXPORT

_LOGGER = logging.getLogger(__name__)

MAX_FICHIERS_MEMOIRE = 300
DELAI_RESEAU = aiohttp.ClientTimeout(total=30)

# Fichiers de l'admin : clé → (fichier, variable globale lue, valeur par défaut)
FICHIERS_ADMIN: dict[str, tuple[str, str, dict]] = {
    "maitres": ("maitres-artisans.js", "MAITRES_ARTISANS", {}),
    "enrichies": ("enrichies.js", "ENRICHIES", {}),
}

Executer = Callable[..., Awaitable[Any]]


class DonneesIndisponibles(Exception):
    """Site injoignable (ou réponse illisible) et aucune copie connue."""


class FormatNonPrisEnCharge(DonneesIndisponibles):
    """Le site publie un format d'export que cette version ne sait pas lire."""


class _ErreurLecture(Exception):
    """Erreur d'un téléchargement (réseau, HTTP, contenu illisible)."""


def lire_variable(texte: str, nom: str) -> Any:
    """Valeur JSON affectée à ``window.<nom>`` dans un fichier .js du site (une affectation par ligne)."""
    debut = f"window.{nom} ="
    for ligne in texte.splitlines():
        if ligne.startswith(debut):
            valeur = ligne[ligne.index("=") + 1 :].strip()
            return json.loads(re.sub(r";\s*$", "", valeur))
    raise ValueError(f"window.{nom} introuvable")


async def _dans_un_fil(fonction: Callable[..., Any], *args: Any) -> Any:
    return await asyncio.to_thread(fonction, *args)


# --- Accès disque (exécutés hors de la boucle) ---------------------------------


def _lire_json(fichier: str) -> Any:
    try:
        with open(fichier, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _ecrire_json(fichier: str, donnees: Any) -> None:
    os.makedirs(os.path.dirname(fichier), exist_ok=True)
    temporaire = f"{fichier}.tmp"
    with open(temporaire, "w", encoding="utf-8") as f:
        json.dump(donnees, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(temporaire, fichier)


def _purger(dossier: str, garder: str) -> None:
    try:
        noms = os.listdir(dossier)
    except OSError:
        return  # dossier absent : rien à purger
    for nom in noms:
        if nom in (garder, "index.json"):
            continue
        chemin = os.path.join(dossier, nom)
        if os.path.isdir(chemin):
            shutil.rmtree(chemin, ignore_errors=True)
        else:
            with contextlib.suppress(OSError):
                os.remove(chemin)


class SourceDonnees:
    """Accès aux fichiers du site, avec caches mémoire et disque."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        dossier_cache: str | None,
        *,
        site: str = SITE,
        executer: Executer | None = None,
        maintenant: Callable[[], float] = time.time,
    ) -> None:
        self.session = session
        self.dossier_cache = dossier_cache
        self.site = site.rstrip("/")
        self.executer: Executer = executer or _dans_un_fil
        self.maintenant = maintenant
        self._index: dict | None = None
        self._index_lu = 0.0
        self._fichiers: OrderedDict[str, Any] = OrderedDict()
        self._admin: dict[str, tuple[Any, float]] = {}

    # --- Réseau ---

    async def _telecharger(self, chemin: str, *, texte: bool = False) -> Any:
        """Contenu d'un fichier du site ; None si absent (404)."""
        url = f"{self.site}/{chemin}"
        entetes = {"User-Agent": AGENT, "Accept": "*/*" if texte else "application/json"}
        try:
            async with self.session.get(url, headers=entetes, timeout=DELAI_RESEAU) as reponse:
                if reponse.status == 404:
                    return None
                if reponse.status >= 400:
                    raise _ErreurLecture(f"{chemin} : HTTP {reponse.status}")
                if texte:
                    return await reponse.text()
                return await reponse.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise _ErreurLecture(f"{chemin} : {err!r}") from err

    # --- Disque (best effort : un disque plein ou en lecture seule ne bloque rien) ---

    async def _lire_disque(self, nom: str) -> Any:
        if not self.dossier_cache:
            return None
        return await self.executer(_lire_json, os.path.join(self.dossier_cache, nom))

    async def _ecrire_disque(self, nom: str, donnees: Any) -> None:
        if not self.dossier_cache:
            return
        try:
            await self.executer(_ecrire_json, os.path.join(self.dossier_cache, nom), donnees)
        except OSError as err:
            _LOGGER.debug("Cache disque indisponible (%s)", err)

    async def _purger_disque(self, garder: str) -> None:
        if self.dossier_cache:
            await self.executer(_purger, self.dossier_cache, garder)

    @staticmethod
    def _dossier_donnees(index: dict) -> str:
        return re.sub(r"[^0-9A-Za-z-]", "_", str(index.get("genere")))

    # --- Export mensuel ---

    async def index(self) -> dict:
        """index.json de l'export (relu au plus toutes les DELAI_INDEX secondes)."""
        if self._index is not None and self.maintenant() - self._index_lu < DELAI_INDEX:
            return self._index
        index: Any = None
        format_inconnu = False
        try:
            index = await self._telecharger("donnees/export/index.json")
        except _ErreurLecture as err:
            _LOGGER.warning("index.json illisible, dernière copie gardée (%s)", err)
        if index is not None and (not isinstance(index, dict) or index.get("version") != VERSION_EXPORT):
            version = index.get("version") if isinstance(index, dict) else None
            _LOGGER.error("Format d'export %s non pris en charge : mettez à jour l'intégration", version)
            format_inconnu = True
            index = None
        if index is not None:
            if self._index is None or self._index.get("genere") != index.get("genere"):
                self._fichiers.clear()
                await self._ecrire_disque("index.json", index)
                await self._purger_disque(self._dossier_donnees(index))
        else:
            index = self._index
            if index is None:
                copie = await self._lire_disque("index.json")
                if isinstance(copie, dict) and copie.get("version") == VERSION_EXPORT:
                    index = copie
            if index is None:
                if format_inconnu:
                    raise FormatNonPrisEnCharge("Format des données de la Carte des artisans non pris en charge")
                raise DonneesIndisponibles("Données de la Carte des artisans indisponibles")
        self._index = index
        self._index_lu = self.maintenant()
        return index

    async def _fichier_export(self, index: dict, relatif: str, defaut: Any) -> Any:
        """Fichier de l'export du mois courant (mémoire, puis disque, puis réseau)."""
        nom = f"{self._dossier_donnees(index)}/{relatif}"
        if nom in self._fichiers:
            self._fichiers.move_to_end(nom)
            return self._fichiers[nom]
        valeur = await self._lire_disque(nom)
        if valeur is None:
            try:
                valeur = await self._telecharger(f"donnees/export/{relatif}")
            except _ErreurLecture as err:
                raise DonneesIndisponibles(f"Fichier {relatif} indisponible ({err})") from err
            if valeur is None:
                valeur = defaut
            await self._ecrire_disque(nom, valeur)
        self._fichiers[nom] = valeur
        while len(self._fichiers) > MAX_FICHIERS_MEMOIRE:
            self._fichiers.popitem(last=False)
        return valeur

    async def lignes(self, index: dict, dep: str, code: str) -> list:
        """Établissements d'une activité dans un département (lignes de index["champs"])."""
        return await self._fichier_export(index, f"{dep}/{code}.json", [])

    async def communes(self, index: dict) -> list:
        """[[NOM, dep, lat, lon], ...] : position moyenne des établissements de chaque commune."""
        return await self._fichier_export(index, "communes.json", [])

    # --- Fichiers de l'admin ---

    async def fichier_admin(self, cle: str) -> dict:
        """maitres / enrichies, relus au plus toutes les DELAI_ADMIN secondes."""
        fichier, variable, defaut = FICHIERS_ADMIN[cle]
        actuel = self._admin.get(cle)
        if actuel is not None and self.maintenant() - actuel[1] < DELAI_ADMIN:
            return actuel[0]
        valeur = actuel[0] if actuel is not None else dict(defaut)
        try:
            texte = await self._telecharger(f"donnees/{fichier}", texte=True)
            if texte is None:
                valeur = dict(defaut)
            else:
                lu = lire_variable(texte, variable)
                if not isinstance(lu, dict):
                    raise ValueError(f"window.{variable} n'est pas un objet")
                valeur = lu
        except (_ErreurLecture, ValueError) as err:
            _LOGGER.warning("%s illisible, dernière copie gardée (%s)", fichier, err)
        self._admin[cle] = (valeur, self.maintenant())
        return valeur
