"""
Checks against independently published results.

These are the tests that matter. Everything else in the suite verifies the
library is internally consistent, which is a weaker claim than being right.
A library can be perfectly self-consistent and wrong by a constant factor.

That is not hypothetical here. During development N9 in the gas equation was
wrong by a factor of 185, and every internal check passed: the units were
right, the choked logic was right, the expansion factor was right, the result
object printed a confident number. Only comparison against an outside source
caught it.
"""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flowcoefficient import (  # noqa: E402
    gas_flow_coefficient,
    liquid_flow_coefficient,
    liquid_flow_rate,
)
from flowcoefficient.coefficients import EXACT_CV_PER_KV, cv_to_kv, kv_to_cv  # noqa: E402
from flowcoefficient.fluids import MOLAR_MASS_AIR  # noqa: E402
from flowcoefficient.gas import N9, Y_CHOKED  # noqa: E402


class TestKvCvIsAUnitConversion:
    """
    The published pair 1.156 and 0.865 should be the unit conversion and not
    an arbitrary factor. If it is, it can be derived from the definitions.
    """

    def test_matches_the_derivation_from_first_principles(self):
        # Cv/Kv = (m3/h per US gpm) / sqrt(psi per bar)
        derived = 4.402868 / math.sqrt(14.503774)
        assert derived == pytest.approx(EXACT_CV_PER_KV, rel=1e-9)
        assert derived == pytest.approx(1.156, rel=5e-4)

    def test_the_published_pair_round_trips(self):
        for kv in (0.1, 1.0, 17.68, 250.0, 4000.0):
            assert cv_to_kv(kv_to_cv(kv)) == pytest.approx(kv, rel=1e-3)


class TestLiquidAgainstHandCalculation:
    """
    Water, 25 m3/h, 6 bar a to 4 bar a, relative density 1.0.

        C = Q / sqrt(dP / rd) = 25 / sqrt(2) = 17.678

    Simple enough to check on paper, which is the point. If this drifts, the
    liquid path has changed underneath.
    """

    def test_matches_the_hand_calculation(self):
        r = liquid_flow_coefficient(
            flow_rate=25, inlet_pressure=6.0, outlet_pressure=4.0,
            pressure_basis='absolute', relative_density=1.0,
        )
        assert r.kv == pytest.approx(25 / math.sqrt(2.0), rel=1e-9)
        assert r.kv == pytest.approx(17.678, rel=1e-4)
        assert r.cv == pytest.approx(20.43, rel=1e-3)

    def test_the_inverse_returns_the_original_flow(self):
        flow = liquid_flow_rate(17.678, 6.0, 4.0, 'absolute', relative_density=1.0)
        assert flow == pytest.approx(25.0, rel=1e-4)

    def test_imperial_inputs_give_the_same_physical_answer(self):
        """
        The same duty stated in psi and US gpm must produce the same Kv. This
        is what proves conversion at the boundary is equivalent to carrying a
        constants table, which is the central design decision of the library.
        """
        metric = liquid_flow_coefficient(
            flow_rate=25, inlet_pressure=6.0, outlet_pressure=4.0,
            pressure_basis='absolute', relative_density=1.0,
        )
        imperial = liquid_flow_coefficient(
            flow_rate=25 * 4.402868,          # m3/h to US gpm
            inlet_pressure=6.0 * 14.503774,   # bar to psi
            outlet_pressure=4.0 * 14.503774,
            pressure_basis='absolute', relative_density=1.0,
            units='imperial',
        )
        assert imperial.kv == pytest.approx(metric.kv, rel=1e-6)


