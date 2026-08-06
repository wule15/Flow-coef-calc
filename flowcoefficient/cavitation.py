"""
Cavitation and flashing, the states between "fine" and "choked".

Why this exists
---------------
The library detects choked flow, which for a liquid means cavitation severe
enough to limit the flow. That is the last event in a sequence, not the first.
By the time a valve chokes it has already been through incipient cavitation,
steady cavitation, and the onset of metal loss. A valve can report "not
choked" for years while eroding its trim.

ISA RP75.23-1995, Considerations for Evaluating Control Valve Cavitation,
defines a cavitation index

    sigma = (p1 - pv) / (p1 - p2)

and a series of thresholds, each a separate measured property of a particular
valve, supplied by its manufacturer:

    sigma_i    incipient cavitation, first detectable bubbles
    sigma_c    constant cavitation, steady and audible
    sigma_id   incipient damage, where metal loss starts
    sigma_mr   the manufacturer's recommended minimum
    sigma_ch   choking cavitation, which this library already detects

**High sigma is safe. Low sigma is severe.** Sigma falls as the pressure drop
grows, so a duty is worse the smaller the number.

What this module deliberately does not do
-----------------------------------------
It does not carry threshold values per valve style.

There are two reasons and the second is the stronger. First, the coefficients
are valve-specific in the same way FL and xT are, and this library has already
learned what happens when it invents a plausible number for one of those.
Second, and worse, RP75.23 is explicit that they **are not constant with
pressure or with valve size**. It names the two corrections: pressure scale
effect and size scale effect. A sigma measured on a DN50 valve at 5 bar does
not transfer to a DN200 valve at 40 bar. Carrying a single number per style
would be wrong in a way that cannot be fixed by choosing a better number.

So sigma is reported as an index. If you supply a threshold from a data sheet
the library compares against it and says what it means. If you do not, it
gives you the number and says it has nothing to judge it against.

Flashing
--------
Separate condition, and the one that takes the duty outside this library
altogether. If the outlet pressure is below the vapour pressure, the liquid
does not recover: it leaves the valve as a two-phase mixture.

EN IEC 60534-2-1 does not cover multiphase flow. ANSI/ISA-75.01.01 states the
same exclusion in as many words, naming gas-liquid, vapour-liquid and
gas-solid streams. So a flashing service is not a gap in this library, it is
outside the standard the library implements, and the honest response is to
say so rather than return a number.
"""

from __future__ import annotations

from dataclasses import dataclass

# ISA RP75.23 sigma is conventionally quoted to two decimals. Below about
# 1.5 most valves are cavitating in some regime; above about 3 most are not.
# These are orientation only and are never used as a verdict.
BROADLY_SEVERE_BELOW = 1.5
BROADLY_CLEAR_ABOVE = 3.0


@dataclass(frozen=True)
class CavitationIndex:
    """Sigma, and a verdict only when a threshold was supplied to judge it by."""

    computed: bool
    sigma: float | None
    threshold: float | None
    threshold_name: str
    acceptable: bool | None
    flashing: bool
    note: str
    warnings: tuple[str, ...] = ()

    def __str__(self) -> str:
        if self.flashing:
            return 'FLASHING, outlet below vapour pressure, two-phase service'
        if not self.computed:
            return 'cavitation index not computed, no vapour pressure'
        text = f'sigma {self.sigma:.3g}'
        if self.threshold is not None:
            verdict = 'acceptable' if self.acceptable else 'BELOW THE THRESHOLD'
            text += f' against {self.threshold_name} {self.threshold:.3g}, {verdict}'
        else:
            text += ', no threshold supplied to judge it against'
        return text


NOT_COMPUTED = CavitationIndex(
    computed=False, sigma=None, threshold=None, threshold_name='',
    acceptable=None, flashing=False,
    note=(
        'No vapour pressure available, so the cavitation index was not '
        'computed. Name a fluid with a temperature, or pass vapour_pressure.'
    ),
)


