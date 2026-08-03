"""
Incompressible liquid sizing. IEC 60534-2-1 clauses 7.1 to 7.3.

Non-choked turbulent flow, clause 7.1:

    C = Q / sqrt( dP / (rho1 / rho0) )

with Q in m3/h and dP in bar, where the IEC numerical constant N1 is 1. The
library converts to those units on entry, so this is the only unit set the
equation ever sees. Other unit sets change N1, not the equation, and the
values are given in the units module docstring.

Choked flow, clauses 7.2 and 7.3. A liquid chokes when the pressure at the
vena contracta falls to the vapour pressure and the fluid flashes or
cavitates. Past that point more pressure drop does not buy more flow:

    dP_choked = FL^2 * ( p1 - FF * pv )
    FF        = 0.96 - 0.28 * sqrt( pv / pc )

Sizing a choked service on the full pressure drop oversizes the valve,
because the equation is handed a pressure drop the valve cannot actually
convert into flow.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .checks import (OpeningCheck, VELOCITY_NOT_CHECKED, VelocityCheck,
                     check_opening, check_velocity)
from .coefficients import kv_to_cv
from .errors import InvalidFlowRateError, InvalidFluidPropertyError, InvalidPressureError
from .fluids import WATER_DENSITY_15C, ff_critical_pressure_ratio, get_fluid
from .regime import FlowRegime, NOT_CHECKED, screen
from .thermal import flow_from_thermal_duty
from .units import (STANDARD_ATMOSPHERE_BAR, convert_flow, convert_temperature,
                    resolve_units, to_absolute_bar)
from .valves import get_valve_style, resolve_fl


@dataclass(frozen=True)
class LiquidSizingResult:
    """
    A liquid sizing answer, carrying enough context to be checked.

    is_choked and choked_check_performed are separate on purpose. False for
    both means the library did not look, which is a different statement from
    looking and finding the valve clear.
    """

    kv: float
    cv: float
    is_choked: bool
    choked_check_performed: bool
    pressure_basis: str
    inlet_pressure_bar_a: float
    outlet_pressure_bar_a: float
    pressure_drop_bar: float
    effective_pressure_drop_bar: float
    relative_density: float
    fl: float | None = None
    fl_source: str = 'not provided'
    vapour_pressure_bar: float | None = None
    ff: float | None = None
    fluid: str | None = None
    flow_regime: FlowRegime = NOT_CHECKED
    flow_rate_m3h: float = 0.0
    flow_source: str = 'supplied'
    velocity: VelocityCheck = VELOCITY_NOT_CHECKED
    opening: OpeningCheck = OpeningCheck(False, 0.0, None, None, ())

    def __str__(self) -> str:
        state = 'CHOKED' if self.is_choked else (
            'not choked' if self.choked_check_performed else 'choked check not performed'
        )
        fluid = f', {self.fluid}' if self.fluid else ''
        regime = ''
        if self.flow_regime.checked and self.flow_regime.correction_needed:
            regime = f" | {self.flow_regime.regime.upper()}, turbulent equations do not apply"
        extra = ''
        if self.velocity.checked:
            extra += f' | {self.velocity.velocity_ms:.2f} m/s'
        for check in (self.velocity, self.opening):
            if check.warnings:
                extra += f' | {check.warnings[0]}'
        return (
            f"Kv {self.kv:.4g} (Cv {self.cv:.4g}) | "
            f"inputs {self.pressure_basis}{fluid} | {state}{regime}{extra}"
        )


def liquid_flow_coefficient(
    inlet_pressure: float,
    pressure_basis: str,
    flow_rate: float | None = None,
    outlet_pressure: float | None = None,
    pressure_drop: float | None = None,
    thermal_duty: float | None = None,
    temperature_in: float | None = None,
    temperature_out: float | None = None,
    specific_heat: float | None = None,
    relative_density: float | None = None,
    fluid: str | None = None,
    temperature: float | None = None,
    fl: float | None = None,
    valve_style: str | None = None,
    vapour_pressure: float | None = None,
    critical_pressure: float | None = None,
    kinematic_viscosity: float | None = None,
    valve_diameter_mm: float | None = None,
    pipe_diameter_mm: float | None = None,
    rated_kv: float | None = None,
    intermittent_service: bool = False,
    units: str | None = None,
    pressure_unit: str | None = None,
    flow_unit: str | None = None,
    temperature_unit: str | None = None,
    atmospheric_pressure_bar: float = STANDARD_ATMOSPHERE_BAR,
) -> LiquidSizingResult:
    """
    Flow coefficient for a liquid. IEC 60534-2-1 clause 7.

    pressure_basis is required and has no default. Assuming the wrong basis
    is the error most likely to produce a confident wrong answer, and stating
    it costs one word.

    The choked flow check runs only when both fl and a vapour pressure are
    available. Without them the result reports choked_check_performed=False
    rather than claiming the valve is clear.

    Worked example, water at 6 bar a falling to 4 bar a, 25 m3/h:

    >>> r = liquid_flow_coefficient(
    ...     flow_rate=25, inlet_pressure=6.0, outlet_pressure=4.0,
    ...     pressure_basis='absolute', relative_density=1.0)
    >>> round(r.kv, 2), round(r.cv, 2), r.choked_check_performed
    (17.68, 20.44, False)
    """
    resolved = resolve_units(
        units,
        pressure=pressure_unit,
        flow=flow_unit,
        temperature=temperature_unit,
    )

    if (flow_rate is None) == (thermal_duty is None):
        raise InvalidFlowRateError(
            'give either flow_rate or thermal_duty, not both and not neither. '
            'thermal_duty derives the flow from an energy balance on the '
            'process, which is the cooling water and heat exchanger case.'
        )
    if (outlet_pressure is None) == (pressure_drop is None):
        raise InvalidPressureError(
            'give either outlet_pressure or pressure_drop, not both and not '
            'neither'
        )

    p1 = to_absolute_bar(inlet_pressure, resolved['pressure'], pressure_basis,
                         atmospheric_pressure_bar, 'inlet pressure')
    if outlet_pressure is not None:
        p2 = to_absolute_bar(outlet_pressure, resolved['pressure'], pressure_basis,
                             atmospheric_pressure_bar, 'outlet pressure')
    else:
        # A pressure difference has no basis, it is the same number either way.
        from .units import convert_pressure
        p2 = p1 - convert_pressure(pressure_drop, resolved['pressure'], 'bar')
        if p2 <= 0:
            raise InvalidPressureError(
                f'a pressure drop of {pressure_drop} {resolved["pressure"]} '
                f'takes the outlet to {p2:.5g} bar absolute, which is not a '
                f'physical pressure'
            )

    if p2 > p1:
        raise InvalidPressureError(
            f'outlet pressure {p2:.5g} bar absolute is above inlet pressure '
            f'{p1:.5g} bar absolute. Flow does not run up a pressure gradient.'
        )
    if p2 == p1:
        raise InvalidPressureError(
            'inlet and outlet pressure are equal, so there is no driving '
            'pressure drop and no finite flow coefficient exists'
        )

    # ── Fluid properties ────────────────────────────────────────────────────
    fluid_obj = get_fluid(fluid) if fluid else None
    temperature_k = None
    if temperature is not None:
        temperature_k = convert_temperature(temperature, resolved['temperature'], 'k')
    elif temperature_in is not None:
        temperature_k = convert_temperature(temperature_in, resolved['temperature'], 'k')

    if relative_density is None:
        if fluid_obj is not None and fluid_obj.relative_density_15c is not None:
            relative_density = fluid_obj.relative_density_15c
        else:
            relative_density = 1.0
    if relative_density <= 0:
        raise InvalidFluidPropertyError(
            f'relative density must be positive, got {relative_density}'
        )

    # ── Flow, supplied or derived from a thermal duty ───────────────────────
    if flow_rate is not None:
        if flow_rate <= 0:
            raise InvalidFlowRateError(f'flow rate must be positive, got {flow_rate}')
        q = convert_flow(flow_rate, resolved['flow'], 'm3/h')
        flow_source = 'supplied'
    else:
        cp = specific_heat
        if cp is None and fluid_obj is not None:
            cp = fluid_obj.specific_heat_kj_kgk
        if cp is None:
            raise InvalidFluidPropertyError(
                'a thermal duty needs a specific heat capacity. Pass '
                'specific_heat in kJ/kg K, or name a fluid that carries one.'
            )
        if temperature_in is None or temperature_out is None:
            raise InvalidFlowRateError(
                'a thermal duty needs temperature_in and temperature_out to '
                'define the temperature change that carries it'
            )
        t_in_c = convert_temperature(temperature_in, resolved['temperature'], 'c')
        t_out_c = convert_temperature(temperature_out, resolved['temperature'], 'c')
        q = flow_from_thermal_duty(thermal_duty, t_in_c, t_out_c, cp, relative_density)
        flow_source = (
            f'from thermal duty {thermal_duty} kW over '
            f'{abs(t_out_c - t_in_c):.3g} C, cp {cp} kJ/kg K'
        )

    pv = vapour_pressure
    if pv is None and fluid_obj is not None and temperature_k is not None:
        try:
            pv = fluid_obj.vapour_pressure_bar(temperature_k)
        except InvalidFluidPropertyError:
            pv = None

    pc = critical_pressure
    if pc is None and fluid_obj is not None:
        pc = fluid_obj.critical_pressure_bar

    fl_value, fl_source = resolve_fl(fl, valve_style)

    # ── Choked check ────────────────────────────────────────────────────────
    dp_actual = p1 - p2
    dp_effective = dp_actual
    is_choked = False
    check_performed = False
    ff = None

    if fl_value is not None and pv is not None and pc is not None:
        check_performed = True
        ff = ff_critical_pressure_ratio(pv, pc)
        dp_choked = fl_value ** 2 * (p1 - ff * pv)
        if dp_choked <= 0:
            raise InvalidFluidPropertyError(
                f'the choked pressure drop works out at {dp_choked:.5g} bar, '
                f'which means the inlet pressure {p1:.5g} bar absolute is at '
                f'or below FF times the vapour pressure. The liquid is already '
                f'flashing at the inlet and these equations do not apply.'
            )
        if dp_actual >= dp_choked:
            is_choked = True
            dp_effective = dp_choked

    kv = q / math.sqrt(dp_effective / relative_density)

    fd = get_valve_style(valve_style).fd if valve_style else 0.46
    flow_regime = screen(
        flow_rate_m3h=q,
        kv=kv,
        kinematic_viscosity_cst=kinematic_viscosity,
        fl=fl_value,
        fd=fd,
        valve_diameter_mm=valve_diameter_mm,
    )

    velocity = check_velocity(
        flow_rate_m3h=q,
        pipe_diameter_mm=pipe_diameter_mm,
        density_kg_m3=relative_density * WATER_DENSITY_15C,
        is_gas=False,
        intermittent=intermittent_service,
    )
    opening = check_opening(kv, rated_kv)

    return LiquidSizingResult(
        kv=kv,
        cv=kv_to_cv(kv),
        is_choked=is_choked,
        choked_check_performed=check_performed,
        pressure_basis=pressure_basis.strip().lower(),
        inlet_pressure_bar_a=p1,
        outlet_pressure_bar_a=p2,
        pressure_drop_bar=dp_actual,
        effective_pressure_drop_bar=dp_effective,
        relative_density=relative_density,
        fl=fl_value,
        fl_source=fl_source,
        vapour_pressure_bar=pv,
        ff=ff,
        fluid=fluid_obj.name if fluid_obj else None,
        flow_regime=flow_regime,
        flow_rate_m3h=q,
        flow_source=flow_source,
        velocity=velocity,
        opening=opening,
    )


def liquid_flow_rate(
    kv: float,
    inlet_pressure: float,
    outlet_pressure: float,
    pressure_basis: str,
    relative_density: float = 1.0,
    units: str | None = None,
    pressure_unit: str | None = None,
    flow_unit: str | None = None,
    atmospheric_pressure_bar: float = STANDARD_ATMOSPHERE_BAR,
) -> float:
    """
    The same equation rearranged: flow through a known Kv.

    Returns flow in the flow unit of the chosen system. Does not check for
    choked flow, because the question being asked is what a given valve
    passes rather than what valve to buy.

    >>> round(liquid_flow_rate(17.68, 6.0, 4.0, 'absolute'), 2)
    25.0
    """
    resolved = resolve_units(units, pressure=pressure_unit, flow=flow_unit)

    if kv <= 0:
        raise InvalidFlowRateError(f'Kv must be positive, got {kv}')
    if relative_density <= 0:
        raise InvalidFluidPropertyError(
            f'relative density must be positive, got {relative_density}'
        )

    p1 = to_absolute_bar(inlet_pressure, resolved['pressure'], pressure_basis,
                         atmospheric_pressure_bar, 'inlet pressure')
    p2 = to_absolute_bar(outlet_pressure, resolved['pressure'], pressure_basis,
                         atmospheric_pressure_bar, 'outlet pressure')
    if p2 >= p1:
        raise InvalidPressureError(
            f'outlet pressure {p2:.5g} bar absolute is not below inlet '
            f'pressure {p1:.5g} bar absolute'
        )

    q_m3h = kv * math.sqrt((p1 - p2) / relative_density)
    return convert_flow(q_m3h, 'm3/h', resolved['flow'])
