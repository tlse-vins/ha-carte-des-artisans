"""Configuration et options d'une entrée Carte des artisans.

Une entrée = un métier (rubrique du site) autour de la maison ou d'un lieu
choisi. La rubrique est gardée dans ``data`` (fixe) ; rayon, labellisés,
suivi de la maison et lieu dans ``options`` (modifiables). Identifiant
unique : rubrique + « maison » ou position arrondie à 3 décimales (≈ 100 m).
"""

from __future__ import annotations

from typing import Any, override

try:
    import probatio
except ImportError:  # Home Assistant antérieur au passage à probatio
    import voluptuous as probatio

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    LocationSelector,
    LocationSelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_LABELLISES,
    CONF_POSITION,
    CONF_RAYON,
    CONF_RUBRIQUE,
    CONF_SUIVRE_MAISON,
    CONF_TITRE,
    DOMAIN,
    RAYON_DEFAUT,
    RAYONS,
)
from .coordinator import obtenir_source, position_maison
from .donnees import DonneesIndisponibles
from .recherche import options_rubriques

# Centre de la France : lieu proposé quand la maison n'est pas localisée
CENTRE_FRANCE = {"latitude": 46.6, "longitude": 2.4}

SELECTEUR_RAYON = SelectSelector(
    SelectSelectorConfig(
        options=[str(r) for r in RAYONS],
        mode=SelectSelectorMode.DROPDOWN,
        translation_key=CONF_RAYON,
    )
)
SELECTEUR_LIEU = LocationSelector(LocationSelectorConfig(radius=False))


def titre_entree(hass: HomeAssistant, titre: str, options: dict[str, Any]) -> str:
    """« Plombier · 10 km », suivi de « · lieu choisi » si ce n'est pas la maison."""
    texte = f"{titre} · {options[CONF_RAYON]} km"
    if not options[CONF_SUIVRE_MAISON]:
        lieu = "lieu choisi" if (hass.config.language or "").startswith("fr") else "custom location"
        texte += f" · {lieu}"
    return texte


def id_unique(rubrique: str, options: dict[str, Any]) -> str:
    """Rubrique + « maison » ou position arrondie (un même métier par lieu)."""
    if options[CONF_SUIVRE_MAISON]:
        return f"{rubrique}|maison"
    position = options[CONF_POSITION]
    return f"{rubrique}|{position['latitude']:.3f},{position['longitude']:.3f}"


def schema_reglages(defauts: dict[str, Any]) -> probatio.Schema:
    """Rayon, labellisés seulement, suivre la maison."""
    return probatio.Schema(
        {
            probatio.Required(CONF_RAYON, default=str(defauts.get(CONF_RAYON, RAYON_DEFAUT))): SELECTEUR_RAYON,
            probatio.Required(CONF_LABELLISES, default=defauts.get(CONF_LABELLISES, False)): BooleanSelector(),
            probatio.Required(CONF_SUIVRE_MAISON, default=defauts.get(CONF_SUIVRE_MAISON, True)): BooleanSelector(),
        }
    )


def schema_position(defaut: dict[str, float]) -> probatio.Schema:
    """Lieu de recherche choisi sur la carte."""
    return probatio.Schema(
        {
            probatio.Required(
                CONF_POSITION,
                default={"latitude": defaut["latitude"], "longitude": defaut["longitude"]},
            ): SELECTEUR_LIEU
        }
    )


def position_par_defaut(hass: HomeAssistant, actuelle: dict[str, float] | None = None) -> dict[str, float]:
    """Lieu proposé : l'actuel, sinon la maison, sinon le centre de la France."""
    if actuelle:
        return actuelle
    if (maison := position_maison(hass)) is not None:
        return {"latitude": maison[0], "longitude": maison[1]}
    return CENTRE_FRANCE


def normaliser_reglages(saisie: dict[str, Any]) -> dict[str, Any]:
    """Rayon en entier, booléens explicites."""
    return {
        CONF_RAYON: int(saisie[CONF_RAYON]),
        CONF_LABELLISES: bool(saisie[CONF_LABELLISES]),
        CONF_SUIVRE_MAISON: bool(saisie[CONF_SUIVRE_MAISON]),
    }


def normaliser_position(position: dict[str, Any]) -> dict[str, float]:
    """Seulement latitude et longitude (pas de rayon)."""
    return {"latitude": float(position["latitude"]), "longitude": float(position["longitude"])}


class CarteDesArtisansConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ajout d'un métier à suivre."""

    VERSION = 1

    def __init__(self) -> None:
        """État du parcours."""
        self._rubriques: dict[str, str] = {}
        self._titres: dict[str, str] = {}
        self._rubrique: str | None = None
        self._options: dict[str, Any] = {}

    @staticmethod
    @callback
    @override
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsCarteDesArtisans:
        """Options de l'entrée."""
        return OptionsCarteDesArtisans()

    @override
    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Métier, rayon, labellisés, maison ou lieu choisi."""
        if not self._rubriques:
            try:
                index = await obtenir_source(self.hass).index()
            except DonneesIndisponibles:
                return self.async_abort(reason="cannot_connect")
            # Libellé « Catégorie › Titre » pour le formulaire, titre seul pour l'entrée
            self._rubriques = {o["value"]: o["label"] for o in options_rubriques(index)}
            self._titres = {cle: rub["titre"] for cle, rub in index["rubriques"].items()}

        errors: dict[str, str] = {}
        if user_input is not None:
            self._rubrique = user_input[CONF_RUBRIQUE]
            self._options = normaliser_reglages(user_input)
            if self._rubrique not in self._rubriques:
                errors[CONF_RUBRIQUE] = "rubrique_inconnue"
            elif not self._options[CONF_SUIVRE_MAISON]:
                return await self.async_step_position()
            elif position_maison(self.hass) is None:
                errors["base"] = "maison_sans_position"
            else:
                return await self._creer()

        defauts = user_input or {}
        schema = probatio.Schema(
            {
                probatio.Required(
                    CONF_RUBRIQUE, default=defauts.get(CONF_RUBRIQUE, probatio.UNDEFINED)
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[{"value": v, "label": l} for v, l in self._rubriques.items()],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        ).extend(schema_reglages(defauts).schema)
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_position(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Lieu de recherche, quand ce n'est pas la maison."""
        if user_input is not None:
            self._options[CONF_POSITION] = normaliser_position(user_input[CONF_POSITION])
            return await self._creer()
        return self.async_show_form(
            step_id="position",
            data_schema=schema_position(position_par_defaut(self.hass)),
        )

    async def _creer(self) -> ConfigFlowResult:
        """Crée l'entrée, sauf si ce métier est déjà suivi à ce lieu."""
        assert self._rubrique is not None
        await self.async_set_unique_id(id_unique(self._rubrique, self._options))
        self._abort_if_unique_id_configured()
        titre = self._titres[self._rubrique]
        return self.async_create_entry(
            title=titre_entree(self.hass, titre, self._options),
            data={CONF_RUBRIQUE: self._rubrique, CONF_TITRE: titre},
            options=self._options,
        )


class OptionsCarteDesArtisans(OptionsFlowWithReload):
    """Rayon, labellisés, maison ou lieu choisi (la rubrique ne change pas)."""

    def __init__(self) -> None:
        """État du parcours."""
        self._options: dict[str, Any] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Réglages."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._options = normaliser_reglages(user_input)
            if not self._options[CONF_SUIVRE_MAISON]:
                return await self.async_step_position()
            if position_maison(self.hass) is None:
                errors["base"] = "maison_sans_position"
            else:
                return self._enregistrer()
        defauts = user_input or dict(self.config_entry.options)
        return self.async_show_form(step_id="init", data_schema=schema_reglages(defauts), errors=errors)

    async def async_step_position(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Lieu de recherche."""
        if user_input is not None:
            self._options[CONF_POSITION] = normaliser_position(user_input[CONF_POSITION])
            return self._enregistrer()
        actuelle = self.config_entry.options.get(CONF_POSITION)
        return self.async_show_form(
            step_id="position",
            data_schema=schema_position(position_par_defaut(self.hass, actuelle)),
        )

    def _enregistrer(self) -> ConfigFlowResult:
        """Met à jour l'identifiant et le titre (s'il n'a pas été renommé), puis les options."""
        entry = self.config_entry
        rubrique = entry.data[CONF_RUBRIQUE]
        nouvel_id = id_unique(rubrique, self._options)
        for autre in self.hass.config_entries.async_entries(DOMAIN):
            if autre.entry_id != entry.entry_id and autre.unique_id == nouvel_id:
                return self.async_abort(reason="already_configured")
        titre = entry.data.get(CONF_TITRE, entry.title)
        ancien = {
            CONF_RAYON: entry.options.get(CONF_RAYON, RAYON_DEFAUT),
            CONF_SUIVRE_MAISON: entry.options.get(CONF_SUIVRE_MAISON, True),
        }
        changements: dict[str, Any] = {"unique_id": nouvel_id}
        if entry.title == titre_entree(self.hass, titre, ancien):
            changements["title"] = titre_entree(self.hass, titre, self._options)
        self.hass.config_entries.async_update_entry(entry, **changements)
        return self.async_create_entry(data=self._options)
