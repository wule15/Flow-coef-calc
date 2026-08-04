"""
Piping geometry factor Fp. IEC 60534-2-1 clause 5.

Why it exists
-------------
A control valve is routinely one or two sizes smaller than the line it sits
in, with a reducer on the inlet and an increaser on the outlet. Those
fittings have their own pressure loss, so the assembly passes less than the
bare valve would on its own.

Fp is the ratio between the two. It is always at or below 1, typically 0.85
to 0.99, and ignoring it makes a sizing calculation optimistic: the
coefficient comes out too small and the installed valve cannot quite pass the
duty.

The equation
------------
    Fp = 1 / sqrt( 1 + (sum_Z / N2) * (C / d^2)^2 )

    sum_Z = Z1 + Z2 + ZB1 - ZB2

with, for a valve of bore d between an upstream line D1 and a downstream D2:

    Z1  = 0.5 * (1 - d^2/D1^2)^2      inlet reducer
    Z2  = 1.0 * (1 - d^2/D2^2)^2      outlet increaser
    ZB1 = 1 - (d/D1)^4                Bernoulli, inlet
    ZB2 = 1 - (d/D2)^4                Bernoulli, outlet

For the common case of identical reducers, D1 = D2, the two Bernoulli terms
cancel and this reduces to sum_Z = 1.5 * (1 - d^2/D^2)^2.

Which C goes into it
--------------------
The valve's **rated** coefficient, fully open, from the catalogue. Fp is a
property of a particular valve in particular pipework, not of the duty, so
it cannot be computed before a candidate valve is chosen. IEC handles the
circularity by iterating from an estimate; this library sidesteps it by
asking for the candidate, which the caller has anyway if they are checking
valve opening.

The N2 constant
---------------
N2 = 0.00160 for d in mm with C expressed as Kv.

The published table gives 890 for d in inches and 0.00214 for millimetres,
both with C as Cv. Those two must differ by exactly the fourth power of the
inch-to-millimetre ratio, because the constant sits under (C/d^2)^2:

    890 / 25.4^4 = 890 / 416231 = 0.002138   ->  0.00214, confirming the pair

Converting from Cv to Kv **divides**, and getting that direction wrong is how
this constant shipped wrong once already. C is squared in the numerator, so
expressing it as Cv makes that term 1.156^2 larger; to leave Fp unchanged N2
must be 1.156^2 larger too. Therefore N2 for Kv is the smaller number:

    0.00214 / 1.156^2 = 0.00160              ->  as Kv

A derivation that touches the published table nowhere, as a second opinion.
Valve resistance K = dP / (0.5 * rho * v^2) with v = 353.678 * Q / d^2 in
m/s for Q in m3/h and d in mm, and dP = SG * (Q/Kv)^2 in bar by the
definition of Kv:

    N2 = 2e5 / (1000 * 353.678^2) = 0.001599

Both give 0.00160. The earlier value of 0.00286 was this conversion applied
backwards, which made Fp too close to 1, which made the required coefficient
too small, which undersizes the valve. Up to 15 percent low on a reduced bore
ball installation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .errors import OutOfRangeError

# d in mm, C as Kv. See the module docstring for both derivations.
N2 = 0.00160

# The published imperial value, kept so the derivation above stays checkable.
N2_INCH_CV = 890.0


@dataclass(frozen=True)
class PipingGeometry:
    """Fp and the terms behind it, so the number can be checked."""

    checked: bool
    fp: float
    sum_z: float | None
    valve_diameter_mm: float | None
    upstream_diameter_mm: float | None
    downstream_diameter_mm: float | None
    rated_kv: float | None
    note: str

    def __str__(self) -> str:
        if not self.checked:
            return 'Fp not applied, line size not given'
        return (
            f'Fp {self.fp:.4g} '
            f'(valve {self.valve_diameter_mm:.0f} mm in '
            f'{self.upstream_diameter_mm:.0f} mm line)'
        )


NOT_APPLIED = PipingGeometry(
    checked=False, fp=1.0, sum_z=None,
    valve_diameter_mm=None, upstream_diameter_mm=None,
    downstream_diameter_mm=None, rated_kv=None,
    note=(
        'No piping geometry factor applied. Fp needs the valve bore, the line '
        'bore and the candidate valve rated Kv. Without it the result assumes '
        'the valve is line size, which is optimistic if it is not.'
    ),
)


def piping_geometry_factor(
    rated_kv: float | None,
    valve_diameter_mm: float | None,
    upstream_diameter_mm: float | None,
    downstream_diameter_mm: float | None = None,
) -> PipingGeometry:
    """
    Fp for a valve between reducers. IEC 60534-2-1 clause 5.

    Returns NOT_APPLIED, with fp = 1.0, when any input is missing. The result
    says so rather than implying the valve is line size, on the same rule as
    every other check in this library.

    A DN50 valve of Kv 63 in a DN80 line:

    >>> g = piping_geometry_factor(63, 50, 80)
    >>> round(g.fp, 4)
    0.905

    The same valve in the same line size as itself has no reducers and so no
    correction:

    >>> piping_geometry_factor(63, 50, 50).fp
    1.0
    """
    if rated_kv is None or valve_diameter_mm is None or upstream_diameter_mm is None:
        return NOT_APPLIED

    d = valve_diameter_mm
    d1 = upstream_diameter_mm
    d2 = downstream_diameter_mm if downstream_diameter_mm is not None else d1

    for name, value in (('valve_diameter_mm', d),
                        ('upstream_diameter_mm', d1),
                        ('downstream_diameter_mm', d2)):
        if value <= 0:
            raise OutOfRangeError(name, value, 0, float('inf'), 'mm')

    if d > d1 or d > d2:
        raise OutOfRangeError(
            'valve_diameter_mm', d, 0, min(d1, d2), 'mm',
            context=(
                'the valve bore is larger than the line it sits in, which is '
                'not an installation Fp describes'
            ),
        )
    if rated_kv <= 0:
        raise OutOfRangeError('rated_kv', rated_kv, 0, float('inf'))

    z1 = 0.5 * (1.0 - d ** 2 / d1 ** 2) ** 2
    z2 = 1.0 * (1.0 - d ** 2 / d2 ** 2) ** 2
    zb1 = 1.0 - (d / d1) ** 4
    zb2 = 1.0 - (d / d2) ** 4
    sum_z = z1 + z2 + zb1 - zb2

    fp = 1.0 / math.sqrt(1.0 + (sum_z / N2) * (rated_kv / d ** 2) ** 2)

    if sum_z == 0.0:
        note = 'Valve is line size, so there are no reducers and Fp is 1.'
    else:
        note = (
            f'Reducers cost {(1 - fp) * 100:.1f} percent of the bare valve '
            f'capacity. The required coefficient is divided by Fp, so the '
            f'valve has to be correspondingly larger.'
        )

    return PipingGeometry(
        checked=True,
        fp=fp,
        sum_z=sum_z,
        valve_diameter_mm=d,
        upstream_diameter_mm=d1,
        downstream_diameter_mm=d2,
        rated_kv=rated_kv,
        note=note,
    )
