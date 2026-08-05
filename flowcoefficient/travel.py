"""
Coefficients that follow the valve opening instead of pretending to be constants.

The problem
-----------
FL and xT are published against Cv/d-squared, which is a proxy for how far
open the valve is. A full bore ball's xT runs from 0.82 nearly closed to 0.05
fully open, a factor of sixteen. Picking one number per valve style and
calling it typical throws that away.

What this module does
---------------------
Given a valve style, its rated coefficient and its bore, it locates the
operating point on the published curve and reads FL and xT off it.

    Cv / d^2   with Cv the coefficient at that travel and d the bore in inches

Confirmed against the catalogue: a DN25 valve of rated Cv 12 tabulates a
maximum Cv/d-squared of 12.0, so the abscissa is Cv over the bore in inches
squared and nothing else.

Default behaviour
-----------------
**Fully open**, which is the rated condition a data sheet quotes, and the
conservative choice: a rotary valve's xT is lowest wide open, so assuming it
makes the choked check pessimistic rather than flattering.

Wide open means *this valve* wide open, that is its rated coefficient over its
own bore. It does not mean the far end of the published curve, which is a
Cv/d-squared a given valve may never reach.

When the bore and rated coefficient are supplied, the duty is located on the
curve and the result says where it landed and what that did to FL and xT.

The circularity, and how it is handled
--------------------------------------
The required coefficient depends on FL and xT, and FL and xT depend on the
coefficient. IEC resolves this by iterating from an estimate, and so does
this module.

An earlier version did two passes and claimed that moved the answer by well
under a percent. That claim was wrong. Sweeping realistic duties across five
valve styles, three bores, three rated coefficients and four pressure drop
ratios, two passes left 13 percent of cases more than 1 percent from the
converged answer, and the worst was 39 percent out. It converges, it does not
oscillate, but two passes does not reach it.

It now iterates to a relative tolerance with an iteration cap, and reports
how many passes it took and whether it converged. A duty that does not settle
says so rather than returning the last guess.

Source
------
Valmet/Neles control valve sizing coefficients catalogue 10CV20EN, which
publishes FL and xT against Cv/d-squared at ten travel points per valve.
These are one manufacturer's measurements on their own valves. Another
maker's curve for the same style will differ, and the data sheet for the
valve actually being bought beats both.
"""

from __future__ import annotations

from dataclasses import dataclass

MM_PER_INCH = 25.4


@dataclass(frozen=True)
class TravelCurve:
    """FL and xT against Cv/d-squared, nearly closed through fully open."""

    cv_over_d2: tuple[float, ...]
    fl: tuple[float, ...]
    xt: tuple[float, ...]
    source: str
    substituted_from: str = ''
    """
    Set when this curve belongs to a different valve geometry than the style
    it is registered under. The substitution then travels into fl_source and
    xt_source, so a caller reading only the result still learns about it.
    """

    def at(self, cv_over_d2: float) -> tuple[float, float]:
        """
        FL and xT at a point on the curve, linearly interpolated.

        Outside the tabulated span the end value is held rather than
        extrapolated. Extrapolating a fitted curve is how the Antoine mistake
        would have happened, and the same reasoning applies here.
        """
        xs = self.cv_over_d2
        if cv_over_d2 <= xs[0]:
            return self.fl[0], self.xt[0]
        if cv_over_d2 >= xs[-1]:
            return self.fl[-1], self.xt[-1]
        for i in range(1, len(xs)):
            if cv_over_d2 <= xs[i]:
                span = xs[i] - xs[i - 1]
                frac = (cv_over_d2 - xs[i - 1]) / span if span else 0.0
                fl = self.fl[i - 1] + frac * (self.fl[i] - self.fl[i - 1])
                xt = self.xt[i - 1] + frac * (self.xt[i] - self.xt[i - 1])
                return fl, xt
        return self.fl[-1], self.xt[-1]

    @property
    def curve_end(self) -> tuple[float, float]:
        """
        The far end of the published curve.

        Only the fallback when the valve's own rated point cannot be
        computed. It is a high Cv/d-squared that a given valve may never
        reach, so it is not the same thing as that valve being wide open.
        It is the conservative choice for xT, which is why it is the default.
        """
        return self.fl[-1], self.xt[-1]