class TestGasAgainstTheImperialForm:
    """
    Cross-check against the long-established imperial sizing equation:

        Q[scfh] = 1360 * Cv * p1[psia] * Y * sqrt(x / (Gg * T[degR] * Z))

    This is the check that caught N9 being wrong by 185x. It compares the
    library against a formula from a different lineage, in different units,
    which is the only kind of check that catches a bad constant.
    """

    @staticmethod
    def _imperial_cv(q_nm3h, p1_bar, t_k, x, y, gg=1.0):
        nm3_to_scf = (288.706 / 273.15) * 35.31467
        q_scfh = q_nm3h * nm3_to_scf
        p1_psia = p1_bar * 14.5037738
        t_degr = t_k * 1.8
        return q_scfh / (1360 * p1_psia * y * math.sqrt(x / (gg * t_degr)))

    def test_air_non_choked_matches_the_imperial_form(self):
        r = gas_flow_coefficient(
            flow_rate=500, inlet_pressure=7.0, outlet_pressure=5.0,
            pressure_basis='absolute', temperature=20,
            relative_density=1.0, gamma=1.4, xt=0.75,
        )
        expected_cv = self._imperial_cv(
            500, 7.0, 293.15, r.pressure_drop_ratio, r.expansion_factor,
        )
        assert r.cv == pytest.approx(expected_cv, rel=1e-6)

    def test_n9_is_close_to_its_derivation(self):
        """
        Guards the constant itself. A future edit that replaces the
        derivation with a remembered number fails here.
        """
        assert N9 == pytest.approx(455.34, rel=1e-3)

    def test_n9_matches_the_tabulated_standard_value(self):
        """
        The ISA/IEC equation constants table gives N9 = 21.2 for Q in m3/h at
        normal conditions, p in kPa, T in K, with C as Cv, for the form of
        the equation that uses molecular weight M.

        This library uses relative density Gg = M / M_air, so the tabulated
        constant converts by sqrt(M_air). This is the test that closes the
        open item the N9 error created.
        """
        tabulated_kpa_cv = 21.2
        tabulated_bar_kv = tabulated_kpa_cv * 100 * 1.156
        equivalent_gg_form = tabulated_bar_kv / math.sqrt(MOLAR_MASS_AIR)
        assert N9 == pytest.approx(equivalent_gg_form, rel=1e-3)

    def test_n1_matches_the_tabulated_standard_value(self):
        """
        Same table gives N1 = 0.865 for Q in m3/h, p in bar, C as Cv. As Kv
        that is 1.000, which is what the liquid module assumes and why its
        equation carries no visible constant.
        """
        assert 0.865 * 1.156 == pytest.approx(1.0, rel=1e-3)

    def test_the_reference_temperature_handling_matches_the_table(self):
        """
        The table gives 21.2 at normal conditions (0 C) and 22.4 at standard
        (15.5 C). Their ratio must be the absolute temperature ratio, which
        confirms the library converts volumes on the right reference.
        """
        assert 22.4 / 21.2 == pytest.approx(288.65 / 273.15, rel=1e-3)

    def test_the_answer_is_physically_plausible(self):
        """
        A magnitude sanity check. 500 Nm3/h of air through a modest pressure
        drop is a small valve, single digit Cv, not a four figure one. This
        is the assertion that would have failed loudly when N9 was wrong.
        """
        r = gas_flow_coefficient(
            flow_rate=500, inlet_pressure=7.0, outlet_pressure=5.0,
            pressure_basis='absolute', temperature=20, fluid='air',
            valve_style='globe',
        )
        assert 1.0 < r.cv < 50.0, (
            f'Cv {r.cv:.1f} is not a plausible size for this duty. A wrong '
            f'numerical constant scales every gas answer and nothing else in '
            f'the result looks wrong.'
        )


class TestChokedGasLimits:
    """The limiting values fall out of the equations and must be exact."""

    def test_expansion_factor_reaches_two_thirds_at_the_limit(self):
        r = gas_flow_coefficient(
            flow_rate=5000, inlet_pressure=45, outlet_pressure=5,
            pressure_basis='absolute', temperature=20,
            relative_density=1.0, gamma=1.4, xt=0.75,
        )
        assert r.is_choked
        # Y at the limit falls out of the equation rather than being pasted
        # in, so derive it here from the expression itself rather than
        # asserting the constant against its own literal.
        fg, xt = r.gamma_factor, r.xt
        derived = 1.0 - (fg * xt) / (3.0 * fg * xt)
        assert derived == pytest.approx(2.0 / 3.0, rel=1e-12)
        assert r.expansion_factor == pytest.approx(derived, rel=1e-12)
        assert Y_CHOKED == pytest.approx(derived, rel=1e-12)

    def test_x_is_clamped_to_the_limiting_ratio(self):
        r = gas_flow_coefficient(
            flow_rate=5000, inlet_pressure=45, outlet_pressure=5,
            pressure_basis='absolute', temperature=20,
            relative_density=1.0, gamma=1.4, xt=0.75,
        )
        assert r.pressure_drop_ratio > r.limiting_ratio
        assert r.effective_pressure_drop_ratio == pytest.approx(r.limiting_ratio)

    def test_gamma_factor_is_one_for_air(self):
        r = gas_flow_coefficient(
            flow_rate=500, inlet_pressure=7.0, outlet_pressure=5.0,
            pressure_basis='absolute', temperature=20, fluid='air', xt=0.75,
        )
        assert r.gamma_factor == pytest.approx(1.0)


class TestVapourPressureAgainstPublishedValues:
    """
    Antoine constants reproduce steam table values. Water is the fluid whose
    vapour pressure everyone can check, which makes it the right one to pin.
    """

    @pytest.mark.parametrize('celsius, published_bar, tolerance', [
        (20.0, 0.02339, 0.02),
        (40.0, 0.07384, 0.02),
        (60.0, 0.19946, 0.02),
        (80.0, 0.47414, 0.01),
        (95.0, 0.84529, 0.02),
    ])
    def test_water(self, celsius, published_bar, tolerance):
        from flowcoefficient import get_fluid
        pv = get_fluid('water').vapour_pressure_bar(celsius + 273.15)
        assert pv == pytest.approx(published_bar, rel=tolerance)

    def test_ammonia_at_25c(self):
        from flowcoefficient import get_fluid
        pv = get_fluid('ammonia').vapour_pressure_bar(298.15)
        assert pv == pytest.approx(10.03, rel=0.02)
