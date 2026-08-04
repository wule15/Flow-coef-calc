"""
Velocity, oversizing, and the gas path having the same checks as the liquid one.

There was no test file for checks.py, and a mutation probe showed it: the API
RP 14E erosional constant could be changed from 122 to 200 with every test
still passing.

Worse, the gas rho v squared criterion was unreachable. is_gas=True appeared
nowhere in the package, so GAS_RHO_V_SQUARED_LIMIT was dead code while the
README implied velocity checking was general. Gases go through valves
constantly; the gap was that the gas sizing function never called any of it.
"""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flowcoefficient import gas_flow_coefficient, liquid_flow_coefficient  # noqa: E402
from flowcoefficient.checks import (  # noqa: E402
    EROSIONAL_C_CONTINUOUS,
    EROSIONAL_C_INTERMITTENT,
    GAS_RHO_V_SQUARED_LIMIT,
    check_opening,
    check_velocity,
)


class TestErosionalVelocityConstant:
    """
    API RP 14E gives v = C / sqrt(rho) with C = 100 for continuous service,
    in feet per second against pounds per cubic foot. The metric constant is
    that converted, so it is derivable rather than remembered.
    """

    def test_continuous_is_the_api_constant_converted(self):
        derived = 100 * 0.3048 * math.sqrt(16.0185)
        assert EROSIONAL_C_CONTINUOUS == pytest.approx(derived, rel=1e-3)

    def test_intermittent_is_the_same_conversion_at_c_125(self):
        derived = 125 * 0.3048 * math.sqrt(16.0185)
        assert EROSIONAL_C_INTERMITTENT == pytest.approx(derived, rel=5e-3)

    def test_water_erosional_limit_is_about_four_metres_per_second(self):
        """Sanity anchor. Everyone in process knows this number."""
        c = check_velocity(1.0, 50.0, 999.1)
        assert c.erosional_limit_ms == pytest.approx(3.86, abs=0.1)

    def test_intermittent_service_allows_more(self):
        cont = check_velocity(50, 50, 999.1, intermittent=False)
        inter = check_velocity(50, 50, 999.1, intermittent=True)
        assert inter.erosional_limit_ms > cont.erosional_limit_ms


class TestVelocityArithmetic:
    def test_velocity_is_flow_over_area(self):
        d_mm, q = 52.5, 21.5
        expected = (q / 3600) / (math.pi * (d_mm / 1000) ** 2 / 4)
        assert check_velocity(q, d_mm, 999.1).velocity_ms == pytest.approx(expected)

    def test_a_narrower_pipe_is_faster(self):
        assert check_velocity(25, 25, 999.1).velocity_ms > check_velocity(25, 50, 999.1).velocity_ms

    def test_no_diameter_means_not_checked_rather_than_no_warning(self):
        c = check_velocity(25, None, 999.1)
        assert c.checked is False
        assert c.velocity_ms is None


class TestGasHasTheSameChecksAsLiquid:
    """
    The gap this file exists for. Gas sizing did not call Fp, the velocity
    check or the oversizing check, so a gas duty got a bare coefficient while
    an identical liquid duty got four checks.
    """

    GAS = dict(flow_rate=5000, inlet_pressure=45, outlet_pressure=5,
               pressure_basis='absolute', temperature=20, fluid='methane',
               valve_style='globe', valve_diameter_mm=50,
               pipe_diameter_mm=80, rated_kv=63)

    def test_fp_is_applied_to_gas(self):
        r = gas_flow_coefficient(**self.GAS)
        assert r.piping.checked is True
        assert r.piping.fp < 1.0
        assert r.kv == pytest.approx(r.kv_bare_valve / r.piping.fp, rel=1e-9)

    def test_velocity_is_checked_on_gas(self):
        r = gas_flow_coefficient(**self.GAS)
        assert r.velocity.checked is True
        assert r.velocity.velocity_ms > 0

    def test_the_rho_v_squared_criterion_is_reachable(self):
        """It was dead code. This is the test that keeps it alive."""
        r = gas_flow_coefficient(**self.GAS)
        assert r.velocity.rho_v_squared is not None
        assert r.velocity.rho_v_squared > GAS_RHO_V_SQUARED_LIMIT
        assert any('rho v squared' in w for w in r.velocity.warnings)

    def test_the_oversizing_check_runs_on_gas(self):
        r = gas_flow_coefficient(**self.GAS)
        assert r.opening.checked is True
        assert r.opening.fraction < 0.20
        assert any('oversized' in w for w in r.opening.warnings)

    def test_gas_velocity_is_evaluated_at_the_outlet(self):
        """
        Gas expands through the valve, so the outlet is where density is
        lowest and velocity highest. Evaluating at the inlet would report a
        comfortable number for a line that is eroding.
        """
        low_drop = dict(self.GAS, outlet_pressure=40)
        big_drop = dict(self.GAS, outlet_pressure=5)
        assert (gas_flow_coefficient(**big_drop).velocity.velocity_ms
                > gas_flow_coefficient(**low_drop).velocity.velocity_ms)

    def test_without_a_line_size_gas_says_not_checked(self):
        r = gas_flow_coefficient(
            flow_rate=5000, inlet_pressure=45, outlet_pressure=5,
            pressure_basis='absolute', temperature=20, fluid='methane',
            valve_style='globe')
        assert r.velocity.checked is False
        assert r.piping.checked is False


class TestOpeningBand:
    def test_a_duty_in_the_band_raises_nothing(self):
        assert check_opening(30, 63).warnings == ()

    def test_undersized_is_called_out(self):
        assert 'undersized' in check_opening(70, 63).warnings[0]

    def test_the_fraction_is_capacity_not_travel(self):
        assert check_opening(17.6, 63).fraction == pytest.approx(17.6 / 63)


class TestLiquidStillHasEverythingItHad:
    """Guard against the gas work quietly removing something from liquid."""

    def test_all_four_checks_present(self):
        r = liquid_flow_coefficient(
            flow_rate=25, inlet_pressure=6.0, outlet_pressure=4.0,
            pressure_basis='absolute', fluid='water', temperature=80,
            valve_style='globe', rated_kv=63, valve_diameter_mm=50,
            pipe_diameter_mm=80, kinematic_viscosity=1.0)
        assert r.piping.checked
        assert r.velocity.checked
        assert r.opening.checked
        assert r.flow_regime.checked
        assert r.choked_check_performed