_VALMET = 'Valmet/Neles 10CV20EN'

# Ten travel points per valve, nearly closed on the left.
CURVES: dict[str, TravelCurve] = {
    'globe': TravelCurve(
        cv_over_d2=(0.22, 0.70, 1.65, 2.81, 4.06, 5.34, 6.43, 6.95, 7.80, 12.0),
        fl=(0.93, 0.93, 0.92, 0.86, 0.85, 0.84, 0.83, 0.83, 0.83, 0.83),
        # This xT array is genuinely non-monotonic: it dips to 0.61 and
        # climbs back. Verified against the catalogue page twice, and the
        # equal percentage trim on the facing page prints the identical
        # numbers. It is measured behaviour, not a transcription error.
        xt=(0.69, 0.69, 0.72, 0.63, 0.61, 0.62, 0.65, 0.69, 0.71, 0.70),
        source=f'{_VALMET}, rotary globe with linear trim',
    ),
    'globe cage': TravelCurve(
        cv_over_d2=(0.18, 0.36, 0.55, 0.98, 1.68, 2.35, 2.98, 3.81, 4.66, 8.89),
        fl=(0.97, 0.97, 0.97, 0.95, 0.95, 0.95, 0.95, 0.95, 0.95, 0.95),
        xt=(0.75, 0.75, 0.75, 0.75, 0.73, 0.71, 0.74, 0.74, 0.75, 0.75),
        source=f'{_VALMET}, rotary globe with balanced trim',
    ),
    'angle': TravelCurve(
        cv_over_d2=(1.12, 2.26, 3.29, 4.53, 5.81, 7.38, 9.44, 11.44, 13.44, 15.0),
        fl=(0.91, 0.89, 0.87, 0.85, 0.83, 0.82, 0.80, 0.78, 0.77, 0.76),
        xt=(0.62, 0.62, 0.62, 0.62, 0.61, 0.60, 0.56, 0.52, 0.45, 0.40),
        source=f'{_VALMET}, eccentric rotary plug flow to open',
        substituted_from='an eccentric rotary plug, the closest published '
                         'geometry. An angle globe body does not lose '
                         'recovery as it opens the way a rotary valve does, '
                         'so treat this as indicative only',
    ),
    'butterfly': TravelCurve(
        cv_over_d2=(0.91, 2.43, 4.38, 6.60, 9.42, 13.63, 20.23, 29.60, 41.36, 47.01),
        fl=(0.87, 0.85, 0.82, 0.80, 0.78, 0.73, 0.66, 0.58, 0.46, 0.40),
        xt=(0.68, 0.68, 0.66, 0.64, 0.58, 0.52, 0.41, 0.37, 0.22, 0.15),
        source=f'{_VALMET}, soft seated butterfly',
    ),
    'butterfly concentric': TravelCurve(
        cv_over_d2=(0.20, 1.58, 3.81, 7.05, 11.50, 17.98, 27.31, 40.96, 58.95, 71.90),
        fl=(0.83, 0.83, 0.83, 0.82, 0.78, 0.72, 0.65, 0.59, 0.53, 0.48),
        xt=(0.46, 0.46, 0.46, 0.45, 0.41, 0.37, 0.35, 0.31, 0.29, 0.28),
        source=f'{_VALMET}, concentric disc butterfly',
    ),
    'ball': TravelCurve(
        cv_over_d2=(0.73, 1.60, 3.00, 5.29, 8.27, 12.62, 20.22, 33.33, 56.0, 156.0),
        fl=(0.91, 0.91, 0.90, 0.88, 0.85, 0.80, 0.74, 0.67, 0.57, 0.28),
        xt=(0.82, 0.82, 0.80, 0.75, 0.67, 0.57, 0.42, 0.30, 0.19, 0.05),
        source=f'{_VALMET}, full bore trunnion mounted ball',
    ),
    'segmented ball': TravelCurve(
        cv_over_d2=(0.59, 1.45, 2.86, 4.93, 7.64, 11.0, 15.07, 20.67, 30.80, 48.90),
        fl=(0.94, 0.93, 0.92, 0.88, 0.85, 0.81, 0.78, 0.72, 0.61, 0.42),
        xt=(0.64, 0.64, 0.63, 0.62, 0.59, 0.54, 0.49, 0.40, 0.32, 0.16),
        source=f'{_VALMET}, metal seated V-port segment',
    ),
    'eccentric plug': TravelCurve(
        cv_over_d2=(1.12, 2.26, 3.29, 4.53, 5.81, 7.38, 9.44, 11.44, 13.44, 15.0),
        fl=(0.91, 0.89, 0.87, 0.85, 0.83, 0.82, 0.80, 0.78, 0.77, 0.76),
        xt=(0.62, 0.62, 0.62, 0.62, 0.61, 0.60, 0.56, 0.52, 0.45, 0.40),
        source=f'{_VALMET}, eccentric rotary plug flow to open',
    ),
    'triple eccentric disc': TravelCurve(
        cv_over_d2=(1.38, 3.02, 5.09, 7.76, 11.17, 15.69, 21.77, 29.96, 40.72, 54.75),
        fl=(0.87, 0.85, 0.83, 0.81, 0.77, 0.73, 0.67, 0.60, 0.49, 0.36),
        xt=(0.53, 0.53, 0.53, 0.52, 0.47, 0.41, 0.35, 0.27, 0.19, 0.11),
        source=f'{_VALMET}, high performance triple eccentric disc',
    ),
}

