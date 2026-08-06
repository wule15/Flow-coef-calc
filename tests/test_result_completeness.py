"""
Every field of a result object must be set explicitly by its constructor.

Written because the same bug happened three times in one session, each time
silently. A field is added to a result dataclass with a default, the code that
computes its value is added, and the assignment into the constructor is
missed. Nothing raises. The computation runs, the value is discarded, and the
caller reads the default forever.

That is exactly the failure this library exists to prevent, committed by the
library. In the last instance the cavitation index was computed correctly on
every call and thrown away, so every result said "not computed, no vapour
pressure" while carrying a vapour pressure in the field beside it.

A static check catches it once and for all: read the source of each sizing
function, find the result constructor, and require a keyword for every field
the dataclass declares. Defaults are for callers who omit an input, not for
values the function computed and forgot to pass on.
"""

import ast
import dataclasses
import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flowcoefficient import (  # noqa: E402
    GasSizingResult,
    LiquidSizingResult,
    gas_flow_coefficient,
    liquid_flow_coefficient,
)

CASES = [
    (liquid_flow_coefficient, LiquidSizingResult),
    (gas_flow_coefficient, GasSizingResult),
]


def _constructor_keywords(func, result_cls):
    """Keyword names passed to result_cls(...) anywhere in func's source."""
    tree = ast.parse(inspect.getsource(func).lstrip())
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, 'id', None) or getattr(node.func, 'attr', None)
        if name != result_cls.__name__:
            continue
        for kw in node.keywords:
            if kw.arg:
                found.add(kw.arg)
    return found


@pytest.mark.parametrize('func, result_cls', CASES, ids=lambda o: getattr(o, '__name__', str(o)))
def test_every_result_field_is_set_explicitly(func, result_cls):
    declared = {f.name for f in dataclasses.fields(result_cls)}
    passed = _constructor_keywords(func, result_cls)
    missing = declared - passed
    assert not missing, (
        f'{func.__name__} never passes {sorted(missing)} to '
        f'{result_cls.__name__}, so those fields keep their defaults no matter '
        f'what the function computed. This is the bug that shipped three times.'
    )


@pytest.mark.parametrize('func, result_cls', CASES, ids=lambda o: getattr(o, '__name__', str(o)))
def test_the_check_would_actually_notice(func, result_cls):
    """Guards the guard: prove the assertion above can fail."""
    declared = {f.name for f in dataclasses.fields(result_cls)}
    passed = _constructor_keywords(func, result_cls)
    assert passed, 'no constructor call found, the AST walk is broken'
    assert declared, 'no fields found, the dataclass introspection is broken'
    assert 'kv' in passed, 'the walk is not finding real keywords'


class TestTheFieldsAgreeWithEachOther:
    """
    A field that is set but contradicts another is the softer version of the
    same bug, and it has also happened here.
    """

    def test_liquid_reports_the_vapour_pressure_the_index_used(self):
        r = liquid_flow_coefficient(
            flow_rate=25, inlet_pressure=6.0, outlet_pressure=4.0,
            pressure_basis='absolute', fluid='water', temperature=20,
            valve_style='globe')
        assert r.vapour_pressure_bar is not None
        assert r.cavitation.computed, (
            'the index reported not computed while a vapour pressure sits in '
            'the field beside it'
        )

    def test_flashing_and_the_coefficient_are_consistent(self):
        r = liquid_flow_coefficient(
            flow_rate=25, inlet_pressure=6.0, outlet_pressure=0.3,
            pressure_basis='absolute', fluid='water', temperature=80,
            valve_style='globe')
        assert r.cavitation.flashing
        assert r.outlet_pressure_bar_a <= r.vapour_pressure_bar
        assert 'FLASHING' in str(r)

    def test_gas_operating_point_matches_the_opening_check(self):
        r = gas_flow_coefficient(
            flow_rate=800, inlet_pressure=10.0, outlet_pressure=5.0,
            pressure_basis='absolute', temperature=20, fluid='air',
            valve_style='ball', valve_diameter_mm=40, rated_kv=30)
        assert r.operating_point.capacity_fraction == pytest.approx(
            r.opening.fraction, rel=1e-6)
