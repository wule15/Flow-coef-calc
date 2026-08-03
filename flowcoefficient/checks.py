"""
Practical checks that need a line size or a candidate valve.

None of this is IEC 60534. The sizing equations answer "what coefficient
does this duty need". These answer "and is that a sensible thing to
install", which is a different question and the one that actually decides
whether a valve survives.

All of it is optional. Supply a pipe diameter and you get velocity checks.
Supply a candidate valve's rated coefficient and you get an opening check.
Supply neither and the sizing result is unchanged.

Why the opening check needs rated_kv and not just a diameter
------------------------------------------------------------
Oversizing is not a diameter problem, it is a travel problem. A valve is
badly sized when the duty sits at the far end of its stroke: below roughly
20 percent open the trim throttles across a tiny gap, control gets coarse
and erratic, and seat erosion accelerates. Above roughly 80 percent there is
no capacity left for an upset.

Working out where the duty sits needs the *valve's* rated coefficient, which
comes from the manufacturer catalogue. A pipe diameter cannot supply it, and
this library will not guess it from a rule of thumb, because valve capacity
per nominal size varies by a factor of three across styles and trims.

So: pass rated_kv from the catalogue and get a real answer. Pass nothing and
get an honest silence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .errors import OutOfRangeError

# API RP 14E erosional velocity, metric form.
#   v_e [ft/s] = C / sqrt(rho [lb/ft3])   with C = 100 continuous service
# converts to v_e [m/s] = 122 / sqrt(rho [kg/m3]).
EROSIONAL_C_CONTINUOUS = 122.0
EROSIONAL_C_INTERMITTENT = 152.0

# Common practice limits for liquid lines. Not a standard, a convention.
LIQUID_VELOCITY_COMFORTABLE_MS = 3.0

# Gas erosion and noise criterion, kg/(m s2). Widely used, not a standard.
GAS_RHO_V_SQUARED_LIMIT = 10_000.0

# The band a control valve should be working in at the design duty.
OPENING_BAND_LOW = 0.20
OPENING_BAND_HIGH = 0.80


@dataclass(frozen=True)
class VelocityCheck:
    """Line velocity and what it is close to."""

    checked: bool
    velocity_ms: float | None
    density_kg_m3: float | None
    erosional_limit_ms: float | None
    rho_v_squared: float | None
    warnings: tuple[str, ...]

    def __str__(self) -> str:
        if not self.checked:
            return 'velocity not checked, no pipe diameter supplied'
        text = f'{self.velocity_ms:.2f} m/s'
        if self.erosional_limit_ms:
            text += f' (erosional limit {self.erosional_limit_ms:.1f} m/s)'
        if self.warnings:
            text += ' | ' + ' | '.join(self.warnings)
        return text


VELOCITY_NOT_CHECKED = VelocityCheck(False, None, None, None, None, ())


@dataclass(frozen=True)
class OpeningCheck:
    """Where the duty sits in a candidate valve's capacity."""

    checked: bool
    required_kv: float
    rated_kv: float | None
    fraction: float | None
    warnings: tuple[str, ...]

    def __str__(self) -> str:
        if not self.checked:
            return 'valve opening not checked, no rated Kv supplied'
        text = (
            f'required Kv {self.required_kv:.4g} is '
            f'{self.fraction * 100:.0f} percent of rated {self.rated_kv:.4g}'
        )
        if self.warnings:
            text += ' | ' + ' | '.join(self.warnings)
        return text


def check_velocity(
    flow_rate_m3h: float,
    pipe_diameter_mm: float | None,
    density_kg_m3: float | None,
    is_gas: bool = False,
    intermittent: bool = False,
) -> VelocityCheck:
    """
    Line velocity, with the erosional limit from API RP 14E.

    Water at 21.5 m3/h through DN50, a normal cooling water line:

    >>> c = check_velocity(21.5, 52.5, 999.1)
    >>> round(c.velocity_ms, 2)
    2.76
    """
    if pipe_diameter_mm is None:
        return VELOCITY_NOT_CHECKED
    if pipe_diameter_mm <= 0:
        raise OutOfRangeError('pipe_diameter_mm', pipe_diameter_mm, 0, float('inf'), 'mm')

    area_m2 = math.pi * (pipe_diameter_mm / 1000.0) ** 2 / 4.0
    velocity = (flow_rate_m3h / 3600.0) / area_m2

    warnings: list[str] = []
    erosional = None
    rho_v2 = None

    if density_kg_m3 and density_kg_m3 > 0:
        c = EROSIONAL_C_INTERMITTENT if intermittent else EROSIONAL_C_CONTINUOUS
        erosional = c / math.sqrt(density_kg_m3)
        if velocity > erosional:
            warnings.append(
                f'above the API RP 14E erosional velocity of '
                f'{erosional:.1f} m/s, expect erosion of bends and fittings'
            )
        rho_v2 = density_kg_m3 * velocity ** 2
        if is_gas and rho_v2 > GAS_RHO_V_SQUARED_LIMIT:
            warnings.append(
                f'rho v squared is {rho_v2:,.0f}, above the usual '
                f'{GAS_RHO_V_SQUARED_LIMIT:,.0f} limit, expect noise and erosion'
            )

    if not is_gas and velocity > LIQUID_VELOCITY_COMFORTABLE_MS and not warnings:
        warnings.append(
            f'above {LIQUID_VELOCITY_COMFORTABLE_MS:.0f} m/s, which is high '
            f'for a liquid line. Check noise and water hammer on fast closure.'
        )

    return VelocityCheck(
        checked=True,
        velocity_ms=velocity,
        density_kg_m3=density_kg_m3,
        erosional_limit_ms=erosional,
        rho_v_squared=rho_v2,
        warnings=tuple(warnings),
    )


def check_opening(required_kv: float, rated_kv: float | None) -> OpeningCheck:
    """
    Where the duty sits in a candidate valve's stroke.

    rated_kv is the valve's fully open coefficient from the catalogue. This
    is a capacity fraction, not a travel percentage, because travel depends
    on the inherent characteristic. For an equal percentage trim the travel
    is lower than the capacity fraction, so a valve flagged here is at least
    as badly placed as it looks.

    >>> check_opening(17.6, 63).fraction
    0.27936507936507937
    >>> check_opening(60, 63).warnings[0][:34]
    'above 80 percent of rated capacity'
    """
    if rated_kv is None:
        return OpeningCheck(False, required_kv, None, None, ())
    if rated_kv <= 0:
        raise OutOfRangeError('rated_kv', rated_kv, 0, float('inf'))

    fraction = required_kv / rated_kv
    warnings: list[str] = []

    if fraction > 1.0:
        warnings.append(
            'the duty needs more than this valve can pass fully open, it is '
            'undersized'
        )
    elif fraction > OPENING_BAND_HIGH:
        warnings.append(
            f'above {OPENING_BAND_HIGH * 100:.0f} percent of rated capacity, '
            f'little margin left for an upset'
        )
    elif fraction < OPENING_BAND_LOW:
        warnings.append(
            f'below {OPENING_BAND_LOW * 100:.0f} percent of rated capacity, '
            f'the valve is oversized. Expect coarse control near the seat and '
            f'accelerated trim erosion.'
        )

    return OpeningCheck(True, required_kv, rated_kv, fraction, tuple(warnings))