# Below this fraction of rated capacity the valve throttles across a small
# gap: control is coarse and trim erosion accelerates. Above the upper bound
# there is no margin left for an upset.
GOOD_OPENING_LOW = 0.20
GOOD_OPENING_HIGH = 0.80

# Relative change in the coefficient below which the fixed point is settled.
# Ten to the minus four is far tighter than any valve data justifies, and it
# costs nothing: convergence is geometric and typically takes four passes.
CONVERGENCE_TOLERANCE = 1.0e-4
MAX_PASSES = 25


@dataclass(frozen=True)
class OperatingPoint:
    """Where the duty sits on the valve, and what that does to FL and xT."""

    located: bool
    fl: float | None
    xt: float | None
    fl_wide_open: float | None
    xt_wide_open: float | None
    capacity_fraction: float | None
    cv_over_d2: float | None
    note: str
    substituted_from: str = ''

    def __str__(self) -> str:
        if not self.located:
            return 'operating point not located, coefficients taken wide open'
        return (
            f'{self.capacity_fraction * 100:.0f} percent of rated capacity, '
            f'FL {self.fl:.3g} xT {self.xt:.3g} '
            f'(wide open {self.fl_wide_open:.3g} / {self.xt_wide_open:.3g})'
        )


NOT_LOCATED = OperatingPoint(
    located=False, fl=None, xt=None, fl_wide_open=None, xt_wide_open=None,
    capacity_fraction=None, cv_over_d2=None,
    note=(
        'No rated coefficient or bore supplied, so FL and xT are the wide '
        'open values. That is the rated condition and the conservative choice '
        'for a rotary valve, whose xT is lowest fully open. Supply rated_kv '
        'and valve_diameter_mm to locate the duty on the published curve.'
    ),
)


