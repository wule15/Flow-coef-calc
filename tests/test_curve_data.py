"""
Pins the published data and the behaviour a mutation probe found unguarded.

A review mutated constants and code across the package and reported what the
231 tests failed to notice. Everything below survived: eight of the nine
travel curves, the FLP over Fp correction, the choked clamp inside the
refinement loop, and the choked branch of the liquid path.

That matters more here than in most projects. Two numerical constants in this
library have already been wrong by factors of 185 and 1.79, both enshrined in
passing tests. A number nothing pins is a number waiting to be wrong.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flowcoefficient import gas_flow_coefficient, liquid_flow_coefficient  # noqa: E402
from flowcoefficient.piping import piping_geometry_factor  # noqa: E402
from flowcoefficient.travel import CURVES  # noqa: E402
from flowcoefficient.valves import VALVE_STYLES, get_valve_style  # noqa: E402


# Transcribed from Valmet/Neles 10CV20EN. Held here as a second copy on
# purpose: if someone edits a curve, this fails, and they have to decide
# whether they meant to.
PUBLISHED = {
    'globe': {
        'cv_over_d2': (0.22, 0.70, 1.65, 2.81, 4.06, 5.34, 6.43, 6.95, 7.80, 12.0),
        'fl': (0.93, 0.93, 0.92, 0.86, 0.85, 0.84, 0.83, 0.83, 0.83, 0.83),
        'xt': (0.69, 0.69, 0.72, 0.63, 0.61, 0.62, 0.65, 0.69, 0.71, 0.70),
    },
    'globe cage': {
        'cv_over_d2': (0.18, 0.36, 0.55, 0.98, 1.68, 2.35, 2.98, 3.81, 4.66, 8.89),
        'fl': (0.97, 0.97, 0.97, 0.95, 0.95, 0.95, 0.95, 0.95, 0.95, 0.95),
        'xt': (0.75, 0.75, 0.75, 0.75, 0.73, 0.71, 0.74, 0.74, 0.75, 0.75),
    },
    'butterfly': {
        'cv_over_d2': (0.91, 2.43, 4.38, 6.60, 9.42, 13.63, 20.23, 29.60, 41.36, 47.01),
        'fl': (0.87, 0.85, 0.82, 0.80, 0.78, 0.73, 0.66, 0.58, 0.46, 0.40),
        'xt': (0.68, 0.68, 0.66, 0.64, 0.58, 0.52, 0.41, 0.37, 0.22, 0.15),
    },
    'butterfly concentric': {
        'cv_over_d2': (0.20, 1.58, 3.81, 7.05, 11.50, 17.98, 27.31, 40.96, 58.95, 71.90),
        'fl': (0.83, 0.83, 0.83, 0.82, 0.78, 0.72, 0.65, 0.59, 0.53, 0.48),
        'xt': (0.46, 0.46, 0.46, 0.45, 0.41, 0.37, 0.35, 0.31, 0.29, 0.28),
    },
    'ball': {
        'cv_over_d2': (0.73, 1.60, 3.00, 5.29, 8.27, 12.62, 20.22, 33.33, 56.0, 156.0),
        'fl': (0.91, 0.91, 0.90, 0.88, 0.85, 0.80, 0.74, 0.67, 0.57, 0.28),
        'xt': (0.82, 0.82, 0.80, 0.75, 0.67, 0.57, 0.42, 0.30, 0.19, 0.05),
    },
    'segmented ball': {
        'cv_over_d2': (0.59, 1.45, 2.86, 4.93, 7.64, 11.0, 15.07, 20.67, 30.80, 48.90),
        'fl': (0.94, 0.93, 0.92, 0.88, 0.85, 0.81, 0.78, 0.72, 0.61, 0.42),
        'xt': (0.64, 0.64, 0.63, 0.62, 0.59, 0.54, 0.49, 0.40, 0.32, 0.16),
    },
    'eccentric plug': {
        'cv_over_d2': (1.12, 2.26, 3.29, 4.53, 5.81, 7.38, 9.44, 11.44, 13.44, 15.0),
        'fl': (0.91, 0.89, 0.87, 0.85, 0.83, 0.82, 0.80, 0.78, 0.77, 0.76),
        'xt': (0.62, 0.62, 0.62, 0.62, 0.61, 0.60, 0.56, 0.52, 0.45, 0.40),
    },
    'triple eccentric disc': {
        'cv_over_d2': (1.38, 3.02, 5.09, 7.76, 11.17, 15.69, 21.77, 29.96, 40.72, 54.75),
        'fl': (0.87, 0.85, 0.83, 0.81, 0.77, 0.73, 0.67, 0.60, 0.49, 0.36),
        'xt': (0.53, 0.53, 0.53, 0.52, 0.47, 0.41, 0.35, 0.27, 0.19, 0.11),
    },
}


class TestEveryPublishedNumber:
    @pytest.mark.parametrize('name', sorted(PUBLISHED))
    @pytest.mark.parametrize('array', ['cv_over_d2', 'fl', 'xt'])
    def test_matches_the_catalogue(self, name, array):
        assert getattr(CURVES[name], array) == PUBLISHED[name][array]

    def test_angle_is_deliberately_the_eccentric_plug_curve(self):
        """
        Identical by design, not by accident, and the substitution has to be
        declared or a caller cannot know the curve is for another geometry.
        """
        assert CURVES['angle'].cv_over_d2 == CURVES['eccentric plug'].cv_over_d2
        assert CURVES['angle'].fl == CURVES['eccentric plug'].fl
        assert CURVES['angle'].substituted_from
        assert not CURVES['eccentric plug'].substituted_from

    def test_no_other_pair_is_accidentally_identical(self):
        seen = {}
        for name, c in CURVES.items():
            if c.substituted_from:
                continue
            key = (c.cv_over_d2, c.fl, c.xt)
            assert key not in seen, f'{name} duplicates {seen[key]} with no substitution note'
            seen[key] = name

    def test_the_globe_dip_is_real_data_not_a_typo(self):
        """
        globe xT falls to 0.61 and climbs back. It is the only non-monotonic
        array in the file, it is in the catalogue as printed, and the equal
        percentage trim on the facing page prints the same numbers.
        """
        xt = CURVES['globe'].xt
        assert xt[2] > xt[4] < xt[8], 'the dip is the documented shape'
        assert min(xt) == 0.61


class TestStylesAndCurvesAgree:
    def test_every_curve_has_a_selectable_style(self):
        """
        The README listed two curves the code raised on. Twenty numbers of
        dead data presented as available.
        """
        assert set(CURVES) - set(VALVE_STYLES) == set()

    @pytest.mark.parametrize('name', sorted(CURVES))
    def test_the_declared_span_is_the_curve_span(self, name):
        """
        globe declared xT 0.69 to 0.75 against a curve dipping to 0.61, and
        angle declared 0.65 to 0.75 against a curve spanning 0.40 to 0.62,
        which do not even overlap. The spans are derived now, so they cannot
        drift, and this proves the derivation ran.
        """
        style, curve = get_valve_style(name), CURVES[name]
        assert style.fl_range == (min(curve.fl), max(curve.fl))
        assert style.xt_range == (min(curve.xt), max(curve.xt))

    @pytest.mark.parametrize('name', sorted(VALVE_STYLES))
    def test_the_placeholder_sits_inside_its_own_span(self, name):
        style = VALVE_STYLES[name]
        if name not in CURVES:
            return
        assert style.fl_range[0] <= style.fl <= style.fl_range[1]
        assert style.xt_range[0] <= style.xt <= style.xt_range[1]


class TestCaseInsensitiveStyleNames:
    """
    'Ball' passed style validation, missed the curve, fell back to the
    placeholder and returned an answer 85 percent different, with a note
    claiming no bore had been supplied.
    """

    @pytest.mark.parametrize('written', ['ball', 'Ball', 'BALL', ' ball '])
    def test_capitalisation_cannot_change_the_answer(self, written):
        r = gas_flow_coefficient(
            flow_rate=800, inlet_pressure=10.0, outlet_pressure=5.0,
            pressure_basis='absolute', temperature=20, fluid='air',
            valve_style=written, valve_diameter_mm=40, rated_kv=30)
        assert r.operating_point.located
        assert r.xt == pytest.approx(0.8072, abs=0.002)


class TestTheResultDoesNotContradictItself:
    """
    The operating point used to describe the first-pass estimate while the
    opening check described the answer. One result object said 34 percent and
    18 percent at the same time.
    """

    def test_operating_point_agrees_with_the_opening_check(self):
        r = gas_flow_coefficient(
            flow_rate=800, inlet_pressure=10.0, outlet_pressure=5.0,
            pressure_basis='absolute', temperature=20, fluid='air',
            valve_style='ball', valve_diameter_mm=40, rated_kv=30)
        assert r.operating_point.capacity_fraction == pytest.approx(
            r.opening.fraction, rel=1e-6)

    def test_the_reported_xt_is_the_one_that_produced_the_answer(self):
        r = gas_flow_coefficient(
            flow_rate=800, inlet_pressure=10.0, outlet_pressure=5.0,
            pressure_basis='absolute', temperature=20, fluid='air',
            valve_style='ball', valve_diameter_mm=40, rated_kv=30)
        assert r.xt == pytest.approx(r.operating_point.xt)

    def test_it_says_how_many_passes_it_took(self):
        r = gas_flow_coefficient(
            flow_rate=800, inlet_pressure=10.0, outlet_pressure=5.0,
            pressure_basis='absolute', temperature=20, fluid='air',
            valve_style='ball', valve_diameter_mm=40, rated_kv=30)
        assert 'converged in' in r.xt_source


class TestFlpOverFp:
    """
    The fourth item of the commit that introduced it had no test at all. It
    could be reverted to bare FL and nothing noticed, while it changes
    verdicts on real duties.
    """

    def test_flp_over_fp_is_below_the_bare_fl(self):
        g = piping_geometry_factor(63, 50, 80, fl=0.90)
        assert g.flp < 0.90
        assert g.effective_fl < 0.90
        assert g.effective_fl == pytest.approx(g.flp / g.fp, rel=1e-12)

    def test_flp_uses_the_inlet_fitting_only(self):
        """
        Choking is decided at the vena contracta, upstream of the outlet
        increaser, so only Z1 and ZB1 enter FLP. Building it from all the Z
        terms would give a different number, and did not fail any test.
        """
        import math
        from flowcoefficient.piping import N2
        d, d1 = 50.0, 80.0
        z1 = 0.5 * (1 - d ** 2 / d1 ** 2) ** 2
        zb1 = 1 - (d / d1) ** 4
        expected = 0.90 / math.sqrt(1 + (0.90 ** 2 / N2) * (z1 + zb1) * (63 / d ** 2) ** 2)
        assert piping_geometry_factor(63, d, d1, fl=0.90).flp == pytest.approx(expected, rel=1e-9)

    def test_reducers_can_choke_a_valve_that_bare_fl_calls_clear(self):
        bare = piping_geometry_factor(800, 100, 150, fl=0.90)
        assert bare.effective_fl < 0.80, (
            'if this stops holding, FLP is no longer being applied and a '
            'reduced bore installation will be reported clear when choked'
        )


class TestTheChokedClampIsPinned:
    """
    The module calls clamping x to Fg*xT its most consequential behaviour.
    A mutation removing it left every test green.
    """

    def test_gas_x_is_clamped_at_the_limit(self):
        r = gas_flow_coefficient(
            flow_rate=5000, inlet_pressure=45, outlet_pressure=5,
            pressure_basis='absolute', temperature=20, fluid='methane',
            valve_style='globe', valve_diameter_mm=50, rated_kv=63)
        assert r.is_choked
        assert r.effective_pressure_drop_ratio == pytest.approx(r.limiting_ratio)
        assert r.effective_pressure_drop_ratio < r.pressure_drop_ratio

    def test_gas_unclamped_would_give_a_different_coefficient(self):
        choked = gas_flow_coefficient(
            flow_rate=5000, inlet_pressure=45, outlet_pressure=5,
            pressure_basis='absolute', temperature=20, fluid='methane', xt=0.75)
        clear = gas_flow_coefficient(
            flow_rate=5000, inlet_pressure=45, outlet_pressure=5,
            pressure_basis='absolute', temperature=20, fluid='methane', xt=0.99)
        assert choked.cv != pytest.approx(clear.cv, rel=1e-3)

    def test_liquid_sizes_on_the_limited_pressure_drop_when_choked(self):
        r = liquid_flow_coefficient(
            flow_rate=25, inlet_pressure=30.0, outlet_pressure=2.0,
            pressure_basis='absolute', fluid='water', temperature=80,
            valve_style='segmented ball', valve_diameter_mm=50, rated_kv=40)
        if r.is_choked:
            assert r.effective_pressure_drop_bar < r.pressure_drop_bar
            assert r.effective_pressure_drop_bar == pytest.approx(
                (r.piping.effective_fl or r.fl) ** 2 * (
                    r.inlet_pressure_bar_a - r.ff * r.vapour_pressure_bar),
                rel=1e-3)
