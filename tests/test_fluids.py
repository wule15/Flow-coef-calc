"""
The fluid table.

There was no test file for this module, which a mutation probe made obvious:
several properties were pinned by nothing at all.

The liquid density tests exist because of a specific mistake. The field used
to be relative_density_15c, a bare number at 15 C, and five of the seven
fluids are not liquid at 15 C, so it held None for all of them. The library
then either used water's density for them, which was wrong, or refused to
size them at all, which was useless. Liquid nitrogen exists at minus 196 and
is 0.81. The field now carries a density and the temperature it applies at.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flowcoefficient import get_fluid, liquid_flow_coefficient  # noqa: E402
from flowcoefficient.errors import InvalidFluidPropertyError, OutOfRangeError  # noqa: E402
from flowcoefficient.fluids import FLUIDS, MOLAR_MASS_AIR, WATER_DENSITY_15C  # noqa: E402


class TestLiquidDensityCarriesItsOwnTemperature:
    @pytest.mark.parametrize('name, expected_rel, expected_ref_c', [
        ('water', 1.000, 15.0),
        ('nitrogen', 0.807, -195.8),
        ('methane', 0.423, -161.5),
        ('ammonia', 0.619, 15.0),
        ('carbon dioxide', 1.179, -56.6),
        ('air', 0.875, -194.3),
    ])
    def test_published_liquid_densities(self, name, expected_rel, expected_ref_c):
        f = get_fluid(name)
        assert f.relative_density == pytest.approx(expected_rel, abs=0.002)
        assert f.liquid_density_temperature_c == pytest.approx(expected_ref_c, abs=0.1)

    def test_liquid_nitrogen_can_be_sized(self):
        """This is the duty the old field made impossible."""
        r = liquid_flow_coefficient(
            flow_rate=25, inlet_pressure=6.0, outlet_pressure=4.0,
            pressure_basis='absolute', fluid='nitrogen', temperature=-195.8)
        assert r.relative_density == pytest.approx(0.807, abs=0.002)
        assert '806' in r.relative_density_source

    def test_a_flowing_temperature_far_from_the_reference_is_flagged(self):
        """
        The library does not correct density for temperature. Not correcting
        is defensible; not saying so is not.
        """
        r = liquid_flow_coefficient(
            flow_rate=25, inlet_pressure=6.0, outlet_pressure=4.0,
            pressure_basis='absolute', fluid='nitrogen', temperature=-150)
        assert 'NOT CORRECTED' in r.relative_density_source

    def test_a_temperature_near_the_reference_is_not_flagged(self):
        r = liquid_flow_coefficient(
            flow_rate=25, inlet_pressure=6.0, outlet_pressure=4.0,
            pressure_basis='absolute', fluid='water', temperature=30)
        assert 'NOT CORRECTED' not in r.relative_density_source

    def test_steam_is_still_refused_as_a_liquid(self):
        """Steam is water vapour. Sizing it as a liquid is a category error."""
        with pytest.raises(InvalidFluidPropertyError, match='no liquid density'):
            liquid_flow_coefficient(
                flow_rate=25, inlet_pressure=6.0, outlet_pressure=4.0,
                pressure_basis='absolute', fluid='steam')

    def test_a_supplied_density_always_wins(self):
        r = liquid_flow_coefficient(
            flow_rate=25, inlet_pressure=6.0, outlet_pressure=4.0,
            pressure_basis='absolute', fluid='nitrogen', relative_density=0.79)
        assert r.relative_density == 0.79
        assert r.relative_density_source == 'supplied'


class TestGasRelativeDensityIsDerived:
    """
    Derived from molar mass rather than tabulated, so it cannot drift out of
    step with the molar mass beside it.
    """

    @pytest.mark.parametrize('name, expected', [
        ('air', 1.000),
        ('nitrogen', 0.967),
        ('methane', 0.554),
        ('carbon dioxide', 1.519),
        ('ammonia', 0.588),
    ])
    def test_against_published_values(self, name, expected):
        assert get_fluid(name).gas_relative_density == pytest.approx(expected, abs=0.002)

    def test_it_tracks_molar_mass(self):
        f = get_fluid('methane')
        assert f.gas_relative_density == pytest.approx(f.molar_mass / MOLAR_MASS_AIR)


class TestCriticalConstants:
    @pytest.mark.parametrize('name, pc_bar', [
        ('water', 220.64), ('air', 37.86), ('nitrogen', 33.958),
        ('methane', 45.99), ('carbon dioxide', 73.773), ('ammonia', 113.33),
    ])
    def test_critical_pressures(self, name, pc_bar):
        assert get_fluid(name).critical_pressure_bar == pytest.approx(pc_bar, rel=1e-3)

    def test_water_density_reference_is_iapws(self):
        assert WATER_DENSITY_15C == pytest.approx(999.1, rel=1e-4)


class TestEveryEntryIsCited:
    """
    A property with no source is a property nobody can check. The N2 and N9
    errors both survived because the number was quoted rather than sourced.
    """

    @pytest.mark.parametrize('name', list(FLUIDS))
    def test_the_fluid_names_a_source(self, name):
        assert FLUIDS[name].source, f'{name} has no source'

    @pytest.mark.parametrize('name', list(FLUIDS))
    def test_any_antoine_set_names_its_own_source_and_range(self, name):
        antoine = FLUIDS[name].antoine
        if antoine is None:
            return
        assert antoine.source
        assert antoine.min_k < antoine.max_k

    @pytest.mark.parametrize('name', list(FLUIDS))
    def test_any_liquid_density_states_its_temperature(self, name):
        f = FLUIDS[name]
        if f.liquid_density_kg_m3 is None:
            return
        assert f.liquid_density_temperature_c is not None, (
            f'{name} has a liquid density with no temperature, which is the '
            f'exact ambiguity the old relative_density_15c field created'
        )
        assert f.liquid_density_note


class TestAntoineRangeIsEnforcedPerFluid:
    @pytest.mark.parametrize('name', [n for n, f in FLUIDS.items() if f.antoine])
    def test_just_outside_the_fit_raises(self, name):
        antoine = FLUIDS[name].antoine
        with pytest.raises(OutOfRangeError):
            FLUIDS[name].vapour_pressure_bar(antoine.max_k + 50)
        with pytest.raises(OutOfRangeError):
            FLUIDS[name].vapour_pressure_bar(antoine.min_k - 20)

    @pytest.mark.parametrize('name', [n for n, f in FLUIDS.items() if f.antoine])
    def test_inside_the_fit_returns_a_positive_pressure(self, name):
        antoine = FLUIDS[name].antoine
        mid = (antoine.min_k + antoine.max_k) / 2
        assert FLUIDS[name].vapour_pressure_bar(mid) > 0
