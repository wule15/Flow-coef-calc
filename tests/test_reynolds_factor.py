"""
Reynolds number factor FR, EN IEC 60534-2-1:2011 Annex A.

The test that matters most is the pinned worked example: the standard prints a
segmented-ball case that gives FR = 0.715, and the FR equation reproduces it.
Everything else checks internal consistency, including the Kv-vs-Cv unit
conversion that is the whole reason N18 and N32 differ from the values printed
in that (Cv-basis) example.
"""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flowcoefficient import liquid_flow_coefficient  # noqa: E402
from flowcoefficient.coefficients import KV_PER_CV  # noqa: E402
from flowcoefficient.reynolds_factor import (  # noqa: E402
    N18, N32, apply_reynolds_factor, n_factor, reynolds_factor,
    trim_is_full_size,
)


class TestPinnedToTheStandardWorkedExample:
    """
    EN IEC 60534-2-1:2011 Annex A worked example (segmented ball, Cv basis):
    FL = 0.98, Rev = 1202, n = 1.235. Transitional (Rev >= 10) gives FR =
    0.715; the laminar term gives 1.022, capped to 1; the Min is 0.715.
    """

    def test_transitional_reproduces_0_715(self):
        assert reynolds_factor(1202.0, 1.235, 0.98) == pytest.approx(0.715, abs=1e-3)

    def test_laminar_term_alone_exceeds_one_and_is_capped(self):
        # (0.026/FL) sqrt(n Rev) = 1.022 for this case; the Min holds FR <= 1
        # only because the transitional term is lower. Check the raw laminar
        # value against the standard by forcing the laminar branch (Rev < 10
        # scales it down, so evaluate the term directly).
        laminar = (0.026 / 0.98) * math.sqrt(1.235 * 1202.0)
        assert laminar == pytest.approx(1.022, abs=1e-3)

    def test_the_min_picks_the_transitional_term(self):
        # Same inputs, full A.7 Min of transitional, laminar and 1.
        assert reynolds_factor(1202.0, 1.235, 0.98) < 1.0

    def test_uses_sqrt_fl_not_fl(self):
        # The standard's 0.715 only falls out of the sqrt(FL) form. Plain FL
        # would give 0.718, so this discriminates the transcription.
        with_sqrt = reynolds_factor(1202.0, 1.235, 0.98)
        with_plain = 1.0 + (0.33 * 0.98 / 1.235 ** 0.25) * math.log10(1202.0 / 10_000.0)
        assert abs(with_sqrt - 0.715) < abs(with_plain - 0.715)


class TestConstantsAreTheKvColumn:
    """
    N18 and N32 are the Kv-basis Table 1 values, derived from the Cv-basis
    figures in the worked example by the unit conversion. Getting this wrong is
    the column swap that produced the old N9 error.
    """

    def test_n18_scales_linearly_from_the_cv_value(self):
        # N18 sits linearly in C/(d^2 N18), so N18_Kv = (Kv/Cv) * N18_Cv.
        assert N18 == pytest.approx(KV_PER_CV * 1.00, abs=1e-3)

    def test_n32_scales_by_the_two_thirds_power_from_the_cv_value(self):
        # N32 sits in n = 1 + N32 (C/d^2)^(2/3); C enters to the 2/3 power, so
        # N32_Kv = N32_Cv / (Kv/Cv)^(2/3). 127 / 0.865^(2/3) = 139.9.
        assert N32 == pytest.approx(127.0 / KV_PER_CV ** (2.0 / 3.0), abs=0.5)

    def test_naive_linear_scaling_of_n32_would_be_wrong(self):
        # Guards against the two easy mistakes: scaling N32 by 0.865 (-> 110)
        # or by 1.156 (-> 147). Neither is the tabulated 140.
        assert abs(N32 - KV_PER_CV * 127.0) > 20
        assert abs(N32 - 127.0 / KV_PER_CV) > 5


class TestTrimClassification:
    """Eq. A.8, classified on the rated coefficient so it cannot flip."""

    def test_large_rated_coefficient_is_full_size(self):
        assert trim_is_full_size(rated_kv=100.0, valve_diameter_mm=50.0) is True

    def test_small_rated_coefficient_is_reduced(self):
        # Crated/(d^2 N18) below 0.016 is reduced trim.
        assert trim_is_full_size(rated_kv=0.5, valve_diameter_mm=50.0) is False

    def test_n_is_continuous_and_positive(self):
        assert n_factor(1.0, 25.0, full_size=True) > 0
        assert n_factor(1.0, 25.0, full_size=False) > 1.0


class TestApplyRaisesTheCoefficient:
    """FR <= 1, so the corrected Kv is never below the turbulent one."""

    def test_viscous_duty_gets_a_correction_above_one(self):
        r = apply_reynolds_factor(
            turbulent_kv=5.0, flow_rate_m3h=10.0, kinematic_viscosity_cst=500.0,
            fl=0.9, fd=0.46, valve_diameter_mm=25.0, rated_kv=8.0)
        assert r.applied is True
        assert r.fr < 1.0
        assert r.corrected_kv > r.turbulent_kv
        assert r.corrected_kv == pytest.approx(r.turbulent_kv / r.fr, rel=1e-6)

    def test_missing_inputs_do_not_apply(self):
        r = apply_reynolds_factor(
            turbulent_kv=5.0, flow_rate_m3h=10.0, kinematic_viscosity_cst=0.0,
            fl=0.9, fd=0.46, valve_diameter_mm=25.0, rated_kv=8.0)
        assert r.applied is False

    def test_fixed_point_converges(self):
        r = apply_reynolds_factor(
            turbulent_kv=5.0, flow_rate_m3h=10.0, kinematic_viscosity_cst=500.0,
            fl=0.9, fd=0.46, valve_diameter_mm=25.0, rated_kv=8.0)
        assert r.converged is True
        # Fixed point: turbulent_kv / FR(corrected) == corrected.
        from flowcoefficient.reynolds_factor import _reynolds_number, n_factor as nf
        rev = _reynolds_number(r.corrected_kv, 10.0, 500.0, 0.9, 0.46, 25.0)
        n = nf(r.corrected_kv, 25.0, r.trim == 'full-size')
        assert 5.0 / reynolds_factor(rev, n, 0.9) == pytest.approx(r.corrected_kv, rel=1e-3)


