"""Variant watts/efficacy mapping — SINGLE EDIT POINT for photometric ratings.

The automate search NEVER reads watts/lumens from the IES file.
It reads them from the admin `VariantResponse`:

- watts  = `variant.power`    (int, W)
- lumens = `variant.power * variant.efficacy`  (efficacy in lm/W)

Photometry SHAPE (candela distribution) still comes from the IES bytes
referenced by `variant.ies_file_id` via `load_ies` — but its RATING is
overridden: the loaded profile is rescaled (see `scale_profile_to_lumens`)
so `installed_flux(profile) == variant lumens`. Without this, a variant
rated 3000 lm via efficacy but carrying a 1000 lm IES file would gate as
3000 lm yet simulate as 1000 lm.

>>> EDIT HERE whenever the rating formula changes <<<
(e.g. if the backend adds a `rated_lumens` field, change `variant_lumens`
below and everything downstream — profile scaling, lumen gate,
power density — follows.)
"""

from __future__ import annotations

from dataclasses import replace

from app.domain.models import IESProfile
from app.schemas.fixtures import VariantDetailResponse, VariantResponse

# Contract field names (VariantResponse.power / VariantResponse.efficacy).
# Change these only if the admin contract renames the fields.
VARIANT_WATTS_FIELD = "power"
VARIANT_EFFICACY_FIELD = "efficacy"


def variant_wattage(variant: VariantResponse | VariantDetailResponse) -> float:
    """Watts per fitting, from the variant response (not the IES file)."""
    return float(getattr(variant, VARIANT_WATTS_FIELD))


def variant_lumens(variant: VariantResponse | VariantDetailResponse) -> float:
    """Installed flux per fitting, lumens.

    EDIT THIS FORMULA to change the watts/efficacy mapping globally.
    Current: power (W) x efficacy (lm/W).
    """
    power = float(getattr(variant, VARIANT_WATTS_FIELD))
    efficacy = float(getattr(variant, VARIANT_EFFICACY_FIELD))
    return power * efficacy


def scale_profile_to_lumens(profile: IESProfile, target_lumens: float) -> IESProfile:
    """Rescale a loaded IES profile so its installed flux equals the variant rating.

    Only `flux_scale` changes (candela shape untouched). `load_ies` sets
    flux_scale so the zonal integral equals the IES rated lamps×lumens;
    here we override it so the integral equals `target_lumens` instead.
    """
    from app.services.ies_service import installed_flux

    if target_lumens <= 0:
        return profile
    current = installed_flux(profile)
    if current <= 0:
        return profile
    return replace(profile, flux_scale=profile.flux_scale * target_lumens / current)


__all__ = [
    "VARIANT_EFFICACY_FIELD",
    "VARIANT_WATTS_FIELD",
    "scale_profile_to_lumens",
    "variant_lumens",
    "variant_wattage",
]
