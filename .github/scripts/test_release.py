"""Tests de release.py (bibliothèque standard seulement).

python .github/scripts/test_release.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import release

RACINE = Path(__file__).resolve().parents[2]
DEPOT = "https://github.com/tlse-vins/ha-carte-des-artisans"

MANIFEST = """{
  "domain": "carte_des_artisans",
  "name": "Carte des artisans",
  "codeowners": ["@tlse-vins"],
  "requirements": [],
  "version": "1.0.0"
}
"""

CHANGELOG = """# Changelog

Intro qui cite ## [Unreleased] sans être un titre.

## [Unreleased]

### Added

- Nouveauté.

## [1.0.0] - 2026-11-22

### Added

- Première version.

[Unreleased]: https://github.com/tlse-vins/ha-carte-des-artisans/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/tlse-vins/ha-carte-des-artisans/releases/tag/v1.0.0
"""


class TestVersion(unittest.TestCase):
    def test_types(self) -> None:
        self.assertEqual(release.version_suivante("1.2.3", "patch"), "1.2.4")
        self.assertEqual(release.version_suivante("1.2.3", "minor"), "1.3.0")
        self.assertEqual(release.version_suivante("1.2.3", "major"), "2.0.0")
        self.assertEqual(release.version_suivante("0.9.9", "patch"), "0.9.10")

    def test_refus(self) -> None:
        with self.assertRaises(ValueError):
            release.version_suivante("1.2", "patch")
        with self.assertRaises(ValueError):
            release.version_suivante("1.2.3", "beta")


class TestManifest(unittest.TestCase):
    def test_seule_la_version_change(self) -> None:
        nouveau = release.changer_version_manifest(MANIFEST, "1.1.0")
        self.assertEqual(nouveau, MANIFEST.replace('"1.0.0"', '"1.1.0"'))

    def test_sans_version(self) -> None:
        with self.assertRaises(ValueError):
            release.changer_version_manifest('{"domain": "x"}', "1.0.0")


class TestChangelog(unittest.TestCase):
    def test_deplacement(self) -> None:
        nouveau = release.deplacer_changelog(CHANGELOG, "1.1.0", "2026-12-01", DEPOT)
        self.assertIn("## [Unreleased]\n\n## [1.1.0] - 2026-12-01\n\n### Added\n\n- Nouveauté.\n\n## [1.0.0]", nouveau)
        self.assertIn(f"[Unreleased]: {DEPOT}/compare/v1.1.0...HEAD\n", nouveau)
        self.assertIn(f"[1.1.0]: {DEPOT}/compare/v1.0.0...v1.1.0\n", nouveau)
        self.assertIn(f"[1.0.0]: {DEPOT}/releases/tag/v1.0.0\n", nouveau)
        self.assertIn("Intro qui cite ## [Unreleased] sans être un titre.", nouveau)
        # Relancer ne change rien
        self.assertEqual(release.deplacer_changelog(nouveau, "1.1.0", "2026-12-01", DEPOT), nouveau)

    def test_premiere_version_sans_liens(self) -> None:
        texte = "# Changelog\n\n## [Unreleased]\n\n### Added\n\n- Tout.\n"
        nouveau = release.deplacer_changelog(texte, "1.0.0", "2026-11-22", DEPOT)
        self.assertTrue(
            nouveau.startswith("# Changelog\n\n## [Unreleased]\n\n## [1.0.0] - 2026-11-22\n\n### Added\n\n- Tout.\n")
        )
        self.assertTrue(
            nouveau.endswith(f"[Unreleased]: {DEPOT}/compare/v1.0.0...HEAD\n[1.0.0]: {DEPOT}/releases/tag/v1.0.0\n")
        )

    def test_sans_unreleased(self) -> None:
        texte = "# Changelog\n"
        self.assertEqual(release.deplacer_changelog(texte, "1.0.0", "2026-11-22", DEPOT), texte)

    def test_notes(self) -> None:
        self.assertEqual(release.notes_version(CHANGELOG, "1.0.0"), "### Added\n\n- Première version.")
        self.assertEqual(release.notes_version(CHANGELOG, "9.9.9"), "")
        nouveau = release.deplacer_changelog(CHANGELOG, "1.1.0", "2026-12-01", DEPOT)
        self.assertEqual(release.notes_version(nouveau, "1.1.0"), "### Added\n\n- Nouveauté.")


class TestPreparer(unittest.TestCase):
    def test_fichiers(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            (racine / release.MANIFEST).parent.mkdir(parents=True)
            (racine / release.MANIFEST).write_text(MANIFEST, encoding="utf-8")
            (racine / release.CHANGELOG).write_text(CHANGELOG, encoding="utf-8")
            self.assertEqual(release.preparer("minor", DEPOT + "/", racine), "1.1.0")
            self.assertEqual(json.loads((racine / release.MANIFEST).read_text(encoding="utf-8"))["version"], "1.1.0")
            self.assertIn("## [1.1.0] - ", (racine / release.CHANGELOG).read_text(encoding="utf-8"))


class TestFichiersDuDepot(unittest.TestCase):
    """Le script doit fonctionner sur les vrais fichiers du dépôt."""

    def test_changelog_reel(self) -> None:
        texte = (RACINE / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertRegex(texte, r"(?m)^## \[Unreleased\][ \t]*$")
        nouveau = release.deplacer_changelog(texte, "99.0.0", "2026-12-01", DEPOT)
        self.assertNotEqual(nouveau, texte)

    def test_manifest_reel(self) -> None:
        chemin = RACINE / release.MANIFEST
        if not chemin.exists():
            self.skipTest("manifest pas encore écrit")
        texte = chemin.read_text(encoding="utf-8")
        version = json.loads(texte)["version"]
        self.assertRegex(version, release.SEMVER)
        suivante = release.version_suivante(version, "patch")
        self.assertEqual(json.loads(release.changer_version_manifest(texte, suivante))["version"], suivante)

    def test_preparer_sur_une_copie(self) -> None:
        if not (RACINE / release.MANIFEST).exists():
            self.skipTest("manifest pas encore écrit")
        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            (racine / release.MANIFEST).parent.mkdir(parents=True)
            shutil.copy(RACINE / release.MANIFEST, racine / release.MANIFEST)
            shutil.copy(RACINE / "CHANGELOG.md", racine / release.CHANGELOG)
            version = release.preparer("patch", DEPOT, racine)
            manifest = json.loads((racine / release.MANIFEST).read_text(encoding="utf-8"))
            self.assertEqual(manifest["version"], version)
            changelog = (racine / release.CHANGELOG).read_text(encoding="utf-8")
            self.assertIn(f"## [{version}] - ", changelog)


if __name__ == "__main__":
    unittest.main()