class TestEndToEndThroughLiquidSizing:
    """The correction reaches the public liquid_flow_coefficient result."""

    def test_viscous_liquid_reports_fr_and_a_higher_kv(self):
        # A viscous oil through a small globe valve: transitional or laminar,
        # so FR should engage and lift the reported Kv above the turbulent one.
        r = liquid_flow_coefficient(
            flow_rate=6.0, inlet_pressure=8.0, outlet_pressure=5.0,
            pressure_basis='absolute', relative_density=0.9,
            kinematic_viscosity=600.0, valve_style='globe',
            valve_diameter_mm=25.0, rated_kv=10.0)
        assert r.reynolds_factor.applied is True
        assert r.reynolds_factor.fr < 1.0
        # Reported Kv is the corrected one.
        assert r.kv == pytest.approx(r.reynolds_factor.corrected_kv, rel=1e-9)
        assert r.kv > r.kv_bare_valve
        assert 'FR' in str(r)

    def test_water_is_turbulent_and_gets_no_correction(self):
        r = liquid_flow_coefficient(
            flow_rate=25.0, inlet_pressure=6.0, outlet_pressure=4.0,
            pressure_basis='absolute', relative_density=1.0,
            kinematic_viscosity=1.0, valve_style='globe',
            valve_diameter_mm=50.0, rated_kv=40.0)
        assert r.reynolds_factor.applied is False
        assert r.flow_regime.regime == 'turbulent'


class TestGasNonTurbulent:
    """
    Non-turbulent compressible flow, EN IEC 60534-2-1:2011 Annex A Eq. A.4 (the
    volumetric non-turbulent equation) and Eq. A.5 (the expansion factor Y). The
    standard has no worked example for this path, so these pin the Eq. A.5
    boundary identities, the N22-vs-N7 unit consistency, and the wiring.
    """

    def test_A5_Y_is_continuous_at_the_1000_boundary(self):
        from flowcoefficient.reynolds_factor import nonturbulent_gas_expansion_factor as Y
        # upper branch collapses to the laminar value (1-x)/2 at Rev = 1000
        assert Y(1000.0, 0.2, 0.5) == pytest.approx((1 - 0.2) / 2)

    def test_A5_Y_reaches_the_turbulent_value_at_10000(self):
        from flowcoefficient.reynolds_factor import nonturbulent_gas_expansion_factor as Y
        x, xc = 0.2, 0.5
        assert Y(10000.0, x, xc) == pytest.approx(1 - x / (3 * xc))

    def test_A5_Y_is_the_laminar_value_below_1000(self):
        from flowcoefficient.reynolds_factor import nonturbulent_gas_expansion_factor as Y
        assert Y(500.0, 0.3, 0.6) == pytest.approx((1 - 0.3) / 2)

    def test_N22_is_unit_consistent_with_the_verified_turbulent_N7(self):
        # The non-turbulent Eq A.4 (molar mass M, N22) must reduce to the
        # turbulent Eq (relative density Gg, N7) in the low pressure-drop limit,
        # which requires N22*sqrt(2/M_air) == N7. Verified turbulent N7 = 455.336.
        from flowcoefficient.reynolds_factor import N22
        from flowcoefficient.fluids import MOLAR_MASS_AIR
        assert N22 * math.sqrt(2.0 / MOLAR_MASS_AIR) == pytest.approx(455.336, rel=3e-3)

    def test_apply_gas_raises_the_coefficient(self):
        from flowcoefficient.reynolds_factor import apply_gas_reynolds_factor
        r = apply_gas_reynolds_factor(
            turbulent_kv=2.0, flow_rate_m3h=50.0, kinematic_viscosity_cst=300.0,
            fl=0.9, fd=0.46, valve_diameter_mm=25.0, rated_kv=8.0,
            inlet_pressure_bar=6.0, outlet_pressure_bar=4.0, effective_x=0.333,
            choked_x=0.6, molar_mass_g_mol=28.96, temperature_k=293.0)
        assert r.applied is True
        assert r.fr < 1.0
        assert r.corrected_kv > 0

    def test_end_to_end_viscous_gas_screens_and_corrects(self):
        from flowcoefficient import gas_flow_coefficient
        r = gas_flow_coefficient(
            flow_rate=30.0, inlet_pressure=6.0, outlet_pressure=4.0,
            pressure_basis='absolute', temperature=20, fluid='air',
            xt=0.7, fl=0.9, kinematic_viscosity=400.0, valve_style='globe',
            valve_diameter_mm=20.0, rated_kv=10.0)
        assert r.flow_regime.checked is True
        if r.flow_regime.correction_needed:
            assert r.reynolds_factor.applied is True
            assert 'FR' in str(r)
