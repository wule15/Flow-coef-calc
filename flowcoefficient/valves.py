"""
Valve style data: FL, xT and Fd.

The thing to understand before using this table
-----------------------------------------------
**FL and xT are not constants. They vary across the valve travel, and for a
rotary valve they vary enormously.**

Measured data, from the Valmet/Neles control valve sizing coefficients
catalogue 10CV20EN, which publishes them against Cv/d-squared at ten travel
points from nearly closed to fully open:

    valve                        FL              xT
    RotaryGlobe, linear trim     0.93 -> 0.83    0.69 -> 0.70
    V-port segment ball          0.94 -> 0.42    0.64 -> 0.16
    Full bore ball, trunnion     0.91 -> 0.28    0.82 -> 0.05
    Eccentric rotary plug        0.91 -> 0.76    0.62 -> 0.40
    Triple eccentric disc        0.87 -> 0.36    0.53 -> 0.11
    Butterfly, soft seated       0.87 -> 0.40    0.68 -> 0.15
    Butterfly, concentric disc   0.83 -> 0.48    0.46 -> 0.28

A full bore ball's xT spans a factor of sixteen across its own travel. Any
single number for it is a point on a curve, not a property of the style.

So the figures below are **mid-travel placeholders**, chosen inside the
published range so the library can answer when you have no data sheet. They
are not from a standard and must not be cited as if they were. Every result
carries the published span alongside the value it used, so nobody mistakes a
placeholder for a measurement.

EN IEC 60534-2-3 defines the flow test a manufacturer runs to measure these.
EN IEC 60534-2-1 Annex D, Table D.1, tabulates its own typical values and is
marked **informative**, not normative, for exactly this reason.

A sizing that has to be right takes FL and xT from the data sheet for the
valve being specified, at the travel it will actually work at.

Why there are no silent defaults
--------------------------------
xT for a globe valve is around 0.75. For a ball valve it is around 0.20.
Size a ball valve using the globe figure and the library would report the
valve clear at a pressure drop ratio of 0.5, when it has in fact been choked
since 0.2. You would then size on a pressure drop the valve cannot use, get
a coefficient smaller than the duty needs, and install a valve that cannot
pass the required flow.

So a caller either supplies the manufacturer's figure, or names a valve
style and gets a typical one that is recorded as typical, or supplies
neither and the library says it did not perform the check.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .errors import OutOfRangeError


@dataclass(frozen=True)
class ValveStyle:
    """Typical published values for a style of valve. Not a substitute for data."""

    name: str
    fl: float
    xt: float
    note: str
    fd: float = 0.46
    fl_range: tuple[float, float] = (0.0, 1.0)
    xt_range: tuple[float, float] = (0.0, 1.0)
    """
    Published span across the valve travel, fully open to nearly closed.
    Carried so a caller can see how much of a placeholder the single value
    above really is.
    """
    """
    Valve style modifier, IEC 60534-2-1 Annex A. Describes the shape of the
    flow passage and is used only in the Reynolds number screening. A single
    round orifice is 1.0; a parabolic plug splitting the flow is lower.
    """


# Typical published manufacturer figures, mid-range across catalogues. NOT a
# reproduction of EN IEC 60534-2-1 Annex A; see the module docstring. The
# rotary entries in particular vary widely between makers, and a full bore
# ball is quoted anywhere from xT 0.15 to 0.42 depending on trim and travel.
# Every one of these varies with size, trim and travel, which is why the
# result records them as typical rather than measured.
VALVE_STYLES: dict[str, ValveStyle] = {
    'globe': ValveStyle('globe', fl=0.90, xt=0.69, fd=0.46,
                        note='single seat, parabolic plug, flow to open. xT '
                             'was 0.75, above the 0.72 maximum of the curve '
                             'this style uses'),
    'globe cage': ValveStyle('globe cage', fl=0.95, xt=0.75, fd=0.41,
                             note='cage guided, balanced plug. Fd was 0.98, '
                                  'which is the segmented ball figure and '
                                  'looked copied; a multi-port cage is '
                                  'nearer 0.41'),
    'angle': ValveStyle('angle', fl=0.85, xt=0.55, fd=1.00,
                        note='flow to close. Fd 1.00, a single flow passage. '
                             'xT was 0.72, above the 0.62 maximum of the '
                             'curve this style actually uses'),
    'butterfly': ValveStyle('butterfly', fl=0.70, xt=0.35, fd=0.57,
                            note='soft seated, mid travel. A concentric disc '
                                 'runs lower on xT, 0.28 to 0.46'),
    'ball': ValveStyle('ball', fl=0.60, xt=0.20, fd=1.00,
                       note='full bore trunnion mounted, around 80 percent '
                            'open. xT spans a factor of 16 across the travel, '
                            'so this figure is a placeholder more than most'),
    'segmented ball': ValveStyle('segmented ball', fl=0.66, xt=0.25, fd=0.98,
                                 note='V port, mid to open travel'),
    'butterfly concentric': ValveStyle('butterfly concentric', fl=0.72, xt=0.38,
                                      fd=0.57,
                                      note='concentric disc, mid travel. '
                                           'Flatter curve than a soft seated '
                                           'disc, and a lower xT throughout'),
    'triple eccentric disc': ValveStyle('triple eccentric disc', fl=0.75,
                                        xt=0.42, fd=0.57,
                                        note='high performance triple '
                                             'eccentric, mid travel'),
    'eccentric plug': ValveStyle('eccentric plug', fl=0.85, xt=0.55, fd=0.42,
                                 note='rotary, flow to open. xT was 0.68, '
                                      'above the published span, now mid '
                                      'range'),
}


def _spans_from_curves() -> None:
    """
    Replace each style's declared span with the span of its own travel curve.

    Hand-written spans drifted from the curves they were meant to describe:
    globe declared xT 0.69 to 0.75 against a curve dipping to 0.61, and angle
    declared 0.65 to 0.75 against a curve spanning 0.40 to 0.62, which do not
    even overlap. Deriving them removes the whole class of mismatch.
    """
    from .travel import CURVES
    for name, style in list(VALVE_STYLES.items()):
        curve = CURVES.get(name)
        if curve is None:
            continue
        VALVE_STYLES[name] = replace(
            style,
            fl_range=(min(curve.fl), max(curve.fl)),
            xt_range=(min(curve.xt), max(curve.xt)),
        )


_spans_from_curves()


def _check_fraction(name: str, value: float) -> None:
    if not 0.0 < value <= 1.0:
        raise OutOfRangeError(
            name, value, 0.0, 1.0,
            context=(
                f'{name} is a pressure recovery factor and must lie between '
                f'0 and 1. Take it from the valve manufacturer data sheet.'
            ),
        )


def get_valve_style(name: str) -> ValveStyle:
    """Look up typical values for a valve style."""
    key = name.strip().lower()
    if key not in VALVE_STYLES:
        raise OutOfRangeError(
            'valve_style', 0, 0, 0,
            context=(
                f'unknown valve style {name!r}. Known styles: '
                f'{", ".join(sorted(VALVE_STYLES))}'
            ),
        )
    return VALVE_STYLES[key]


def resolve_fl(fl: float | None, valve_style: str | None) -> tuple[float | None, str]:
    """
    Decide which FL to use and record where it came from.

    Returns (value, source). A supplied figure always wins over a style
    default, and the source string travels into the result so a reader can
    tell a measured figure from a typical one.
    """
    if fl is not None:
        _check_fraction('fl', fl)
        return fl, 'supplied'
    if valve_style is not None:
        style = get_valve_style(valve_style)
        lo, hi = style.fl_range
        return style.fl, (
            f'placeholder for {style.name} at mid travel. Published span '
            f'{lo:.2f} to {hi:.2f} across the travel, so take the data sheet '
            f'figure for a sizing that has to be right'
        )
    return None, 'not provided'


def resolve_xt(xt: float | None, valve_style: str | None) -> tuple[float | None, str]:
    """Same as resolve_fl, for the gas side."""
    if xt is not None:
        _check_fraction('xt', xt)
        return xt, 'supplied'
    if valve_style is not None:
        style = get_valve_style(valve_style)
        lo, hi = style.xt_range
        return style.xt, (
            f'placeholder for {style.name} at mid travel. Published span '
            f'{lo:.2f} to {hi:.2f} across the travel, so take the data sheet '
            f'figure for a sizing that has to be right'
        )
    return None, 'not provided'
