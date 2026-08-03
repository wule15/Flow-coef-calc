"""
Valve style data: FL and xT.

Both are properties of a particular valve, measured by flow test to
IEC 60534-2-3 and published by the manufacturer per size and per travel.
They are not properties of the process.

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

from dataclasses import dataclass

from .errors import OutOfRangeError


@dataclass(frozen=True)
class ValveStyle:
    """Typical published values for a style of valve. Not a substitute for data."""

    name: str
    fl: float
    xt: float
    note: str
    fd: float = 0.46
    """
    Valve style modifier, IEC 60534-2-1 Annex A. Describes the shape of the
    flow passage and is used only in the Reynolds number screening. A single
    round orifice is 1.0; a parabolic plug splitting the flow is lower.
    """


# Mid-range values from published manufacturer data and IEC 60534-2-1
# Annex A typical values. Every one of these varies with size, trim and
# travel, which is exactly why they are labelled typical in the result.
VALVE_STYLES: dict[str, ValveStyle] = {
    'globe': ValveStyle('globe', fl=0.90, xt=0.75, fd=0.46,
                        note='single seat, parabolic plug, flow to open'),
    'globe cage': ValveStyle('globe cage', fl=0.90, xt=0.75, fd=0.98,
                             note='cage guided, balanced plug'),
    'angle': ValveStyle('angle', fl=0.85, xt=0.72, fd=0.46,
                        note='flow to close'),
    'butterfly': ValveStyle('butterfly', fl=0.70, xt=0.35, fd=0.57,
                            note='60 degree open, swing through'),
    'ball': ValveStyle('ball', fl=0.60, xt=0.20, fd=1.00,
                       note='full bore, chokes far earlier than a globe'),
    'segmented ball': ValveStyle('segmented ball', fl=0.66, xt=0.25, fd=0.98,
                                 note='V notch, 60 degree open'),
    'eccentric plug': ValveStyle('eccentric plug', fl=0.85, xt=0.68, fd=0.42,
                                 note='rotary, flow to open'),
}


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
        return style.fl, f'typical for {style.name}'
    return None, 'not provided'


def resolve_xt(xt: float | None, valve_style: str | None) -> tuple[float | None, str]:
    """Same as resolve_fl, for the gas side."""
    if xt is not None:
        _check_fraction('xt', xt)
        return xt, 'supplied'
    if valve_style is not None:
        style = get_valve_style(valve_style)
        return style.xt, f'typical for {style.name}'
    return None, 'not provided'
