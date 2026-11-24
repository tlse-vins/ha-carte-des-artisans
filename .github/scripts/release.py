"""Outils de publication, lancés par les workflows Release et GitHub releases.

    python .github/scripts/release.py prepare <patch|minor|major> <url-du-dépôt>
        Calcule la version suivante depuis le manifest de l'intégration,
        l'y écrit, déplace la section `## [Unreleased]` de CHANGELOG.md sous
        `## [<version>] - <date du jour>` et affiche la nouvelle version.

    python .github/scripts/release.py notes <x.y.z> < CHANGELOG.md
        Affiche la section du changelog de cette version (rien s'il n'y en a
        pas) : le texte de sa GitHub Release.

Les deux fichiers sont modifiés sur place, sans être réécrits (json.dump...),
pour que le commit de publication ne change que la version. Aucune dépendance
hors de la bibliothèque standard ; testé par .github/scripts/test_release.py.
"""

from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path

MANIFEST = Path("custom_components/carte_des_artisans/manifest.json")
CHANGELOG = Path("CHANGELOG.md")
TITRE_UNRELEASED = "## [Unreleased]"
TYPES = ("patch", "minor", "major")
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def version_suivante(actuelle: str, type_: str) -> str:
    """Version sémantique suivante : 1.2.3 + minor -> 1.3.0."""
    trouve = SEMVER.match(actuelle)
    if not trouve:
        raise ValueError(f"version non sémantique dans le manifest : {actuelle!r}")
    if type_ not in TYPES:
        raise ValueError(f"type de version inconnu : {type_!r} ({', '.join(TYPES)})")
    majeure, mineure, correctif = (int(n) for n in trouve.groups())
    if type_ == "major":
        return f"{majeure + 1}.0.0"
    if type_ == "minor":
        return f"{majeure}.{mineure + 1}.0"
    return f"{majeure}.{mineure}.{correctif + 1}"


def changer_version_manifest(texte: str, version: str) -> str:
    """Remplace la valeur de `version` du manifest, sans toucher au reste."""
    manifest = json.loads(texte)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("version"), str):
        raise ValueError(f'{MANIFEST} : pas de clé "version" (texte) à modifier')
    motif = re.compile(r'("version"\s*:\s*)"[^"]*"')
    # La clé `version` n'existe qu'au premier niveau d'un manifest d'intégration
    if len(motif.findall(texte)) != 1:
        raise ValueError(f'{MANIFEST} : clé "version" absente ou en double')
    resultat = motif.sub(lambda m: m.group(1) + json.dumps(version), texte)
    attendu = {**manifest, "version": version}
    if json.loads(resultat) != attendu:
        raise AssertionError("le manifest a changé au-delà de la version")
    return resultat


def _titre_version(version: str) -> re.Pattern[str]:
    """Ligne de titre d'une version : `## [1.2.0] - 2026-01-02` (ou `## 1.2.0`)."""
    return re.compile(rf"^## \[?{re.escape(version)}\]?(?: |$).*$", re.MULTILINE)


def _fin_section(texte: str, debut: int) -> int:
    """Fin d'une section : titre `## ` suivant, sinon liens de fin, sinon fin du texte."""
    reste = texte[debut:]
    titre = re.search(r"^## ", reste, re.MULTILINE)
    if titre:
        return debut + titre.start()
    liens = re.search(r"^\[[^\]]+\]: ", reste, re.MULTILINE)
    return debut + liens.start() if liens else len(texte)


def deplacer_changelog(texte: str, version: str, date: str, url_depot: str) -> str:
    """Déplace la section Unreleased sous la version et met à jour les liens.

    Texte inchangé s'il n'y a pas de section Unreleased ou si la version est
    déjà listée.
    """
    titre = re.search(r"^## \[Unreleased\][ \t]*$", texte, re.MULTILINE)
    if not titre or _titre_version(version).search(texte):
        return texte
    debut_corps = titre.end()
    fin_corps = _fin_section(texte, debut_corps)
    corps = texte[debut_corps:fin_corps].strip()
    reste = texte[fin_corps:].lstrip()

    publiee = f"## [{version}] - {date}\n\n" + (f"{corps}\n\n" if corps else "")
    resultat = f"{texte[: titre.start()]}{TITRE_UNRELEASED}\n\n{publiee}{reste}"

    # Liens : [Unreleased] compare depuis la nouvelle étiquette ; la nouvelle
    # version compare avec la précédente, ou pointe vers son étiquette
    precedente = re.search(r"^## \[(\d+\.\d+\.\d+)\]", reste, re.MULTILINE)
    liens = f"[Unreleased]: {url_depot}/compare/v{version}...HEAD\n" + (
        f"[{version}]: {url_depot}/compare/v{precedente.group(1)}...v{version}"
        if precedente
        else f"[{version}]: {url_depot}/releases/tag/v{version}"
    )
    lien_unreleased = re.compile(r"^\[Unreleased\]: .*$", re.MULTILINE)
    if lien_unreleased.search(resultat):
        resultat = lien_unreleased.sub(lambda _m: liens, resultat, count=1)
    else:
        resultat = f"{resultat.rstrip()}\n\n{liens}"
    return resultat.rstrip() + "\n"


def notes_version(texte: str, version: str) -> str:
    """Corps de la section d'une version du changelog (vide s'il n'y en a pas)."""
    titre = _titre_version(version).search(texte)
    if not titre:
        return ""
    return texte[titre.end() : _fin_section(texte, titre.end())].strip()


def preparer(type_: str, url_depot: str, racine: Path = Path(".")) -> str:
    """Écrit la nouvelle version dans le manifest et le changelog ; la renvoie."""
    chemin_manifest = racine / MANIFEST
    texte = chemin_manifest.read_text(encoding="utf-8")
    version = version_suivante(json.loads(texte)["version"], type_)
    chemin_manifest.write_text(changer_version_manifest(texte, version), encoding="utf-8", newline="")

    chemin_changelog = racine / CHANGELOG
    if chemin_changelog.exists():
        ancien = chemin_changelog.read_text(encoding="utf-8")
        date = datetime.date.today().isoformat()
        nouveau = deplacer_changelog(ancien, version, date, url_depot.rstrip("/"))
        if nouveau == ancien:
            print(
                f'::warning::{CHANGELOG} inchangé : pas de section "{TITRE_UNRELEASED}", ou {version} déjà listée',
                file=sys.stderr,
            )
        chemin_changelog.write_text(nouveau, encoding="utf-8", newline="")
    return version


def main(arguments: list[str]) -> int:
    """Point d'entrée en ligne de commande."""
    if len(arguments) == 3 and arguments[0] == "prepare" and arguments[1] in TYPES:
        print(preparer(arguments[1], arguments[2]))
        return 0
    if len(arguments) == 2 and arguments[0] == "notes" and SEMVER.match(arguments[1]):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(notes_version(sys.stdin.buffer.read().decode("utf-8"), arguments[1]))
        return 0
    print("Usage : release.py prepare <patch|minor|major> <url-du-dépôt>", file=sys.stderr)
    print("        release.py notes <x.y.z> < CHANGELOG.md", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
