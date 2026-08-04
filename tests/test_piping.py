"""
Piping geometry factor Fp, and the constant behind it.

N2 gets the same treatment N9 got. It is derived rather than quoted, and the
derivation is asserted here, because a constant that is wrong scales every
answer that uses it and nothing in the output looks wrong.
"""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flowcoefficient import liquid_flow_coefficient  # noqa: E402
from flowcoefficient.errors import OutOfRangeError  # noqa: E402
from flowcoefficient.piping import N2, N2_INCH_CV, piping_geometry_factor  # noqa: E402
from flowcoefficient.regime import N2 as REGIME_N2  # noqa: E402


class TestN2IsSelfConsistent:
    """
    N2 sits under (C / d^2)^2, so the imperial and metric constants must
    differ by exactly the fourth power of the inch-to-millimetre ratio. That
    makes the published pair check itself.
    """

    def test_the_metric_and_imperial_constants_differ_by_the_unit_ratio(self):
        published_mm_cv = 0.00214
        assert N2_INCH_CV / published_mm_cv == pytest.approx(25.4 ** 4, rel=1e-3)

    def test_the_library_constant_is_the_published_one_converted_to_kv(self):
        published_mm_cv = 0.00214
        assert N2 == pytest.approx(published_mm_cv * 1.156 ** 2, rel=1e-3)

    def test_the_reynolds_screening_uses_the_same_constant(self):
        """
        Two copies of a constant are two copies that drift. regime.py held
        1.60e-3 for a while, which was simply wrong.
        """
        assert REGIME_N2 == N2


class TestFpAgainstHandCalculation:
    """
    A DN50 valve of rated Kv 63 in a DN80 line, worked through on paper:

        d^2/D^2   = 2500 / 6400          = 0.390625
        (1 - that) = 0.609375, squared    = 0.371338
        sum_Z      = 1.5 * 0.371338       = 0.557007
        (C/d^2)^2  = (63/2500)^2          = 0.000635
        Fp         = 1/sqrt(1 + (0.557007/0.00286) * 0.000635)
                                          = 0.9434
    """

    def test_matches_the_hand_calculation(self):
        assert piping_geometry_factor(63, 50, 80).fp == pytest.approx(0.9434, rel=1e-3)

    def test_the_terms_are_reported_so_the_number_can_be_checked(self):
        g = piping_geometry_factor(63, 50, 80)
        expected_sum_z = 1.5 * (1 - 50 ** 2 / 80 ** 2) ** 2
        assert g.sum_z == pytest.approx(expected_sum_z, rel=1e-9)

    def test_identical_reducers_cancel_the_bernoulli_terms(self):
        """
        With D1 = D2 the two Bernoulli terms are equal and cancel, leaving
        sum_Z = 1.5 (1 - d^2/D^2)^2. Worth pinning because that
        simplification is what most references print.
        """
        d, D = 50.0, 80.0
        g = piping_geometry_factor(63, d, D, D)
        assert g.sum_z == pytest.approx(1.5 * (1 - d ** 2 / D ** 2) ** 2, rel=1e-9)


class TestFpBehaviour:
    def test_a_line_size_valve_needs_no_correction(self):
        assert piping_geometry_factor(63, 50, 50).fp == 1.0

    def test_fp_is_never_above_one(self):
        for d, D in ((25, 80), (50, 80), (50, 100), (80, 100), (100, 100)):
            assert piping_geometry_factor(63, d, D).fp <= 1.0

    def test_a_bigger_mismatch_costs_more_capacity(self):
        loose = piping_geometry_factor(63, 50, 80).fp
        tighter = piping_geometry_factor(63, 25, 80).fp
        assert tighter < loose

    def test_a_larger_valve_coefficient_costs_more(self):
        """
        Fp falls as the valve gets more capacious relative to its bore,
        because the reducers become the limiting restriction.
        """
        assert piping_geometry_factor(100, 50, 80).fp < piping_geometry_factor(40, 50, 80).fp


class TestItSaysWhenItDidNotApply:
    """Same rule as everywhere else in this library."""

    @pytest.mark.parametrize('args', [
        (None, 50, 80),      # no rated Kv
        (63, None, 80),      # no valve bore
        (63, 50, None),      # no line bore
    ])
    def test_missing_input_returns_not_applied_with_fp_of_one(self, args):
        g = piping_geometry_factor(*args)
        assert g.checked is False
        assert g.fp == 1.0
        assert 'optimistic' in g.note

    def test_the_sizing_result_carries_the_bare_and_installed_values(self):
        r = liquid_flow_coefficient(
            flow_rate=25, inlet_pressure=6.0, outlet_pressure=4.0,
            pressure_basis='absolute', relative_density=1.0,
            valve_style='globe', rated_kv=63,
            valve_diameter_mm=50, pipe_diameter_mm=80)
        assert r.kv > r.kv_bare_valve
        assert r.kv == pytest.approx(r.kv_bare_valve / r.piping.fp, rel=1e-9)

    def test_without_diameters_the_result_is_unchanged(self):
        with_pipe = liquid_flow_coefficient(
            flow_rate=25, inlet_pressure=6.0, outlet_pressure=4.0,
            pressure_basis='absolute', relative_density=1.0)
        assert with_pipe.piping.checked is False
        assert with_pipe.kv == pytest.approx(with_pipe.kv_bare_valve, rel=1e-12)


class TestRefusals:
    def test_a_valve_larger_than_its_line_is_refused(self):
        with pytest.raises(OutOfRangeError, match='larger than the line'):
            piping_geometry_factor(63, 100, 80)

    def test_a_negative_diameter_is_refused(self):
        with pytest.raises(OutOfRangeError):
            piping_geometry_factor(63, -50, 80)
