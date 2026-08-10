"""
Reynolds number factor FR for non-turbulent liquid flow. EN IEC
60534-2-1:2011 Annex A (normative), "Sizing equations for non-turbulent
flow", Equations A.6, A.7 and A.8.

The turbulent sizing equations in clause 6 assume the valve Reynolds number
Rev is at or above 10 000. Below that the flow is transitional or laminar and
the valve passes less than the turbulent equation predicts, so the required
coefficient grows to C_turbulent / FR, with FR <= 1 (Eq. A.2). regime.py
already computes Rev and flags the duty; this module supplies the correction
FR and the liquid path applies it.

The factor depends on the coefficient through Rev, and Rev depends on the
coefficient, so it is solved by fixed-point iteration to the same tolerance
the operating-point loop uses.

Trim classification, Eq. A.8, is made on the RATED coefficient, a fixed
property of the valve, so the full-size / reduced-trim branch cannot flip
mid-iteration:

    Crated / (d^2 * N18) >= 0.016   ->  full-size trim
    Crated / (d^2 * N18) <  0.016   ->  reduced trim

The intermediate variable n, Eq. A.8:

    full-size trim:  n = N2 / (C/d^2)^2
    reduced trim:    n = 1 + N32 * (C/d^2)^(2/3)

The factor itself, in the coefficient C being solved for and the liquid
pressure recovery factor FL:

    laminar,      Rev < 10   (Eq. A.6):
        FR = Min[ (0.026 / FL) * sqrt(n * Rev) , 1 ]

    transitional, Rev >= 10  (Eq. A.7):
        FR = Min[ 1 + (0.33 * sqrt(FL) / n^(1/4)) * log10(Rev/10000) ,
                  (0.026 / FL) * sqrt(n * Rev) ,
                  1 ]

Constants N18 and N32 are read from Table 1 on the Kv basis. Both differ from
the values printed in the standard's worked example, which is on the Cv basis;
using the Cv figure in a Kv library is the column swap that produced the old
N9 error, so the Kv values are used here and cross-checked against the unit
conversion in the tests.

Only the liquid path is wired up. The compressible case additionally needs
the non-turbulent expansion factor Y of Eq. A.5, which is not implemented
here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .piping import N2  # EN IEC 60534-2-1:2011 Table 1, D in mm, C as Kv
from .regime import N4  # EN IEC 60534-2-1:2011 Table 1, Q in m3/h, nu in cSt, C as Kv
from .travel import CONVERGENCE_TOLERANCE, MAX_PASSES

# EN IEC 60534-2-1:2011 Table 1, Kv basis.
# N18 sits linearly in the trim boundary C/(d^2 N18), so it scales from the
# Cv column value 1.00 by the Kv/Cv factor: 0.865 * 1.00 = 0.865.
N18 = 0.865
# N32 sits in n = 1 + N32 (C/d^2)^(2/3); C enters to the 2/3 power, so it does
# NOT scale by 0.865. From the Cv column value 127: 127 / 0.865^(2/3) = 139.9.
N32 = 140.0

# Eq. A.8 trim boundary, and the Eq. A.4(3) validity restriction on C/(N18 d^2).
TRIM_BOUNDARY = 0.016
VALIDITY_CAP = 0.047

# Below this Rev the flow is laminar (Eq. A.6); at or above it, transitional
# (Eq. A.7). Matches regime.FULLY_LAMINAR_BELOW.
LAMINAR_BELOW = 10.0


@dataclass(frozen=True)
class ReynoldsFactor:
    """
    The Reynolds-factor correction, including the case where it was not
    applied. applied is False either because the flow was turbulent (no
    correction due) or because an input needed to compute it was missing.
    """

    applied: bool
    fr: float | None
    turbulent_kv: float | None
    corrected_kv: float | None
    reynolds: float | None
    n: float | None
    trim: str                 # 'full-size' | 'reduced' | 'not classified'
    within_validity: bool
    passes: int
    converged: bool
    note: str

    def __str__(self) -> str:
        if not self.applied:
            return 'FR not applied'
        settled = 'converged' if self.converged else 'DID NOT CONVERGE'
        return (f'FR {self.fr:.4g} ({self.trim} trim, Rev {self.reynolds:,.0f}, '
                f'{settled} in {self.passes} passes)')


NOT_APPLIED = ReynoldsFactor(
    applied=False, fr=None, turbulent_kv=None, corrected_kv=None,
    reynolds=None, n=None, trim='not classified', within_validity=True,
    passes=0, converged=True,
    note=('Reynolds factor not applied. Either the flow is turbulent and no '
          'correction is due, or a valve diameter, rated coefficient, '
          'viscosity or FL was missing.'),
)


def trim_is_full_size(rated_kv: float, valve_diameter_mm: float) -> bool:
    """
    Classify trim on the rated coefficient. EN IEC 60534-2-1:2011 Eq. A.8.

    >>> trim_is_full_size(100.0, 50.0)
    True
    """
    return rated_kv / (valve_diameter_mm ** 2 * N18) >= TRIM_BOUNDARY


def n_factor(kv: float, valve_diameter_mm: float, full_size: bool) -> float:
    """
    The intermediate n. EN IEC 60534-2-1:2011 Eq. A.8.

    >>> round(n_factor(100.0, 25.0, full_size=True), 4)  # N2/(C/d^2)^2, C/d^2=0.16
    0.0625
    """
    ratio = kv / valve_diameter_mm ** 2  # C/d^2, Kv per mm^2
    if full_size:
        return N2 / ratio ** 2
    return 1.0 + N32 * ratio ** (2.0 / 3.0)


def reynolds_factor(reynolds: float, n: float, fl: float) -> float:
    """
    FR from Rev, n and FL. EN IEC 60534-2-1:2011 Eq. A.6 (laminar) and Eq. A.7
    (transitional), capped at 1.

    Pinned to the standard's own worked example (segmented ball, Cv basis):
    FL = 0.98, Rev = 1202, n = 1.235 is transitional and gives FR = 0.715.

    >>> round(reynolds_factor(1202.0, 1.235, 0.98), 3)
    0.715
    """
    laminar_term = (0.026 / fl) * math.sqrt(n * reynolds)
    if reynolds < LAMINAR_BELOW:
        return min(laminar_term, 1.0)
    transitional_term = (
        1.0 + (0.33 * math.sqrt(fl) / n ** 0.25) * math.log10(reynolds / 10_000.0)
    )
    return min(transitional_term, laminar_term, 1.0)


def _reynolds_number(kv: float, flow_rate_m3h: float, kinematic_viscosity_cst: float,
                     fl: float, fd: float, valve_diameter_mm: float) -> float:
    """
    Valve Reynolds number, EN IEC 60534-2-1:2011 Eq. (23), same form as
    regime.py but evaluated at the coefficient the FR loop is iterating. The
    pipe-geometry bracket is always kept here because FR needs a diameter
    anyway.
    """
    rev = N4 * fd * flow_rate_m3h / (kinematic_viscosity_cst * math.sqrt(kv * fl))
    rev *= ((fl ** 2 * kv ** 2) / (N2 * valve_diameter_mm ** 4) + 1.0) ** 0.25
    return rev


def apply_reynolds_factor(
    turbulent_kv: float,
    flow_rate_m3h: float,
    kinematic_viscosity_cst: float,
    fl: float,
    fd: float,
    valve_diameter_mm: float,
    rated_kv: float,
) -> ReynoldsFactor:
    """
    Correct a turbulent liquid coefficient for non-turbulent flow.

    Solves C = C_turbulent / FR(C) by fixed point, since FR depends on the
    coefficient through Rev. Returns NOT_APPLIED-style result when the flow
    turns out to be turbulent after all (FR = 1).

    Returns the corrected Kv and the full provenance of the correction.
    """
    if turbulent_kv <= 0 or valve_diameter_mm <= 0 or rated_kv <= 0:
        return NOT_APPLIED
    if kinematic_viscosity_cst <= 0 or fl <= 0 or fd <= 0:
        return NOT_APPLIED

    full_size = trim_is_full_size(rated_kv, valve_diameter_mm)
    trim = 'full-size' if full_size else 'reduced'

    kv = turbulent_kv
    fr = 1.0
    reynolds = math.nan
    n = math.nan
    converged = False
    passes = 0
    for passes in range(1, MAX_PASSES + 1):
        reynolds = _reynolds_number(
            kv, flow_rate_m3h, kinematic_viscosity_cst, fl, fd, valve_diameter_mm)
        n = n_factor(kv, valve_diameter_mm, full_size)
        fr = reynolds_factor(reynolds, n, fl)
        kv_next = turbulent_kv / fr
        if abs(kv_next - kv) <= CONVERGENCE_TOLERANCE * max(kv_next, 1e-12):
            kv = kv_next
            converged = True
            break
        kv = kv_next
    else:
        # Recompute FR at the final coefficient so the reported factor matches
        # the reported Kv even when the loop ran out of passes.
        reynolds = _reynolds_number(
            kv, flow_rate_m3h, kinematic_viscosity_cst, fl, fd, valve_diameter_mm)
        n = n_factor(kv, valve_diameter_mm, full_size)
        fr = reynolds_factor(reynolds, n, fl)

    # The Reynolds number climbed back above the turbulent threshold once the
    # coefficient settled: no correction is actually due.
    if fr >= 1.0:
        return ReynoldsFactor(
            applied=False, fr=1.0, turbulent_kv=turbulent_kv,
            corrected_kv=turbulent_kv, reynolds=reynolds, n=n, trim=trim,
            within_validity=True, passes=passes, converged=converged,
            note=('Reynolds factor resolved to 1 at the settled coefficient, '
                  'so the turbulent coefficient stands.'),
        )

    corrected_kv = turbulent_kv / fr
    within_validity = corrected_kv / (N18 * valve_diameter_mm ** 2) <= VALIDITY_CAP

    settled = ('converged' if converged
               else f'DID NOT CONVERGE in {MAX_PASSES} passes, treat with caution')
    note = (
        f'Non-turbulent flow. EN IEC 60534-2-1:2011 Annex A Reynolds factor '
        f'FR = {fr:.4g} on {trim} trim, Rev {reynolds:,.0f}, n {n:.4g}. '
        f'Required Kv raised from {turbulent_kv:.4g} to {corrected_kv:.4g}. '
        f'{settled} in {passes} passes. The Annex A curves are fitted at rated '
        f'travel and lose accuracy at low opening, and Fd is a single '
        f'catalogue value per valve style, not a per-valve type test, so treat '
        f'FR as an engineering correction rather than an exact figure.'
    )
    if not within_validity:
        note += (
            f' NOTE: C/(N18 d^2) exceeds the Eq. A.4(3) validity limit of '
            f'{VALIDITY_CAP}, so the corrected coefficient is outside the '
            f'range the Annex A fit was validated over.'
        )

    return ReynoldsFactor(
        applied=True, fr=fr, turbulent_kv=turbulent_kv, corrected_kv=corrected_kv,
        reynolds=reynolds, n=n, trim=trim, within_validity=within_validity,
        passes=passes, converged=converged, note=note,
    )
