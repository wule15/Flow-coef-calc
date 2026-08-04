"""
Fluid properties needed by the IEC 60534 sizing equations.

This is deliberately not a thermophysical property library. It holds five
properties, for seven fluids, each cited, each with the range it is valid
over. Anything outside that range raises rather than extrapolating.

Vapour pressure is a correlation, not a number
----------------------------------------------
Water at 20 C has a vapour pressure of 0.023 bar. At 80 C it is 0.474 bar.
At 100 C it is 1.013 bar. A table holding one value per fluid would be wrong
almost everywhere, and vapour pressure feeds straight into the cavitation
check, so wrong there means a valve that erodes.

Vapour pressure is therefore stored as Antoine constants:

    log10(P_bar) = A - B / (T_K + C)

valid over a stated temperature range. Antoine constants are fitted, not
derived, so outside their range they are not approximately right, they are
confidently wrong. The library refuses instead.

Sources
-------
Antoine constants: NIST Chemistry WebBook, https://webbook.nist.gov/chemistry/
Critical constants: NIST Chemistry WebBook.
Ratio of specific heats: at 25 C and 1 atm unless noted.
Molar masses: IUPAC 2021 atomic weights.

Every fluid entry names its source in the `source` field.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .errors import InvalidFluidPropertyError, OutOfRangeError, UnknownFluidError

# Molar mass of dry air, used to convert molar mass into gas relative
# density. CIPM 2007 composition.
MOLAR_MASS_AIR = 28.96546

# Density of water at 15 C, the reference relative density is measured
# against. IAPWS-95.
WATER_DENSITY_15C = 999.1


@dataclass(frozen=True)
class Antoine:
    """
    Antoine constants for log10(P_bar) = A - B / (T_K + C).

    min_k and max_k are the range the constants were fitted over, not the
    range the fluid exists over.
    """

    a: float
    b: float
    c: float
    min_k: float
    max_k: float
    source: str

    def vapour_pressure_bar(self, temperature_k: float) -> float:
        """Vapour pressure in bar absolute, refusing outside the fitted range."""
        if not (self.min_k <= temperature_k <= self.max_k):
            raise OutOfRangeError(
                'temperature',
                round(temperature_k, 2),
                self.min_k,
                self.max_k,
                'K',
                context=(
                    f'Antoine constants are fitted, not derived, so outside '
                    f'their range they are confidently wrong rather than '
                    f'approximately right. Source: {self.source}. Pass '
                    f'vapour_pressure explicitly to size outside this range.'
                ),
            )
        return 10.0 ** (self.a - self.b / (temperature_k + self.c))


@dataclass(frozen=True)
class Fluid:
    """One fluid, with the properties the sizing equations need."""

    name: str
    molar_mass: float                      # g/mol
    critical_pressure_bar: float
    critical_temperature_k: float
    gamma: float | None = None             # ratio of specific heats, gases
    antoine: Antoine | None = None
    liquid_density_kg_m3: float | None = None
    liquid_density_temperature_c: float | None = None
    liquid_density_note: str = ''
    specific_heat_kj_kgk: float | None = None   # cp, liquids, at reference T
    specific_heat_reference_c: float | None = None
    jt_coefficient_k_per_bar: float | None = None
    jt_reference: str = ''
    source: str = ''
    note: str = ''

    @property
    def relative_density(self) -> float | None:
        """
        Liquid density relative to water at 15 C, at the temperature the
        density below was measured at.

        Held as an absolute density with its own reference temperature rather
        than as a bare number at 15 C, because most of these fluids are not
        liquid at 15 C. Nitrogen is a liquid at minus 196 and is 0.81 there;
        a field called relative_density_15c simply had nothing to say about
        it, which made the library refuse a duty it should be able to size.
        """
        if self.liquid_density_kg_m3 is None:
            return None
        return self.liquid_density_kg_m3 / WATER_DENSITY_15C

    @property
    def gas_relative_density(self) -> float:
        """
        Density relative to air, which is what the gas sizing equation wants.

        Derived from molar mass rather than tabulated, so it cannot drift out
        of step with the molar mass above.
        """
        return self.molar_mass / MOLAR_MASS_AIR

    def vapour_pressure_bar(self, temperature_k: float) -> float:
        """Vapour pressure at temperature, or a clear refusal."""
        if self.antoine is None:
            raise InvalidFluidPropertyError(
                f"no vapour pressure correlation is held for {self.name}. "
                f"{self.note or 'It is handled as a gas in normal service.'} "
                f"Pass vapour_pressure explicitly if you need the liquid "
                f"choked flow check."
            )
        return self.antoine.vapour_pressure_bar(temperature_k)


_NIST = 'NIST Chemistry WebBook'

FLUIDS: dict[str, Fluid] = {
    'water': Fluid(
        name='water',
        molar_mass=18.01528,
        critical_pressure_bar=220.64,
        critical_temperature_k=647.096,
        antoine=Antoine(
            a=4.6543, b=1435.264, c=-64.848,
            min_k=255.9, max_k=373.0,
            source=f'{_NIST}, Stull 1947',
        ),
        liquid_density_kg_m3=999.1,
        liquid_density_temperature_c=15.0,
        liquid_density_note='the reference fluid; density falls to 958 at 100 C',
        specific_heat_kj_kgk=4.186,
        specific_heat_reference_c=15.0,
        source=f'{_NIST}. cp at 15 C, IAPWS-95. cp varies about 1 percent '
               f'between 0 and 100 C, so one value is adequate for duty '
               f'calculations over that span.',
        note='The reference fluid for both Kv and Cv, and for relative density.',
    ),
    'steam': Fluid(
        name='steam',
        molar_mass=18.01528,
        critical_pressure_bar=220.64,
        critical_temperature_k=647.096,
        gamma=1.33,
        jt_coefficient_k_per_bar=0.6,
        jt_reference='approximate, strongly condition dependent',
        source=f'{_NIST}. Gamma 1.33 for superheated steam at moderate pressure.',
        note='Same substance as water. Listed separately because it is sized '
             'with the gas equations.',
    ),
    'air': Fluid(
        name='air',
        molar_mass=MOLAR_MASS_AIR,
        critical_pressure_bar=37.86,
        critical_temperature_k=132.53,
        gamma=1.400,
        liquid_density_kg_m3=874.0,
        liquid_density_temperature_c=-194.3,
        liquid_density_note='saturated liquid at the normal boiling point. '
                            'Air is a mixture and boils over a range, so this '
                            'is approximate',
        specific_heat_kj_kgk=1.005,
        specific_heat_reference_c=20.0,
        jt_coefficient_k_per_bar=0.25,
        jt_reference='at 20 C and moderate pressure',
        source='CIPM 2007 composition. Pseudo-critical constants, air is a mixture.',
        note='The reference gas. xT is measured on air, and gas relative '
             'density is defined against it.',
    ),
    'nitrogen': Fluid(
        name='nitrogen',
        molar_mass=28.0134,
        critical_pressure_bar=33.958,
        critical_temperature_k=126.192,
        gamma=1.400,
        antoine=Antoine(
            a=3.7362, b=264.651, c=-6.788,
            min_k=63.14, max_k=126.0,
            source=f'{_NIST}, Edejer and Thodos 1967',
        ),
        liquid_density_kg_m3=806.1,
        liquid_density_temperature_c=-195.8,
        liquid_density_note='saturated liquid at the normal boiling point, 77.4 K',
        jt_coefficient_k_per_bar=0.22,
        jt_reference='at 20 C and moderate pressure',
        source=f'{_NIST}',
        note='Antoine range is cryogenic. Nitrogen is a gas in normal service.',
    ),
    'methane': Fluid(
        name='methane',
        molar_mass=16.0425,
        critical_pressure_bar=45.99,
        critical_temperature_k=190.564,
        gamma=1.32,
        antoine=Antoine(
            a=3.9895, b=443.028, c=-0.49,
            min_k=90.99, max_k=189.99,
            source=f'{_NIST}, Prydz and Goodwin 1972',
        ),
        liquid_density_kg_m3=422.4,
        liquid_density_temperature_c=-161.5,
        liquid_density_note='saturated liquid at the normal boiling point, '
                            '111.7 K. This is LNG density',
        jt_coefficient_k_per_bar=0.45,
        jt_reference='at 20 C and moderate pressure. The value that makes '
                     'gas letdown stations ice up.',
        source=f'{_NIST}',
        note='Single-component stand-in for natural gas. Real pipeline gas '
             'has a different molar mass and gamma, so pass them explicitly '
             'when the composition matters.',
    ),
    'carbon dioxide': Fluid(
        name='carbon dioxide',
        molar_mass=44.0095,
        critical_pressure_bar=73.773,
        critical_temperature_k=304.128,
        gamma=1.289,
        antoine=Antoine(
            a=6.81228, b=1301.679, c=-3.494,
            min_k=154.26, max_k=195.89,
            source=f'{_NIST}, Giauque and Egan 1937',
        ),
        liquid_density_kg_m3=1178.0,
        liquid_density_temperature_c=-56.6,
        liquid_density_note='saturated liquid at the triple point. CO2 has no '
                            'normal boiling point, it sublimes at 1 atm, so '
                            'liquid CO2 only exists above 5.2 bar',
        jt_coefficient_k_per_bar=1.10,
        jt_reference='at 20 C and moderate pressure. Large, and the reason '
                     'CO2 letdown freezes solid.',
        source=f'{_NIST}',
        note='Critical temperature is only 31 C, so CO2 is often near or '
             'above critical in service and the ideal gas assumption is poor. '
             'Supply a compressibility factor.',
    ),
    'ammonia': Fluid(
        name='ammonia',
        molar_mass=17.03052,
        critical_pressure_bar=113.33,
        critical_temperature_k=405.4,
        gamma=1.31,
        antoine=Antoine(
            a=4.86886, b=1113.928, c=-10.409,
            min_k=239.6, max_k=371.5,
            source=f'{_NIST}, Overstreet and Giauque 1937',
        ),
        liquid_density_kg_m3=618.0,
        liquid_density_temperature_c=15.0,
        liquid_density_note='saturated liquid under its own vapour pressure, '
                            'about 7.3 bar at 15 C',
        specific_heat_kj_kgk=4.70,
        specific_heat_reference_c=20.0,
        jt_coefficient_k_per_bar=2.5,
        jt_reference='at 20 C, approximate',
        source=f'{_NIST}',
        note='The case a water default would hurt most. Critical pressure is '
             '113 bar against 221 for water, so FF differs substantially.',
    ),
}

# Convenience spellings.
_ALIASES: dict[str, str] = {
    'co2': 'carbon dioxide',
    'carbon-dioxide': 'carbon dioxide',
    'nh3': 'ammonia',
    'n2': 'nitrogen',
    'ch4': 'methane',
    'natural gas': 'methane',
    'h2o': 'water',
}


def get_fluid(name: str) -> Fluid:
    """
    Look up a fluid by name or common alias.

    >>> get_fluid('co2').name
    'carbon dioxide'
    >>> round(get_fluid('water').vapour_pressure_bar(353.15), 4)
    0.4742
    """
    key = name.strip().lower()
    key = _ALIASES.get(key, key)
    if key not in FLUIDS:
        raise UnknownFluidError(name, tuple(FLUIDS) + tuple(_ALIASES))
    return FLUIDS[key]


def ff_critical_pressure_ratio(vapour_pressure_bar: float,
                               critical_pressure_bar: float) -> float:
    """
    Liquid critical pressure ratio factor FF. IEC 60534-2-1 clause 7.3.

        FF = 0.96 - 0.28 * sqrt(pv / pc)

    Approaches 0.96 as vapour pressure becomes small against critical
    pressure, and falls as the liquid approaches its critical point.

    >>> round(ff_critical_pressure_ratio(0.4741, 220.64), 4)
    0.947
    """
    if critical_pressure_bar <= 0:
        raise InvalidFluidPropertyError(
            f'critical pressure must be positive, got {critical_pressure_bar}'
        )
    if vapour_pressure_bar < 0:
        raise InvalidFluidPropertyError(
            f'vapour pressure cannot be negative, got {vapour_pressure_bar}'
        )
    if vapour_pressure_bar > critical_pressure_bar:
        raise InvalidFluidPropertyError(
            f'vapour pressure {vapour_pressure_bar} bar exceeds critical '
            f'pressure {critical_pressure_bar} bar, which is not a physical '
            f'state for a liquid'
        )
    return 0.96 - 0.28 * math.sqrt(vapour_pressure_bar / critical_pressure_bar)
