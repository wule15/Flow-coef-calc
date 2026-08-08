"""
Valve flow coefficient calculation to IEC 60534-2-1.

Kv and Cv conversion, incompressible liquid sizing, compressible gas sizing
including the choked flow condition, unit conversion, and a small table of
fluid properties.

Standard library only. No runtime dependencies.

    >>> from flowcoefficient import liquid_flow_coefficient
    >>> r = liquid_flow_coefficient(
    ...     flow_rate=25, inlet_pressure=6.0, outlet_pressure=4.0,
    ...     pressure_basis='absolute', relative_density=1.0)
    >>> print(r)
    Kv 17.68 (Cv 20.44) | inputs absolute | choked check not performed

Two things this library does deliberately differently:

Pressure basis is never assumed. Every sizing call requires pressure_basis
to be stated, because a gauge reading treated as absolute produces a
confident wrong answer and nothing in the output would look wrong.

It reports when it did not check. A result carries is_choked and
choked_check_performed separately, so "checked and clear" is never confused
with "no valve data available, did not look".
"""

from __future__ import annotations

from .coefficients import CV_PER_KV, KV_PER_CV, cv_to_kv, kv_to_cv
from .errors import (
    FlowCoefficientError,
    InvalidFlowRateError,
    InvalidFluidPropertyError,
    InvalidPressureError,
    NonFiniteInputError,
    OutOfRangeError,
    UnknownFluidError,
    UnknownUnitError,
)
from .fluids import FLUIDS, Fluid, ff_critical_pressure_ratio, get_fluid
from .cavitation import CavitationIndex
from .cavitation import evaluate as evaluate_cavitation
from .checks import OpeningCheck, VelocityCheck, check_opening, check_velocity
from .gas import GasSizingResult, gas_flow_coefficient
from .materials import MATERIALS, Material, MaterialGuidance, screen_materials
from .regime import FlowRegime, screen as screen_flow_regime
from .thermal import (JouleThomsonEstimate, estimate_joule_thomson,
                      flow_from_thermal_duty)
from .liquid import LiquidSizingResult, liquid_flow_coefficient, liquid_flow_rate
from .units import (
    STANDARD_ATMOSPHERE_BAR,
    absolute_to_gauge,
    convert_flow,
    convert_pressure,
    convert_temperature,
    gauge_to_absolute,
)
from .valves import VALVE_STYLES, ValveStyle, get_valve_style

__version__ = '0.1.0'

__all__ = [
    # sizing
    'liquid_flow_coefficient',
    'liquid_flow_rate',
    'gas_flow_coefficient',
    'LiquidSizingResult',
    'GasSizingResult',
    # coefficients
    'kv_to_cv',
    'cv_to_kv',
    'CV_PER_KV',
    'KV_PER_CV',
    # units
    'convert_pressure',
    'convert_flow',
    'convert_temperature',
    'gauge_to_absolute',
    'absolute_to_gauge',
    'STANDARD_ATMOSPHERE_BAR',
    # fluids and valves
    'get_fluid',
    'Fluid',
    'FLUIDS',
    'ff_critical_pressure_ratio',
    'screen_materials', 'Material', 'MATERIALS', 'MaterialGuidance',
    'flow_from_thermal_duty', 'estimate_joule_thomson', 'JouleThomsonEstimate',
    'check_velocity', 'check_opening', 'VelocityCheck', 'OpeningCheck',
    'evaluate_cavitation', 'CavitationIndex',
    'screen_flow_regime', 'FlowRegime',
    'get_valve_style',
    'ValveStyle',
    'VALVE_STYLES',
    # errors
    'FlowCoefficientError',
    'InvalidPressureError',
    'InvalidFlowRateError',
    'InvalidFluidPropertyError',
    'NonFiniteInputError',
    'OutOfRangeError',
    'UnknownUnitError',
    'UnknownFluidError',
]
