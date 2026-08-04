"""
What the library refuses, and what it reports rather than refusing.

The rule: a nonsensical input raises; a physical operating state is
reported. Choking, cavitation risk and laminar flow are things that happen
in real plants, so they come back on the result. A negative absolute
pressure is not a plant condition, it is a mistake, and it stops.

The second rule, which these tests pin harder: the library never claims to
have checked something it did not check. is_choked False with
choked_check_performed False means "no data, did not look", and confusing
that with "looked, and it is clear" is how somebody installs a valve that
cavitates.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flowcoefficient import (  # noqa: E402
    InvalidFlowRateError,
    InvalidFluidPropertyError,
    InvalidPressureError,
    OutOfRangeError,
    UnknownFluidError,
    UnknownUnitError,
    gas_flow_coefficient,
    get_fluid,
    liquid_flow_coefficient,
)


class TestPressureBasisMustBeStated:
    """
    The single most valuable refusal in the library. A gauge reading treated
    as absolute produces a confident wrong answer with nothing in the output
    to reveal it.
    """

    def test_a_nonsense_basis_is_refused(self):
        with pytest.raises(InvalidPressureError, match='absolute'):
            liquid_flow_coefficient(
                flow_rate=25, inlet_pressure=6.0, outlet_pressure=4.0,
                pressure_basis='barg', relative_density=1.0,
            )

    def test_basis_has_no_default(self):
        """Calling without it must be a TypeError, not a silent assumption."""
        with pytest.raises(TypeError):
            liquid_flow_coefficient(  # noqa
                flow_rate=25, inlet_pressure=6.0, outlet_pressure=4.0,
                relative_density=1.0,
            )

    def test_gauge_and_absolute_give_different_answers(self):
        """If they agreed, the parameter would be decoration."""
        absolute = liquid_flow_coefficient(
            flow_rate=25, inlet_pressure=6.0, outlet_pressure=4.0,
            pressure_basis='absolute', relative_density=1.0)
        gauge = liquid_flow_coefficient(
            flow_rate=25, inlet_pressure=6.0, outlet_pressure=4.0,
            pressure_basis='gauge', relative_density=1.0)
        assert gauge.inlet_pressure_bar_a > absolute.inlet_pressure_bar_a
        assert gauge.pressure_basis == 'gauge'

    def test_a_gauge_value_below_vacuum_is_refused(self):
        with pytest.raises(InvalidPressureError, match='vacuum'):
            liquid_flow_coefficient(
                flow_rate=25, inlet_pressure=-2.0, outlet_pressure=-3.0,
                pressure_basis='gauge', relative_density=1.0,
            )


class TestImpossibleFlowConditions:
    def test_outlet_above_inlet(self):
        with pytest.raises(InvalidPressureError, match='pressure gradient'):
            liquid_flow_coefficient(
                flow_rate=25, inlet_pressure=4.0, outlet_pressure=6.0,
                pressure_basis='absolute', relative_density=1.0)

    def test_no_pressure_drop(self):
        with pytest.raises(InvalidPressureError):
            liquid_flow_coefficient(
                flow_rate=25, inlet_pressure=6.0, outlet_pressure=6.0,
                pressure_basis='absolute', relative_density=1.0)

    def test_negative_flow(self):
        with pytest.raises(InvalidFlowRateError):
            liquid_flow_coefficient(
                flow_rate=-25, inlet_pressure=6.0, outlet_pressure=4.0,
                pressure_basis='absolute', relative_density=1.0)

    def test_flow_and_thermal_duty_together(self):
        with pytest.raises(InvalidFlowRateError, match='not both'):
            liquid_flow_coefficient(
                flow_rate=25, thermal_duty=250, temperature_in=10,
                temperature_out=20, inlet_pressure=6.0, outlet_pressure=4.0,
                pressure_basis='absolute', fluid='water')

    def test_neither_flow_nor_duty(self):
        with pytest.raises(InvalidFlowRateError, match='not neither'):
            liquid_flow_coefficient(
                inlet_pressure=6.0, outlet_pressure=4.0,
                pressure_basis='absolute', relative_density=1.0)


class TestOutOfRangeInputs:
    def test_unknown_pressure_unit(self):
        with pytest.raises(UnknownUnitError):
            liquid_flow_coefficient(
                flow_rate=25, inlet_pressure=6.0, outlet_pressure=4.0,
                pressure_basis='absolute', relative_density=1.0,
                pressure_unit='furlongs')

    def test_unknown_fluid(self):
        with pytest.raises(UnknownFluidError, match='Known fluids'):
            get_fluid('unobtainium')

    def test_fl_outside_zero_to_one(self):
        with pytest.raises(OutOfRangeError):
            liquid_flow_coefficient(
                flow_rate=25, inlet_pressure=6.0, outlet_pressure=4.0,
                pressure_basis='absolute', relative_density=1.0, fl=1.4)

    def test_gamma_outside_physical_range(self):
        with pytest.raises(OutOfRangeError):
            gas_flow_coefficient(
                flow_rate=500, inlet_pressure=7.0, outlet_pressure=5.0,
                pressure_basis='absolute', temperature=20,
                relative_density=1.0, gamma=3.5, xt=0.75)


class TestAntoineRefusesToExtrapolate:
    """
    An extrapolated vapour pressure is not approximately right, it is
    confidently wrong, and it feeds the cavitation check.
    """

    def test_above_the_fitted_range(self):
        with pytest.raises(OutOfRangeError, match='confidently wrong'):
            get_fluid('water').vapour_pressure_bar(500.0)

    def test_below_the_fitted_range(self):
        with pytest.raises(OutOfRangeError):
            get_fluid('water').vapour_pressure_bar(200.0)

    def test_the_error_says_how_to_proceed(self):
        with pytest.raises(OutOfRangeError, match='Pass vapour_pressure'):
            get_fluid('water').vapour_pressure_bar(500.0)


class TestDidNotCheckIsNotTheSameAsClear:
    """The distinction the whole result object design exists to preserve."""

    def test_liquid_without_fl_reports_no_check(self):
        r = liquid_flow_coefficient(
            flow_rate=25, inlet_pressure=6.0, outlet_pressure=4.0,
            pressure_basis='absolute', relative_density=1.0)
        assert r.choked_check_performed is False
        assert r.is_choked is False
        assert 'not performed' in str(r)

    def test_liquid_with_data_reports_a_real_check(self):
        r = liquid_flow_coefficient(
            flow_rate=25, inlet_pressure=6.0, outlet_pressure=4.0,
            pressure_basis='absolute', fluid='water', temperature=80,
            valve_style='globe')
        assert r.choked_check_performed is True
        assert r.fl_source == 'typical for globe'

    def test_supplied_fl_beats_the_style_default(self):
        r = liquid_flow_coefficient(
            flow_rate=25, inlet_pressure=6.0, outlet_pressure=4.0,
            pressure_basis='absolute', fluid='water', temperature=80,
            valve_style='ball', fl=0.93)
        assert r.fl == 0.93
        assert r.fl_source == 'supplied'

    def test_gas_without_xt_reports_no_check_at_low_x(self):
        """
        Below x = 0.1 the true expansion factor is within a few percent of 1,
        so proceeding without xT is defensible. The result still has to say
        it did not check, and say the Y it used was assumed.
        """
        r = gas_flow_coefficient(
            flow_rate=500, inlet_pressure=7.0, outlet_pressure=6.7,
            pressure_basis='absolute', temperature=20, fluid='air')
        assert r.choked_check_performed is False
        assert r.xt_source == 'not provided'
        assert 'assumed' in r.expansion_factor_source
        assert 'assumed' in str(r)

    def test_gas_without_xt_refuses_once_x_is_large(self):
        """
        Y is in the denominator, so Y = 1 gives the smallest coefficient the
        equation can produce, up to a third below the choked value. It is the
        most optimistic assumption available, and the failure is an
        undersized valve. Past x = 0.1 the library refuses rather than
        returning it.
        """
        with pytest.raises(InvalidFluidPropertyError, match='undersizes'):
            gas_flow_coefficient(
                flow_rate=500, inlet_pressure=7.0, outlet_pressure=5.0,
                pressure_basis='absolute', temperature=20, fluid='air')

    def test_regime_without_viscosity_reports_no_check(self):
        r = liquid_flow_coefficient(
            flow_rate=25, inlet_pressure=6.0, outlet_pressure=4.0,
            pressure_basis='absolute', relative_density=1.0)
        assert r.flow_regime.checked is False
        assert r.flow_regime.regime == 'not checked'


class TestTheBallValveAccident:
    """
    The case the no-default rule on xT exists to prevent. Same duty, two
    valve styles, and only one of them is choked.
    """

    DUTY = dict(
        flow_rate=500, inlet_pressure=7.0, outlet_pressure=5.0,
        pressure_basis='absolute', temperature=20, fluid='air',
    )

    def test_globe_is_not_choked(self):
        assert gas_flow_coefficient(**self.DUTY, valve_style='globe').is_choked is False

    def test_ball_is_choked_on_the_identical_duty(self):
        assert gas_flow_coefficient(**self.DUTY, valve_style='ball').is_choked is True

    def test_the_ball_valve_needs_more_capacity(self):
        globe = gas_flow_coefficient(**self.DUTY, valve_style='globe')
        ball = gas_flow_coefficient(**self.DUTY, valve_style='ball')
        assert ball.cv > globe.cv * 1.4, (
            'a library defaulting xT to the globe value would report the same '
            'coefficient for both and undersize the ball valve'
        )
