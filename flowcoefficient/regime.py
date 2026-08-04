"""
Flow regime screening. IEC 60534-2-1 clause 6.

Every sizing equation in this library assumes fully developed turbulent
flow. That assumption is true for water, air and gas in almost any normal
service, and false for viscous liquids, small valves and low flows.

**This module screens the assumption. It does not correct for it.**

When flow is not fully turbulent, IEC applies a Reynolds number factor FR
that reduces the effective coefficient. FR is not implemented here. What is
implemented is the check that tells you the turbulent equations no longer
apply, so a viscous answer arrives labelled rather than silently wrong.

That distinction is the whole point of the module. A library that quietly
returns a turbulent answer for hot bitumen has told you nothing about the
30 percent error it just handed you.

The screening equation
----------------------
IEC 60534-2-1 gives the valve Reynolds number as

    Rev = N4 * Fd * Q / ( nu * sqrt(C * FL) )
          * ( (FL^2 * C^2) / (N2 * D^4) + 1 ) ^ 0.25

with N4 = 7.07e4 for Q in m3/h, nu in mm2/s (centistokes), C as Kv, D in mm.

The bracketed term corrects for the valve being small relative to the pipe.
It is always at or above 1, so **dropping it underestimates Rev**, which
makes the screening conservative: it will warn slightly too often rather
than too rarely. The library drops it when no diameter is supplied and says
so in the result, because requiring a valve diameter to run a warning check
would mean the check rarely gets run.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .errors import InvalidFluidPropertyError

# IEC 60534-2-1 Table 1. Q in m3/h, kinematic viscosity in mm2/s, C as Kv.
N4 = 7.07e4

# IEC 60534-2-1 Table 1. D in mm, C as Kv. Imported from the piping module so
# there is one value rather than two that can drift apart. The 1.60e-3 that
# used to sit here was correct; it was briefly replaced with 0.00286, which
# was not. See the derivation in piping.py.
from .piping import N2  # noqa: E402

# IEC treats flow as fully turbulent above 10 000 and fully laminar below
# about 10. Between the two the FR correction applies on a curve.
FULLY_TURBULENT_ABOVE = 10_000.0
FULLY_LAMINAR_BELOW = 10.0


@dataclass(frozen=True)
class FlowRegime:
    """The outcome of the screening, including the case where it was skipped."""

    checked: bool
    reynolds: float | None
    regime: str            # 'turbulent' | 'transitional' | 'laminar' | 'not checked'
    correction_needed: bool
    note: str

    def __str__(self) -> str:
        if not self.checked:
            return 'flow regime not checked, turbulent assumed'
        return f'Rev {self.reynolds:,.0f}, {self.regime}'


NOT_CHECKED = FlowRegime(
    checked=False,
    reynolds=None,
    regime='not checked',
    correction_needed=False,
    note=(
        'No kinematic viscosity supplied, so fully turbulent flow is assumed. '
        'That holds for water, air and gas in normal service. Supply '
        'viscosity in centistokes to have it checked.'
    ),
)


def screen(
    flow_rate_m3h: float,
    kv: float,
    kinematic_viscosity_cst: float | None,
    fl: float | None,
    fd: float,
    valve_diameter_mm: float | None = None,
) -> FlowRegime:
    """
    Screen the turbulent flow assumption.

    Returns NOT_CHECKED when viscosity or FL is unavailable, rather than
    guessing. A result that says it did not look is honest; a result that
    says turbulent when nothing was checked is not.

    Water at 1 cSt through a DN50 globe valve, well into turbulent:

    >>> screen(25.0, 17.68, 1.0, 0.9, 0.46).regime
    'turbulent'

    The same duty on a 200 cSt oil, which has fallen out of the turbulent
    range the sizing equations assume:

    >>> screen(25.0, 17.68, 200.0, 0.9, 0.46).regime
    'transitional'
    """
    if kinematic_viscosity_cst is None or fl is None:
        return NOT_CHECKED

    if kinematic_viscosity_cst <= 0:
        raise InvalidFluidPropertyError(
            f'kinematic viscosity must be positive, got '
            f'{kinematic_viscosity_cst} cSt'
        )

    rev = N4 * fd * flow_rate_m3h / (kinematic_viscosity_cst * math.sqrt(kv * fl))

    used_diameter = valve_diameter_mm is not None and valve_diameter_mm > 0
    if used_diameter:
        rev *= ((fl ** 2 * kv ** 2) / (N2 * valve_diameter_mm ** 4) + 1.0) ** 0.25

    if rev >= FULLY_TURBULENT_ABOVE:
        regime = 'turbulent'
        correction = False
        note = 'Fully turbulent. The sizing equations apply as written.'
    elif rev <= FULLY_LAMINAR_BELOW:
        regime = 'laminar'
        correction = True
        note = (
            'Laminar. The turbulent sizing equations do not describe this flow '
            'and the coefficient above is not trustworthy. IEC 60534-2-1 '
            'clause 6 gives the Reynolds factor FR, which this library does '
            'not implement.'
        )
    else:
        regime = 'transitional'
        correction = True
        note = (
            'Transitional. The turbulent sizing equations are losing accuracy '
            'and the error grows as Rev falls. IEC 60534-2-1 clause 6 gives '
            'the Reynolds factor FR, which this library does not implement.'
        )

    if not used_diameter:
        note += (
            ' No valve diameter supplied, so the pipe geometry term was '
            'dropped. That underestimates Rev, so this screening errs towards '
            'warning rather than staying quiet.'
        )

    return FlowRegime(
        checked=True,
        reynolds=rev,
        regime=regime,
        correction_needed=correction,
        note=note,
    )
