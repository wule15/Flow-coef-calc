"""
Valve body material screening by temperature, ASME and EN designations.

What this does
--------------
Given the coldest and hottest temperature the valve body sees, it excludes
materials that are outside their permitted range and lists the ones that are
not. Both the ASTM/ASME grade and the EN material number are given, because
a European datasheet and an American one name the same casting differently
and that mismatch causes real procurement errors.

What this deliberately does not do
----------------------------------
**It does not select a material.** Temperature is usually not the deciding
factor. Material selection is driven by corrosion and compatibility with the
process fluid, by the pressure class, by erosion, and by whatever the client
specification mandates. This library knows none of those things.

So the output is "carbon steel is excluded at this temperature, these groups
are not" rather than "use 1.4408". Anything stronger would be a confident
recommendation made on one variable out of five.

The low temperature limit is the one that bites
-----------------------------------------------
In Europe the governing requirement is EN 13480-2 for industrial piping and
EN 13445-2 for pressure vessels, both under the Pressure Equipment Directive
2014/68/EU. They set the impact testing a steel needs for its design minimum
temperature, and for ordinary carbon steel that boundary sits around -29 C,
which is also the ASME B31.3 exemption limit quoted in American practice.
Below it the steel loses toughness and can fail in a brittle manner without
warning. Joule-Thomson
cooling on a gas letdown routinely lands below that line while the inlet is
at a comfortable ambient temperature, which is exactly the case an engineer
is most likely to miss.

Sources
-------
EN 10213 for the European cast steel grades, which is the primary reference
here. ASTM A216, A217, A351 and A352 for the American equivalents, given
alongside because datasheets cross borders. EN 13480-2 and EN 13445-2 for the
low temperature requirement under PED 2014/68/EU, with ASME B31.3 Table
323.2.2 as the American counterpart.

Ranges below are commonly quoted service limits and are a screening aid, not
a substitute for the material standard.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Material:
    """One cast valve body material, in both designation systems."""

    asme: str
    en_number: str
    en_name: str
    min_c: float
    max_c: float
    group: str
    note: str

    def __str__(self) -> str:
        return f'{self.en_number} {self.en_name} / {self.asme}'


MATERIALS: tuple[Material, ...] = (
    Material('A216 WCB', '1.0619', 'GP240GH', -29, 425, 'carbon steel',
             'the default body material for general service'),
    Material('A352 LCB', '1.6220', 'G20Mn5', -46, 343, 'low temperature carbon steel',
             'impact tested carbon steel, the first step down from WCB'),
    Material('A352 LCC', '1.6220', 'G20Mn5+QT', -46, 343, 'low temperature carbon steel',
             'higher strength than LCB, same temperature floor'),
    Material('A352 LC3', '1.5638', 'G9Ni10', -101, 343, 'nickel steel',
             '3.5 percent nickel, for deep cold service'),
    Material('A352 LC9', '1.5662', 'X8Ni9', -196, 100, 'nickel steel',
             '9 percent nickel, LNG and cryogenic service'),
    Material('A351 CF8', '1.4308', 'GX5CrNi19-10', -196, 538, 'austenitic stainless',
             'cast 304. No low temperature limit of practical concern'),
    Material('A351 CF8M', '1.4408', 'GX5CrNiMo19-11-2', -196, 538, 'austenitic stainless',
             'cast 316, molybdenum bearing, the usual process choice'),
    Material('A351 CF3M', '1.4409', 'GX2CrNiMo19-11-2', -196, 454, 'austenitic stainless',
             'low carbon 316L, for welded assemblies and corrosion service'),
    Material('A217 WC6', '1.7357', 'G17CrMo5-5', -29, 540, 'chrome moly',
             '1.25Cr 0.5Mo, for elevated temperature service'),
    Material('A217 WC9', '1.7379', 'G17CrMo9-10', -29, 570, 'chrome moly',
             '2.25Cr 1Mo, higher temperature than WC6'),
    Material('A217 C5', '1.7363', 'G12MoCrV5-2', -29, 650, 'chrome moly',
             '5Cr 0.5Mo, high temperature and some sulphur resistance'),
)

CARBON_STEEL_FLOOR_C = -29.0


@dataclass(frozen=True)
class MaterialGuidance:
    """Which materials the temperature range permits, and which it excludes."""

    checked: bool
    minimum_c: float | None
    maximum_c: float | None
    candidates: tuple[Material, ...]
    excluded: tuple[Material, ...]
    headline: str
    caveat: str

    def __str__(self) -> str:
        if not self.checked:
            return 'material not screened'
        if not self.candidates:
            return f'{self.headline} No material in the table covers this range.'
        names = ', '.join(str(m) for m in self.candidates[:3])
        more = f', and {len(self.candidates) - 3} more' if len(self.candidates) > 3 else ''
        return f'{self.headline} Temperature-suitable: {names}{more}'


NOT_SCREENED = MaterialGuidance(
    checked=False, minimum_c=None, maximum_c=None,
    candidates=(), excluded=(), headline='', caveat='',
)

_CAVEAT = (
    'Screened on temperature only. Material selection is normally decided by '
    'corrosion and compatibility with the process fluid, by pressure class, '
    'and by the client specification, none of which this library knows. Treat '
    'this as an exclusion list, not a recommendation, and confirm against the '
    'material standard.'
)


def screen_materials(
    minimum_c: float | None,
    maximum_c: float | None,
) -> MaterialGuidance:
    """
    Materials whose service range covers the temperatures given.

    A gas letdown cooling to -41 C, which is where carbon steel drops out:

    >>> g = screen_materials(-41.0, 20.0)
    >>> any(m.asme == 'A216 WCB' for m in g.candidates)
    False
    >>> any(m.asme == 'A351 CF8M' for m in g.candidates)
    True

    Ordinary ambient service, where everything qualifies:

    >>> len(screen_materials(10.0, 80.0).excluded)
    0
    """
    if minimum_c is None and maximum_c is None:
        return NOT_SCREENED

    low = minimum_c if minimum_c is not None else maximum_c
    high = maximum_c if maximum_c is not None else minimum_c

    candidates = tuple(m for m in MATERIALS if m.min_c <= low and m.max_c >= high)
    excluded = tuple(m for m in MATERIALS if m not in candidates)

    if low < CARBON_STEEL_FLOOR_C:
        headline = (
            f'Coldest metal temperature approximately {low:.0f} C, below the '
            f'{CARBON_STEEL_FLOOR_C:.0f} C impact test boundary of EN 13480-2 '
            f'and ASME B31.3. '
            f'Ordinary carbon steel is excluded.'
        )
    elif high > 425:
        headline = (
            f'Hottest metal temperature approximately {high:.0f} C, above the '
            f'usual carbon steel ceiling. A chrome moly or austenitic grade is '
            f'required.'
        )
    else:
        headline = (
            f'Metal temperature between {low:.0f} C and {high:.0f} C, within '
            f'ordinary carbon steel range.'
        )

    return MaterialGuidance(
        checked=True,
        minimum_c=low,
        maximum_c=high,
        candidates=candidates,
        excluded=excluded,
        headline=headline,
        caveat=_CAVEAT,
    )
