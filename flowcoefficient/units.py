"""
Unit conversion, and the gauge to absolute boundary.

The library works internally in bar, cubic metres per hour and kelvin.
Everything arriving from outside is converted here, once, on entry.

Why one internal unit system rather than a constants table
----------------------------------------------------------
The IEC 60534 sizing equations carry a numerical constant, N, whose value
depends on the units the caller is working in. That constant is not physics,
it is units bookkeeping, and the standard publishes a table of N values
because the equation stays put while the units move.

A library can either carry that table and select from it, or convert inputs
once and use a single constant. This library does the second. The equations
are identical either way, but with one physics path a sizing error and a
units error cannot disguise each other, and the conversions here can be
tested to a tolerance without touching a flow equation.

Sources for the conversion factors
----------------------------------
BIPM, The International System of Units (SI), 9th edition 2019, for the
exact definitions. NIST Special Publication 811 for the derived factors.
Every factor below is exact by definition except where noted.
"""

from __future__ import annotations

from .errors import InvalidPressureError, UnknownUnitError

# Standard atmosphere. Exact by definition, ISO 2533 and BIPM.
STANDARD_ATMOSPHERE_BAR = 1.01325

# ── Pressure ─────────────────────────────────────────────────────────────────
# Multiply a value in the keyed unit by the factor to get bar.
# 1 bar = 100 000 Pa exactly. 1 psi = 6894.757293168 Pa exactly, from the
# definition of the pound-force and the inch.
_PRESSURE_TO_BAR: dict[str, float] = {
    'bar': 1.0,
    'mbar': 1.0e-3,
    'pa': 1.0e-5,
    'kpa': 1.0e-2,
    'mpa': 10.0,
    'psi': 0.0689475729316836,
    'atm': STANDARD_ATMOSPHERE_BAR,
    'kgf/cm2': 0.980665,  # still on older European valve datasheets
}

# ── Volumetric flow ──────────────────────────────────────────────────────────
# Multiply a value in the keyed unit by the factor to get m3/h.
# The US liquid gallon is 231 cubic inches exactly, so
# 1 US gpm = 231 * 0.0254^3 * 60 = 0.227124707 m3/h.
_FLOW_TO_M3H: dict[str, float] = {
    'm3/h': 1.0,
    'm3/s': 3600.0,
    'l/h': 1.0e-3,
    'l/min': 0.06,
    'l/s': 3.6,
    'gpm': 0.2271247,      # US liquid gallons per minute
    'gph': 0.003785412,    # US liquid gallons per hour
    'cfh': 0.0283168466,   # cubic feet per hour
    'cfm': 1.699010796,    # cubic feet per minute
}

_TEMPERATURE_UNITS: tuple[str, ...] = ('c', 'f', 'k')

# Unit sets the caller can name instead of listing each unit.
UNIT_SYSTEMS: dict[str, dict[str, str]] = {
    'metric': {'pressure': 'bar', 'flow': 'm3/h', 'temperature': 'c'},
    'imperial': {'pressure': 'psi', 'flow': 'gpm', 'temperature': 'f'},
}


def _normalise(unit: str) -> str:
    return unit.strip().lower().replace('^', '')


def convert_pressure(value: float, frm: str, to: str) -> float:
    """
    Convert a pressure between units. Basis is not changed.

    This converts magnitude only. A gauge value in is a gauge value out.
    Use to_absolute_bar when the basis matters, which is every time a
    pressure reaches a sizing equation.

    >>> round(convert_pressure(1.0, 'bar', 'psi'), 4)
    14.5038
    >>> round(convert_pressure(100.0, 'kpa', 'bar'), 6)
    1.0
    """
    f, t = _normalise(frm), _normalise(to)
    for unit in (f, t):
        if unit not in _PRESSURE_TO_BAR:
            raise UnknownUnitError(unit, 'pressure', tuple(_PRESSURE_TO_BAR))
    return value * _PRESSURE_TO_BAR[f] / _PRESSURE_TO_BAR[t]


def convert_flow(value: float, frm: str, to: str) -> float:
    """
    Convert a volumetric flow rate between units.

    >>> round(convert_flow(1.0, 'm3/h', 'gpm'), 4)
    4.4029
    >>> round(convert_flow(60.0, 'l/min', 'm3/h'), 6)
    3.6
    """
    f, t = _normalise(frm), _normalise(to)
    for unit in (f, t):
        if unit not in _FLOW_TO_M3H:
            raise UnknownUnitError(unit, 'flow', tuple(_FLOW_TO_M3H))
    return value * _FLOW_TO_M3H[f] / _FLOW_TO_M3H[t]


