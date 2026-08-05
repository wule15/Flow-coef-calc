"""
Coefficients that follow the valve opening.

Why this exists. FL and xT are published against Cv/d-squared, not as one
number per valve style. A full bore ball's xT runs 0.82 nearly closed to 0.05
wide open. The library used to carry a single mid-travel placeholder, which
threw that away and made the choked check depend on a guess.

These tests pin the curve, the interpolation, the refusal to extrapolate, and
the two things a caller actually needs told: where the duty sits on the valve,
and whether the valve will do the job well rather than merely pass the flow.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flowcoefficient import gas_flow_coefficient, liquid_flow_coefficient  # noqa: E402
from flowcoefficient.travel import (  # noqa: E402
    CURVES,
    GOOD_OPENING_HIGH,
    GOOD_OPENING_LOW,
    MM_PER_INCH,
    NOT_LOCATED,
    locate,
)


class TestTheCurvesAreWellFormed:
    @pytest.mark.parametrize('name', list(CURVES))
    def test_all_three_arrays_are_the_same_length(self, name):
        c = CURVES[name]
        assert len(c.cv_over_d2) == len(c.fl) == len(c.xt) == 10

    @pytest.mark.parametrize('name', list(CURVES))
    def test_the_abscissa_increases(self, name):
        xs = CURVES[name].cv_over_d2
        assert all(b > a for a, b in zip(xs, xs[1:])), f'{name} is not monotonic'

    @pytest.mark.parametrize('name', list(CURVES))
    def test_coefficients_stay_physical(self, name):
        c = CURVES[name]
        assert all(0 < v <= 1 for v in c.fl)
        assert all(0 < v <= 1 for v in c.xt)

    @pytest.mark.parametrize('name', list(CURVES))
    def test_every_curve_names_its_source(self, name):
        assert CURVES[name].source

    def test_a_rotary_valve_loses_recovery_as_it_opens(self):
        """
        The physical claim behind the whole module. A ball opens into a
        straighter path, recovers more pressure, and chokes earlier.
        """
        ball = CURVES['ball']
        assert ball.fl[0] > ball.fl[-1]
        assert ball.xt[0] > ball.xt[-1]
        assert ball.xt[0] / ball.xt[-1] > 10, 'the factor of sixteen claim'


class TestInterpolation:
    def test_a_tabulated_point_returns_its_own_value(self):
        c = CURVES['ball']
        fl, xt = c.at(c.cv_over_d2[3])
        assert (fl, xt) == (c.fl[3], c.xt[3])

    def test_between_points_lands_between_values(self):
        c = CURVES['ball']
        mid = (c.cv_over_d2[2] + c.cv_over_d2[3]) / 2
        fl, xt = c.at(mid)
        assert c.fl[3] < fl < c.fl[2]
        assert c.xt[3] < xt < c.xt[2]

    def test_it_holds_the_end_value_rather_than_extrapolating(self):
        """
        Same reasoning as the Antoine range. A fitted curve outside its fit is
        not approximately right, it is confidently wrong.
        """
        c = CURVES['ball']
        assert c.at(0.0001) == (c.fl[0], c.xt[0])
        assert c.at(10_000.0) == (c.fl[-1], c.xt[-1])


class TestLocatingTheDuty:
    def test_the_abscissa_is_cv_over_bore_in_inches_squared(self):
        """
        Confirmed against the catalogue: a DN25 valve of rated Cv 12
        tabulates a maximum Cv/d-squared of 12.0.
        """
        p = locate('ball', 100.0, 400.0, 50.0)
        expected = (100.0 * 1.156) / ((50.0 / MM_PER_INCH) ** 2)
        assert p.cv_over_d2 == pytest.approx(expected, rel=1e-9)

    def test_wide_open_means_this_valve_not_the_end_of_the_curve(self):
        """
        A DN100 ball rated Kv 800 never reaches the curve's last point, so
        its own wide open figure has to be read at its rated Cv/d-squared.
        """
        p = locate('ball', 200.0, 800.0, 100.0)
        assert p.xt_wide_open != CURVES['ball'].xt[-1]
        assert p.xt_wide_open == pytest.approx(0.185, abs=0.01)

    def test_a_more_closed_valve_has_a_higher_xt(self):
        tight = locate('ball', 100.0, 800.0, 100.0)
        open_ = locate('ball', 600.0, 800.0, 100.0)
        assert tight.xt > open_.xt

    @pytest.mark.parametrize('args', [
        ('ball', 100.0, None, 100.0),
        ('ball', 100.0, 800.0, None),
        ('no such style', 100.0, 800.0, 100.0),
    ])
    def test_missing_input_returns_not_located(self, args):
        assert locate(*args) is NOT_LOCATED or locate(*args).located is False


class TestItSaysWhetherTheValveWillDoTheJobWell:
    """
    The distinction asked for: a valve can pass the flow without being a
    sensible choice for it.
    """

    def test_an_oversized_valve_is_told_it_will_work_but_not_at_its_best(self):
        p = locate('ball', 60.0, 800.0, 100.0)
        assert p.capacity_fraction < GOOD_OPENING_LOW
        assert 'not at its best' in p.note
        assert 'smaller valve' in p.note

    def test_a_valve_near_its_limit_is_told_there_is_no_margin(self):
        p = locate('ball', 700.0, 800.0, 100.0)
        assert p.capacity_fraction > GOOD_OPENING_HIGH
        assert 'margin' in p.note

    def test_a_well_matched_valve_is_told_so(self):
        p = locate('ball', 400.0, 800.0, 100.0)
        assert GOOD_OPENING_LOW <= p.capacity_fraction <= GOOD_OPENING_HIGH
        assert 'works well' in p.note

    def test_a_large_difference_from_the_rated_figure_is_called_out(self):
        p = locate('ball', 60.0, 800.0, 100.0)
        assert 'misjudged the choked point' in p.note


class TestTheSizingFunctionsUseIt:
    DUTY = dict(flow_rate=800, inlet_pressure=10.0, outlet_pressure=5.0,
                pressure_basis='absolute', temperature=20, fluid='air',
                valve_style='ball')

    def test_gas_reads_xt_off_the_curve_when_it_can(self):
        r = gas_flow_coefficient(**self.DUTY, valve_diameter_mm=40, rated_kv=30)
        assert r.operating_point.located
        assert 'published curve' in r.xt_source
        assert r.xt == pytest.approx(r.operating_point.xt)

    def test_gas_falls_back_to_the_placeholder_without_a_bore(self):
        r = gas_flow_coefficient(**self.DUTY)
        assert r.operating_point.located is False
        assert 'placeholder' in r.xt_source

    def test_a_supplied_xt_is_never_overridden_by_the_curve(self):
        r = gas_flow_coefficient(**self.DUTY, valve_diameter_mm=40,
                                 rated_kv=30, xt=0.33)
        assert r.xt == 0.33
        assert r.xt_source == 'supplied'

    def test_valve_size_changes_the_answer(self):
        """
        The whole point. Same duty, three ball valves, three different xT and
        therefore three different coefficients.
        """
        small = gas_flow_coefficient(**self.DUTY, valve_diameter_mm=25, rated_kv=12)
        large = gas_flow_coefficient(**self.DUTY, valve_diameter_mm=80, rated_kv=130)
        assert small.xt != large.xt
        assert small.cv != large.cv

    def test_liquid_reads_fl_off_the_curve(self):
        r = liquid_flow_coefficient(
            flow_rate=25, inlet_pressure=6.0, outlet_pressure=4.0,
            pressure_basis='absolute', fluid='water', temperature=80,
            valve_style='ball', valve_diameter_mm=50, rated_kv=40)
        assert r.operating_point.located
        assert 'published curve' in r.fl_source
