# CLAUDE.md

Project rules for coding assistants (Claude Code reads this file) and for human
contributors.

## What this is

The **Carte des artisans** custom integration for Home Assistant (domain
`carte_des_artisans`): per config entry, two sensors (craftspeople count
within the radius, nearest craftsperson with the first 10 results as
attributes) and one action with a response,
`carte_des_artisans.chercher_artisan`. Data comes from the public files of
cartedesartisans.fr (`/donnees/export/`, plus `maitres-artisans.js` and
`enrichies.js`), read with Home Assistant's shared aiohttp session. No
third-party requirement (`requirements: []` in the manifest).

Distributed through the Home Assistant Marketplace / HACS (custom repository
first, then the `hacs/default` catalog: see `PUBLICATION.md`).

## Commands

Tests need Python 3.14 (the version Home Assistant 2026.10+ requires). Docker
is the simplest way on a machine without it:

```bash
docker run --rm -v "$PWD:/depot" -w /depot python:3.14 \
  sh -c "pip install -q -r requirements_test.txt && pytest"
pytest tests/test_recherche.py                  # one file (inside the container)
python .github/scripts/test_release.py         # release script, stdlib only, any Python 3.10+
```

The CI runs `validate.yaml` (HACS action, `category: integration`, no
`ignore`: the catalog rejects ignored checks), `hassfest.yaml` and
`tests.yaml` (release script tests, then `pytest`): keep all three green.

## Architecture

```
custom_components/carte_des_artisans/
  __init__.py        setup, action chercher_artisan (registered in async_setup)
  config_flow.py     config + options flows (trade, radius, certified, place)
  coordinator.py     DataUpdateCoordinator per entry, shared data source, repairs
  donnees.py         downloads the site files and keeps them in memory
  recherche.py       site rules: radius, ranking, public result shape, links
  sensor.py          the two sensors
  diagnostics.py     entry diagnostics, location redacted
  const.py           constants, config keys, VERSION_EXPORT
  manifest.json, services.yaml, icons.json, translations/{en,fr}.json
  brand/             icon.png, icon@2x.png, dark_icon.png, dark_icon@2x.png
brand-source/        SVG sources of the brand images (not shipped)
tests/               pytest-homeassistant-custom-component, fake site in tests/site/
hacs.json            Marketplace / HACS metadata
.github/scripts/     release.py (version bump, changelog) + test_release.py
```

## Rules

- **Stored ids are forever.** Home Assistant stores the domain, the config
  entry keys (`rubrique`, `rayon`, `labellises`, `suivre_maison`, `position`,
  see `CONF_*` in `const.py`), the sensor `unique_id`s
  (`<entry_id>_nombre`, `<entry_id>_plus_proche`) and translation keys, the
  action name `chercher_artisan` and its field names (used in users'
  automations and scripts), and the rubric keys `<catégorie>.<rubrique>`
  coming from the site. Never rename them; add a config entry migration
  (`async_migrate_entry`, bump `VERSION`/`MINOR_VERSION` of the flow) if a
  stored format must change. A rubric removed from the site raises a repair,
  it is never silently remapped.
- **Versions belong to the Release workflow** (Actions → Release). Never edit
  `version` in `manifest.json` by hand. Each release is a full GitHub Release
  (the catalog and the Marketplace need one, a tag is not enough).
- **Changelog.** Every user-visible change adds a line under `## [Unreleased]`
  in `CHANGELOG.md` (`### Added`, `Changed`, `Fixed`, `Removed`, `Security`).
  Never write a version heading: the Release workflow moves the section, and
  it becomes the notes of the GitHub Release.
- **Minimum Home Assistant version** is `homeassistant` in `hacs.json`
  (2026.3.0: first version reading the local `brand/` folder). Raise it when
  the code uses a newer API, and say so in the changelog.
- **Translations.** `translations/en.json` and `translations/fr.json` have
  exactly the same keys; `strings.json` is not used (custom integration).
  User-facing texts in `README.md` are French with a short English section:
  keep both in step.
- **Brand images**: PNG, square, transparent background, trimmed; 256 and
  512 px; light and `dark_` variants. Regenerate them from `brand-source/`
  (headless Edge or any SVG renderer), never use Home Assistant branding.
- **Style.** Code, comments and identifiers are in French (owner's
  convention, same as the website); English is fine in this file and the
  workflows. Tests never touch the network (fake site in `tests/site/`).
- **Site rules** (cartedesartisans.fr, `faq.html#classement`): certified
  businesses (RGE, EPV, Maître artisan) first, then the nearest. **No
  "Sponsorisé" block** in this integration. The site is independent: never
  present it as official or affiliated with Insee or the chambers of trade.
  Never expose the e-mail of `enrichies.js`. Links to the site carry
  `mtm_campaign=homeassistant`. Change these only with the site owner.
- **Privacy.** The home or chosen location never leaves Home Assistant: never
  in a request, a URL, a log line or the diagnostics. Only public site files
  are downloaded; only the departments within reach of the radius.
- **Shared logic.** `recherche.py` mirrors `integration-gladys/src/recherche.js`
  and `serveur-mcp/src/recherche.js` in the website project (radius,
  department reach, ranking, labels): change them together.
- **Export format.** `VERSION_EXPORT` in `const.py` must match `VERSION` in
  the website's `generer_export.py`: when the site bumps it, update the
  reading code and the constant together (and the Gladys and MCP twins).