def convert_temperature(value: float, frm: str, to: str) -> float:
    """
    Convert a temperature between Celsius, Fahrenheit and kelvin.

    Offsets rather than factors, so this cannot share the table above.

    >>> round(convert_temperature(0.0, 'c', 'k'), 2)
    273.15
    >>> round(convert_temperature(212.0, 'f', 'c'), 6)
    100.0
    """
    f, t = _normalise(frm), _normalise(to)
    for unit in (f, t):
        if unit not in _TEMPERATURE_UNITS:
            raise UnknownUnitError(unit, 'temperature', _TEMPERATURE_UNITS)

    if f == 'c':
        kelvin = value + 273.15
    elif f == 'f':
        kelvin = (value + 459.67) * 5.0 / 9.0
    else:
        kelvin = value

    if t == 'c':
        return kelvin - 273.15
    if t == 'f':
        return kelvin * 9.0 / 5.0 - 459.67
    return kelvin


def gauge_to_absolute(
    gauge_bar: float,
    atmospheric_bar: float = STANDARD_ATMOSPHERE_BAR,
) -> float:
    """
    Add atmospheric pressure to a gauge reading.

    >>> round(gauge_to_absolute(5.0), 5)
    6.01325
    """
    return gauge_bar + atmospheric_bar


def absolute_to_gauge(
    absolute_bar: float,
    atmospheric_bar: float = STANDARD_ATMOSPHERE_BAR,
) -> float:
    """
    Subtract atmospheric pressure from an absolute value.

    >>> round(absolute_to_gauge(6.01325), 5)
    5.0
    """
    return absolute_bar - atmospheric_bar


def to_absolute_bar(
    value: float,
    unit: str,
    basis: str,
    atmospheric_bar: float = STANDARD_ATMOSPHERE_BAR,
    name: str = 'pressure',
) -> float:
    """
    The single entry point every pressure passes through.

    Converts to bar and to absolute, in that order, and refuses anything that
    cannot describe a real flow condition. No sizing equation in this library
    ever sees a pressure that has not been through here, which is what makes
    it impossible for a gauge value to reach a formula.

    basis must be given explicitly. There is no default, because a wrong
    assumption about basis is the error most likely to produce a confident
    wrong answer, and stating it costs one word.

    >>> round(to_absolute_bar(5.0, 'bar', 'gauge'), 5)
    6.01325
    >>> round(to_absolute_bar(6.01325, 'bar', 'absolute'), 5)
    6.01325
    """
    basis_key = basis.strip().lower()
    if basis_key not in ('absolute', 'gauge'):
        raise InvalidPressureError(
            f"pressure_basis must be 'absolute' or 'gauge', got {basis!r}. "
            f"There is no default because assuming the wrong basis is the "
            f"error most likely to produce a confident wrong answer."
        )

    in_bar = convert_pressure(value, unit, 'bar')
    absolute = gauge_to_absolute(in_bar, atmospheric_bar) if basis_key == 'gauge' else in_bar

    if absolute <= 0.0:
        detail = (
            f" ({value} {unit} gauge is below a perfect vacuum at "
            f"{atmospheric_bar} bar atmospheric)"
            if basis_key == 'gauge' else ''
        )
        raise InvalidPressureError(
            f"{name} works out at {absolute:.5g} bar absolute, which is not a "
            f"physical pressure{detail}"
        )

    return absolute


def resolve_units(system: str | None, **overrides: str | None) -> dict[str, str]:
    """
    Turn a unit system name into the individual units, with overrides.

    Lets a caller say units='imperial' rather than naming three units, while
    still allowing one of them to be set differently.

    >>> resolve_units('imperial')['pressure']
    'psi'
    >>> resolve_units('imperial', pressure='bar')['pressure']
    'bar'
    """
    key = (system or 'metric').strip().lower()
    if key not in UNIT_SYSTEMS:
        raise UnknownUnitError(key, 'system', tuple(UNIT_SYSTEMS))
    resolved = dict(UNIT_SYSTEMS[key])
    for quantity, unit in overrides.items():
        if unit is not None:
            resolved[quantity] = _normalise(unit)
    return resolved


def validate_pressure_drop(inlet_bar_a: float, outlet_bar_a: float) -> float:
    """
    Check two absolute pressures describe a real flow, and return the drop.

    Both sizing modules need this and neither should carry its own copy: a
    message that drifts between liquid and gas is a message somebody stops
    trusting.
    """
    if outlet_bar_a > inlet_bar_a:
        raise InvalidPressureError(
            f'outlet pressure {outlet_bar_a:.5g} bar absolute is above inlet '
            f'pressure {inlet_bar_a:.5g} bar absolute. Flow does not run up a '
            f'pressure gradient.'
        )
    if outlet_bar_a == inlet_bar_a:
        raise InvalidPressureError(
            'inlet and outlet pressure are equal, so there is no driving '
            'pressure drop and no finite flow coefficient exists'
        )
    return inlet_bar_a - outlet_bar_a