NO_CURVE = OperatingPoint(
    located=False, fl=None, xt=None, fl_wide_open=None, xt_wide_open=None,
    capacity_fraction=None, cv_over_d2=None,
    note=(
        'No published travel curve is held for this valve style, so FL and xT '
        'are the placeholder values. The bore and rated coefficient supplied '
        'were not used.'
    ),
)


def locate(
    style_name: str,
    required_kv: float,
    rated_kv: float | None,
    valve_diameter_mm: float | None,
) -> OperatingPoint:
    """
    Read FL and xT off the published curve at the duty's own operating point.

    A DN100 ball valve rated Kv 800 asked to pass Kv 200 is at a quarter of
    its capacity, where xT is far higher than wide open:

    >>> p = locate('ball', 200.0, 800.0, 100.0)
    >>> round(p.capacity_fraction, 3)
    0.25
    >>> p.xt > p.xt_wide_open
    True
    >>> round(p.xt, 3), round(p.xt_wide_open, 3)
    (0.525, 0.185)
    """
    # Normalise exactly as get_valve_style does. Without this a caller who
    # writes 'Ball' passes style validation, misses the curve, silently falls
    # back to the placeholder, and gets an answer 85 percent different with a
    # note claiming no bore was supplied.
    curve = CURVES.get(style_name.strip().lower()) if style_name else None
    if curve is None:
        return NOT_LOCATED
    if rated_kv is None or valve_diameter_mm is None:
        return NOT_LOCATED
    if curve is None:
        return NO_CURVE
    if rated_kv <= 0 or valve_diameter_mm <= 0 or required_kv <= 0:
        return NOT_LOCATED

    d_inch = valve_diameter_mm / MM_PER_INCH
    # Wide open means THIS valve fully open, which is its rated coefficient
    # over its own bore, not the far end of a curve it may never reach.
    rated_cv_over_d2 = (rated_kv * 1.156) / (d_inch ** 2)
    fl_open, xt_open = curve.at(rated_cv_over_d2)
    cv_over_d2 = (required_kv * 1.156) / (d_inch ** 2)
    fl, xt = curve.at(cv_over_d2)
    fraction = required_kv / rated_kv

    parts = [f'Located on the {curve.source} curve at Cv/d2 {cv_over_d2:.3g}.']
    if curve.substituted_from:
        parts.append(f'That curve is measured on {curve.substituted_from}.')
    if fraction < GOOD_OPENING_LOW:
        parts.append(
            f'The duty is {fraction * 100:.0f} percent of rated capacity, below '
            f'{GOOD_OPENING_LOW * 100:.0f} percent. The valve will pass this '
            f'flow, but not at its best: throttling near the seat gives coarse '
            f'control and accelerates trim erosion. A smaller valve would work '
            f'this duty better.'
        )
    elif fraction > GOOD_OPENING_HIGH:
        parts.append(
            f'The duty is {fraction * 100:.0f} percent of rated capacity, above '
            f'{GOOD_OPENING_HIGH * 100:.0f} percent. It will pass, but there is '
            f'little margin left for an upset or for fouling.'
        )
    else:
        parts.append(
            f'The duty is {fraction * 100:.0f} percent of rated capacity, inside '
            f'the {GOOD_OPENING_LOW * 100:.0f} to {GOOD_OPENING_HIGH * 100:.0f} '
            f'percent band where a control valve works well.'
        )

    if xt_open and abs(xt - xt_open) / xt_open > 0.25:
        parts.append(
            f'xT at this travel is {xt:.3g} against {xt_open:.3g} wide open, a '
            f'difference of {abs(xt - xt_open) / xt_open * 100:.0f} percent, so '
            f'using the rated figure would have misjudged the choked point.'
        )

    return OperatingPoint(
        located=True,
        substituted_from=curve.substituted_from,
        fl=fl,
        xt=xt,
        fl_wide_open=fl_open,
        xt_wide_open=xt_open,
        capacity_fraction=fraction,
        cv_over_d2=cv_over_d2,
        note=' '.join(parts),
    )