def evaluate(
    inlet_pressure_bar_a: float,
    outlet_pressure_bar_a: float,
    vapour_pressure_bar: float | None,
    sigma_threshold: float | None = None,
    threshold_name: str = 'the supplied threshold',
) -> CavitationIndex:
    """
    Cavitation index per ISA RP75.23, and the flashing check.

    A modest drop on cold water, nowhere near trouble:

    >>> e = evaluate(6.0, 4.0, 0.0234)
    >>> round(e.sigma, 2)
    2.99
    >>> e.flashing
    False

    The same water hot enough that the outlet sits below its vapour pressure.
    This is a flashing service and the liquid equations do not describe it:

    >>> evaluate(6.0, 0.3, 0.4736).flashing
    True

    With a manufacturer's recommended minimum to judge against:

    >>> e = evaluate(20.0, 4.0, 0.0234, sigma_threshold=2.0, threshold_name='sigma_mr')
    >>> round(e.sigma, 2), e.acceptable
    (1.25, False)
    """
    if vapour_pressure_bar is None:
        return NOT_COMPUTED

    dp = inlet_pressure_bar_a - outlet_pressure_bar_a
    if dp <= 0:
        return NOT_COMPUTED

    # Flashing is decided on the outlet, not the vena contracta. If the
    # downstream pressure is below vapour pressure the fluid cannot condense
    # back and leaves as a mixture.
    if outlet_pressure_bar_a <= vapour_pressure_bar:
        return CavitationIndex(
            computed=True,
            sigma=(inlet_pressure_bar_a - vapour_pressure_bar) / dp,
            threshold=sigma_threshold,
            threshold_name=threshold_name,
            acceptable=False,
            flashing=True,
            note=(
                f'The outlet is at {outlet_pressure_bar_a:.4g} bar absolute, at or '
                f'below the vapour pressure of {vapour_pressure_bar:.4g} bar. The '
                f'liquid flashes across the valve and leaves as a two-phase '
                f'mixture. EN IEC 60534-2-1 does not cover multiphase flow and '
                f'neither does this library, so the coefficient above describes '
                f'a liquid that is not what is actually flowing. Size this with '
                f'a package that implements a homogeneous equilibrium model, and '
                f'expect trim damage and noise.'
            ),
            warnings=(
                'FLASHING service. The sizing equations used do not describe '
                'two-phase flow.',
            ),
        )

    sigma = (inlet_pressure_bar_a - vapour_pressure_bar) / dp

    warnings: list[str] = []
    acceptable = None
    if sigma_threshold is not None:
        acceptable = sigma >= sigma_threshold
        if not acceptable:
            warnings.append(
                f'sigma {sigma:.3g} is below {threshold_name} '
                f'{sigma_threshold:.3g}, so this duty is in the regime that '
                f'threshold was set to keep it out of'
            )
        note = (
            f'sigma = (p1 - pv) / (p1 - p2) = {sigma:.4g}, compared against '
            f'{threshold_name} = {sigma_threshold:.4g}. Higher sigma is safer; '
            f'sigma falls as the pressure drop grows.'
        )
    else:
        orientation = ''
        if sigma < BROADLY_SEVERE_BELOW:
            orientation = (
                ' For orientation only, most valves are cavitating in some '
                'regime below about 1.5, but that is not a verdict on this one.'
            )
        elif sigma > BROADLY_CLEAR_ABOVE:
            orientation = (
                ' For orientation only, most valves are clear above about 3.'
            )
        note = (
            f'sigma = (p1 - pv) / (p1 - p2) = {sigma:.4g}. No threshold was '
            f'supplied, so there is nothing to judge it against. ISA RP75.23 '
            f'thresholds are measured per valve and vary with both pressure '
            f'and valve size, so this library will not invent one. Take '
            f'sigma_mr or sigma_id from the manufacturer and pass it in.'
            + orientation
        )

    return CavitationIndex(
        computed=True,
        sigma=sigma,
        threshold=sigma_threshold,
        threshold_name=threshold_name,
        acceptable=acceptable,
        flashing=False,
        note=note,
        warnings=tuple(warnings),
    )
