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
from .errors import (InvalidFlowRateError, InvalidFluidPropertyError,
                     InvalidPressureError, OutOfRangeError)
from .fluids import WATER_DENSITY_15C, ff_critical_pressure_ratio, get_fluid
from .piping import NOT_APPLIED as FP_NOT_APPLIED, PipingGeometry, piping_geometry_factor
from .regime import FlowRegime, NOT_CHECKED, screen
from .travel import (CONVERGENCE_TOLERANCE, MAX_PASSES, NOT_LOCATED,
                     OperatingPoint, locate)
from .thermal import flow_from_thermal_duty
from .units import (STANDARD_ATMOSPHERE_BAR, convert_flow, convert_temperature,
                    resolve_units, to_absolute_bar,
                    validate_pressure_drop)
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
    relative_density_source: str = 'supplied'
    operating_point: OperatingPoint = NOT_LOCATED
    velocity: VelocityCheck = VELOCITY_NOT_CHECKED
    piping: PipingGeometry = FP_NOT_APPLIED
    kv_bare_valve: float = 0.0
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
        if self.piping.checked and self.piping.fp < 1.0:
            extra += f' | Fp {self.piping.fp:.3g}'
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
    downstream_diameter_mm: float | None = None,
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

    validate_pressure_drop(p1, p2)

    # ── Fluid properties ────────────────────────────────────────────────────
    fluid_obj = get_fluid(fluid) if fluid else None
    temperature_k = None
    if temperature is not None:
        temperature_k = convert_temperature(temperature, resolved['temperature'], 'k')
    elif temperature_in is not None:
        temperature_k = convert_temperature(temperature_in, resolved['temperature'], 'k')

    if relative_density is not None:
        relative_density_source = 'supplied'
    elif fluid_obj is not None:
        tabulated = fluid_obj.relative_density
        if tabulated is None:
            raise InvalidFluidPropertyError(
                f'{fluid_obj.name} has no liquid density in the table, because '
                f'it is not sized as a liquid. Pass relative_density '
                f'explicitly if you have it, or use gas_flow_coefficient.'
            )
        relative_density = tabulated
        ref_c = fluid_obj.liquid_density_temperature_c
        relative_density_source = (
            f'tabulated for {fluid_obj.name}, {fluid_obj.liquid_density_kg_m3:.4g} '
            f'kg/m3 at {ref_c:.4g} C. {fluid_obj.liquid_density_note}'
        )
        # Liquid density falls with temperature and this library does not
        # correct for it. Roughly 4 percent for water between 15 and 100 C,
        # and Kv goes with the square root of density, so about 2 percent on
        # the answer. Small, but it should not be silent.
        if temperature is not None:
            flowing_c = convert_temperature(temperature, resolved['temperature'], 'c')
            if abs(flowing_c - ref_c) > 30.0:
                relative_density_source += (
                    f' NOT CORRECTED to the flowing temperature of '
                    f'{flowing_c:.4g} C, a difference of {abs(flowing_c-ref_c):.0f} C. '
                    f'Supply relative_density at the flowing condition for a '
                    f'sizing that has to be right.'
                )
    else:
        relative_density = 1.0
        relative_density_source = 'assumed 1.0, no fluid named and none supplied'
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
        except (InvalidFluidPropertyError, OutOfRangeError):
            # Outside the Antoine fit, or no correlation held. Skip the
            # choked check and say so, rather than refusing an otherwise
            # ordinary sizing. Water above 100 C hits this.
            pv = None

    pc = critical_pressure
    if pc is None and fluid_obj is not None:
        pc = fluid_obj.critical_pressure_bar

    fl_value, fl_source = resolve_fl(fl, valve_style)

    # Fp and FLP together. FLP/Fp replaces FL in the choked test below,
    # because a valve between reducers chokes at a lower pressure drop than
    # the bare valve does. IEC 60534-2-1 clause 5.
    piping = piping_geometry_factor(
        rated_kv=rated_kv,
        valve_diameter_mm=valve_diameter_mm,
        upstream_diameter_mm=pipe_diameter_mm,
        downstream_diameter_mm=downstream_diameter_mm,
        fl=fl_value,
    )
    fl_for_choking = piping.effective_fl if piping.effective_fl is not None else fl_value

    # ── Choked check ────────────────────────────────────────────────────────
    dp_actual = p1 - p2
    dp_effective = dp_actual
    is_choked = False
    check_performed = False
    ff = None

    if fl_for_choking is not None and pv is not None and pc is not None:
        check_performed = True
        ff = ff_critical_pressure_ratio(pv, pc)
        dp_choked = fl_for_choking ** 2 * (p1 - ff * pv)
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

    kv_bare = q / math.sqrt(dp_effective / relative_density)

    # FL is published against Cv/d-squared, so it depends on where this duty
    # sits on the valve, which depends on the coefficient, which depends on
    # FL through the choked test. Iterate, for the same reason and with the
    # same history as the gas side.
    operating_point = NOT_LOCATED
    passes = 0
    converged = True
    if valve_style is not None and fl is None and rated_kv and valve_diameter_mm:
        previous = kv_bare
        for passes in range(1, MAX_PASSES + 1):
            point = locate(valve_style, previous / piping.fp, rated_kv, valve_diameter_mm)
            if not point.located:
                operating_point = point
                break
            operating_point = point
            fl_value = point.fl
            piping = piping_geometry_factor(
                rated_kv=rated_kv,
                valve_diameter_mm=valve_diameter_mm,
                upstream_diameter_mm=pipe_diameter_mm,
                downstream_diameter_mm=downstream_diameter_mm,
                fl=fl_value,
            )
            fl_for_choking = (piping.effective_fl
                              if piping.effective_fl is not None else fl_value)
            if fl_for_choking is not None and pv is not None and pc is not None:
                check_performed = True
                ff = ff_critical_pressure_ratio(pv, pc)
                dp_choked = fl_for_choking ** 2 * (p1 - ff * pv)
                if dp_choked > 0:
                    is_choked = dp_actual >= dp_choked
                    dp_effective = dp_choked if is_choked else dp_actual
            kv_bare = q / math.sqrt(dp_effective / relative_density)
            if abs(kv_bare - previous) <= CONVERGENCE_TOLERANCE * max(kv_bare, 1e-12):
                break
            previous = kv_bare
        else:
            converged = False

        if operating_point.located:
            # Re-locate on the settled coefficient, so the reported operating
            # point describes the answer rather than an estimate.
            operating_point = locate(
                valve_style, kv_bare / piping.fp, rated_kv, valve_diameter_mm)
            fl_value = operating_point.fl
            settled = 'converged' if converged else (
                f'DID NOT CONVERGE in {MAX_PASSES} passes, treat with caution')
            fl_source = (
                f'read off the published curve at '
                f'{operating_point.capacity_fraction * 100:.0f} percent of rated '
                f'capacity, against {operating_point.fl_wide_open:.3g} wide open. '
                f'{settled} in {passes} passes'
            )
            if operating_point.substituted_from:
                fl_source += f'. Curve measured on {operating_point.substituted_from}'

    kv = kv_bare / piping.fp

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
        relative_density_source=relative_density_source,
        operating_point=operating_point,
        velocity=velocity,
        opening=opening,
        piping=piping,
        kv_bare_valve=kv_bare,
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
