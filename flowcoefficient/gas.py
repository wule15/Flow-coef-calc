"""
Compressible gas and vapour sizing. IEC 60534-2-1 clause 8.

    x     = ( p1 - p2 ) / p1
    Fg    = gamma / 1.40
    Y     = 1 - x / ( 3 * Fg * xT )
    C     = Q / ( N9 * p1 * Y * sqrt( x / ( Gg * T1 * Z ) ) )

Choked flow, clause 8.3. Gas accelerating through the vena contracta
eventually reaches sonic velocity there, and once it does, lowering the
downstream pressure further cannot increase the mass flow. That happens at

    x >= Fg * xT

Past that point x is clamped to Fg * xT, and Y takes its limiting value of
2/3, which falls straight out of the Y equation at the limit:

    Y = 1 - (Fg * xT) / (3 * Fg * xT) = 1 - 1/3 = 2/3

This is the most consequential behaviour in the library. Sizing a choked
service on the actual pressure drop instead of the limited one produces a
coefficient smaller than the duty requires, and the valve is undersized in
service with nothing in the number to say so. It is why this function
returns a result object carrying is_choked rather than a bare float.

The numerical constant, and why it is called N7 not N9
------------------------------------------------------
**This equation uses relative density Gg, and in both IEC and ISA
nomenclature the constant for that form is N7. N9 belongs to the molecular
weight form.** The library called it N9 for several commits, which meant
anyone checking against IEC Table 1 found the N9 row, read 2.46e3, and
concluded the library was out by a factor of 5.4. The name is the error, not
the value.

Fisher Catalog 12 Table 2 tabulates N7 = 394 for Cv, bar, m3/h and K at
normal conditions. As Kv that is 394 x 1.15606 = 455.5, against the 455.336
derived below, 0.04 percent apart.

A first principles derivation from N1 and the ideal gas law gives 456.7, so
the tabulated figure is about 0.3 percent low against physics. That gap is in
the published Cv column, not in this code, and 455.336 is the number an
engineer checking a manufacturer table will expect.

Unlike N1 on the liquid side, N9 is not 1 in this library's internal units,
so it has to appear explicitly. A wrong N9 scales every gas answer by a
constant factor and nothing else in the output looks wrong, which makes it
the most dangerous single number in the module.

It is therefore derived below from the long-established imperial form rather
than quoted from memory, so the working is visible and checkable:

    Q[scfh] = 1360 * Cv * p1[psia] * Y * sqrt( x / (Gg * T[degR] * Z) )

converted to Q in Nm3/h, p in bar and T in K, with C expressed as Kv.

The reference conditions differ and that matters: a normal cubic metre is
referenced to 0 degrees C, a standard cubic foot to 60 degrees F. The
conversion below carries that temperature ratio explicitly. Using a 15
degrees C reference instead moves the constant by about 5 percent.

A note on a cross-check that used to sit here and was withdrawn. It converted
the tabulated N9 = 21.2 through the molecular weight form and arrived at
455.36, calling that an independent confirmation. It was not: 2120 divided by
sqrt(28.96546) is 393.9, which is the same tabulated N7 = 394 the imperial
1360 already encodes. It was one number agreeing with itself while reading as
verification, which is worse than no cross-check. The genuine outside checks
are the Fisher N7 row above and the first principles derivation.

The reference temperature handling is confirmed separately and does hold: the
ratio of the standard to normal condition constants, 22.4/21.2 = 1.0566,
matches 288.65/273.15 = 1.0567. Fisher lists standard conditions as 15.5 C,
which is the 288.65 K used here.

The derivation is kept rather than replaced by the tabulated number, because
the working is what makes the constant checkable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .checks import (OpeningCheck, VELOCITY_NOT_CHECKED, VelocityCheck,
                     check_opening, check_velocity)
from .coefficients import kv_to_cv
from .errors import InvalidFlowRateError, InvalidFluidPropertyError, InvalidPressureError, OutOfRangeError, require_finite
from .fluids import MOLAR_MASS_AIR, get_fluid
from .piping import NOT_APPLIED as FP_NOT_APPLIED, PipingGeometry, piping_geometry_factor
from .units import (
    STANDARD_ATMOSPHERE_BAR,
    convert_flow,
    convert_temperature,
    resolve_units,
    to_absolute_bar,
    validate_pressure_drop,
)
from .materials import NOT_SCREENED, MaterialGuidance, screen_materials
from .thermal import JouleThomsonEstimate, NOT_ESTIMATED, estimate_joule_thomson
from .travel import (CONVERGENCE_TOLERANCE, MAX_PASSES, NOT_LOCATED,
                     OperatingPoint, locate)
from .valves import resolve_xt

# ── N9, derived rather than quoted. See the module docstring. ───────────────
# Established imperial form: Q[scfh] = 1360 * Cv * p1[psia] * Y * sqrt(...)
_IMPERIAL_GAS_CONSTANT = 1360.0

# A normal cubic metre is at 0 C, a standard cubic foot at 60 F. Same
# pressure reference to within 0.03 percent, so this is the temperature
# ratio times the volume conversion.
NM3_TO_SCF = (288.706 / 273.15) * 35.31467

# Q[Nm3/h], p1[bar absolute], T[K], coefficient expressed as Kv, relative
# density form. This is IEC/ISA's N7. See the module docstring.
N7 = (
    _IMPERIAL_GAS_CONSTANT
    * 1.156                 # Cv per Kv
    * 14.5037738            # psi per bar
    / (1.8 ** 0.5)          # degR per K, under the square root
    / NM3_TO_SCF
)

# xT is measured on air, whose ratio of specific heats is 1.40. Fg corrects
# it to another gas. IEC 60534-2-1 clause 8.5.
GAMMA_AIR = 1.40

# The limiting expansion factor at and beyond choked flow.
Y_CHOKED = 2.0 / 3.0

# Above this pressure differential ratio, assuming Y = 1 without an xT is
# not defensible. At x = 0.1 the true Y for a globe is about 0.96, so the
# assumption costs about 4 percent. At x = 0.5 it costs nearly 30 percent,
# in the direction that undersizes the valve.
Y_ASSUMPTION_LIMIT = 0.1


@dataclass(frozen=True)
class GasSizingResult:
    """
    A gas sizing answer.

    is_choked and choked_check_performed are separate. False for both means
    no xT was available and the library did not look, which is not the same
    as looking and finding the valve clear.
    """

    kv: float
    cv: float
    is_choked: bool
    choked_check_performed: bool
    pressure_basis: str
    inlet_pressure_bar_a: float
    outlet_pressure_bar_a: float
    pressure_drop_ratio: float
    effective_pressure_drop_ratio: float
    expansion_factor: float
    limiting_ratio: float | None
    gamma: float
    gamma_factor: float
    relative_density: float
    temperature_k: float
    compressibility: float
    xt: float | None = None
    xt_source: str = 'not provided'
    expansion_factor_source: str = 'from xT'
    operating_point: OperatingPoint = NOT_LOCATED
    fluid: str | None = None
    joule_thomson: JouleThomsonEstimate = NOT_ESTIMATED
    materials: MaterialGuidance = NOT_SCREENED
    piping: PipingGeometry = FP_NOT_APPLIED
    kv_bare_valve: float = 0.0
    velocity: VelocityCheck = VELOCITY_NOT_CHECKED
    opening: OpeningCheck = OpeningCheck(False, 0.0, None, None, ())

    def __str__(self) -> str:
        state = 'CHOKED' if self.is_choked else (
            'not choked' if self.choked_check_performed else 'choked check not performed'
        )
        fluid = f', {self.fluid}' if self.fluid else ''
        jt = ''
        if self.joule_thomson.estimated and self.joule_thomson.warnings:
            jt = f" | {self.joule_thomson.warnings[0]}"
        if self.piping.checked and self.piping.fp < 1.0:
            jt = f" | Fp {self.piping.fp:.3g}" + jt
        for check in (self.velocity, self.opening):
            if check.warnings:
                jt += f" | {check.warnings[0]}"
        return (
            f"Kv {self.kv:.4g} (Cv {self.cv:.4g}) | "
            f"inputs {self.pressure_basis}{fluid} | "
            f"x {self.pressure_drop_ratio:.3f}, "
            f"Y {self.expansion_factor:.3f}"
            f"{' assumed' if 'assumed' in self.expansion_factor_source else ''}"
            f" | {state}{jt}"
        )


def gas_flow_coefficient(
    flow_rate: float,
    inlet_pressure: float,
    outlet_pressure: float,
    pressure_basis: str,
    temperature: float,
    relative_density: float | None = None,
    fluid: str | None = None,
    gamma: float | None = None,
    xt: float | None = None,
    valve_style: str | None = None,
    compressibility: float = 1.0,
    valve_diameter_mm: float | None = None,
    pipe_diameter_mm: float | None = None,
    downstream_diameter_mm: float | None = None,
    rated_kv: float | None = None,
    units: str | None = None,
    pressure_unit: str | None = None,
    flow_unit: str | None = None,
    temperature_unit: str | None = None,
    atmospheric_pressure_bar: float = STANDARD_ATMOSPHERE_BAR,
) -> GasSizingResult:
    """
    Flow coefficient for a gas or vapour. IEC 60534-2-1 clause 8.

    Flow is volumetric at normal conditions, 0 degrees C and 101.325 kPa.

    pressure_basis is required and has no default, for the same reason as on
    the liquid side.

    Worked example, air at 7 bar a falling to 5 bar a, 20 C, 500 Nm3/h,
    through a globe valve:

    >>> r = gas_flow_coefficient(
    ...     flow_rate=500, inlet_pressure=7.0, outlet_pressure=5.0,
    ...     pressure_basis='absolute', temperature=20, fluid='air',
    ...     valve_style='globe')
    >>> r.is_choked
    False
    >>> round(r.pressure_drop_ratio, 4)
    0.2857
    """
    require_finite(
        flow_rate=flow_rate, inlet_pressure=inlet_pressure,
        outlet_pressure=outlet_pressure, temperature=temperature,
        relative_density=relative_density, gamma=gamma, xt=xt,
        compressibility=compressibility, valve_diameter_mm=valve_diameter_mm,
        pipe_diameter_mm=pipe_diameter_mm,
        downstream_diameter_mm=downstream_diameter_mm, rated_kv=rated_kv,
        atmospheric_pressure_bar=atmospheric_pressure_bar,
    )

    resolved = resolve_units(
        units,
        pressure=pressure_unit,
        flow=flow_unit,
        temperature=temperature_unit,
    )

    if flow_rate <= 0:
        raise InvalidFlowRateError(f'flow rate must be positive, got {flow_rate}')
    if compressibility <= 0:
        raise InvalidFluidPropertyError(
            f'compressibility factor must be positive, got {compressibility}'
        )

    p1 = to_absolute_bar(inlet_pressure, resolved['pressure'], pressure_basis,
                         atmospheric_pressure_bar, 'inlet pressure')
    p2 = to_absolute_bar(outlet_pressure, resolved['pressure'], pressure_basis,
                         atmospheric_pressure_bar, 'outlet pressure')

    validate_pressure_drop(p1, p2)

    temperature_k = convert_temperature(temperature, resolved['temperature'], 'k')
    if temperature_k <= 0:
        raise OutOfRangeError('temperature', temperature_k, 0, float('inf'), 'K',
                              context='absolute temperature cannot be zero or below')

    fluid_obj = get_fluid(fluid) if fluid else None

    if gamma is None:
        gamma = fluid_obj.gamma if fluid_obj and fluid_obj.gamma else None
    if gamma is None:
        raise InvalidFluidPropertyError(
            'ratio of specific heats is required. Pass gamma, or name a fluid '
            'that carries one.'
        )
    if not 1.0 < gamma < 2.0:
        raise OutOfRangeError('gamma', gamma, 1.0, 2.0,
                              context='ratio of specific heats for real gases '
                                      'lies between 1 and 2')

    if relative_density is None:
        relative_density = fluid_obj.gas_relative_density if fluid_obj else None
    if relative_density is None:
        raise InvalidFluidPropertyError(
            'gas relative density is required. Pass relative_density, or name '
            'a fluid.'
        )
    if relative_density <= 0:
        raise InvalidFluidPropertyError(
            f'relative density must be positive, got {relative_density}'
        )

    q = convert_flow(flow_rate, resolved['flow'], 'm3/h')

    x = (p1 - p2) / p1
    fg = gamma / GAMMA_AIR

    xt_value, xt_source = resolve_xt(xt, valve_style)

    is_choked = False
    check_performed = False
    limiting_ratio = None
    x_effective = x

    jt_estimate = estimate_joule_thomson(
        fluid_obj,
        convert_temperature(temperature, resolved['temperature'], 'c'),
        p1 - p2,
    )

    expansion_source = 'from xT'
    if xt_value is not None:
        check_performed = True
        limiting_ratio = fg * xt_value
        if x >= limiting_ratio:
            is_choked = True
            x_effective = limiting_ratio
        y = 1.0 - x_effective / (3.0 * fg * xt_value)
    elif x > Y_ASSUMPTION_LIMIT:
        # Y sits in the denominator, so Y = 1 produces the SMALLEST
        # coefficient the equation can give, up to a third below the choked
        # value of 2/3. It is the most optimistic assumption available, not
        # the least wrong one, and the failure it causes is an undersized
        # valve. Below x = 0.1 the true Y is within about 4 percent of 1 and
        # assuming it is defensible. Above, it is not, so this refuses.
        raise InvalidFluidPropertyError(
            f'the pressure differential ratio x is {x:.3g}, above '
            f'{Y_ASSUMPTION_LIMIT}, and no xT was supplied. Without xT the '
            f'expansion factor cannot be evaluated, and assuming Y = 1 would '
            f'return a coefficient up to a third too small, which undersizes '
            f'the valve. Pass xt from the valve data sheet, or valve_style '
            f'for a typical figure.'
        )
    else:
        y = 1.0
        expansion_source = (
            f'assumed 1.0, no xT supplied. Defensible only because x is '
            f'{x:.3g}, below {Y_ASSUMPTION_LIMIT}.'
        )



    kv_bare = q / (N7 * p1 * y * math.sqrt(
        x_effective / (relative_density * temperature_k * compressibility)))

    # Fp applies to gas exactly as it does to liquid. Computed before the
    # refinement below, which needs it to place the duty on the curve.
    piping = piping_geometry_factor(
        rated_kv=rated_kv,
        valve_diameter_mm=valve_diameter_mm,
        upstream_diameter_mm=pipe_diameter_mm,
        downstream_diameter_mm=downstream_diameter_mm,
    )

    # xT is published against Cv/d-squared, so the right value depends on
    # where this duty sits on the valve, which depends on the coefficient,
    # which depends on xT. IEC resolves the circularity by iterating and so
    # do we.
    #
    # An earlier version did exactly two passes and claimed that was enough.
    # It was not: swept across realistic duties, two passes left 13 percent
    # of cases more than 1 percent from the converged answer and the worst
    # was 39 percent out. It now iterates to a tolerance and reports whether
    # it got there.
    #
    # The lookup uses the Fp-corrected coefficient, because that is what the
    # valve actually has to deliver and therefore what sets its travel.
    # IEC 60534-2-1 clause 5: C = Q / (N1 Fp sqrt(dP/rho)).
    operating_point = NOT_LOCATED
    passes = 0
    converged = True
    if valve_style is not None and xt is None and rated_kv and valve_diameter_mm:
        previous = kv_bare
        for passes in range(1, MAX_PASSES + 1):
            point = locate(valve_style, previous / piping.fp, rated_kv, valve_diameter_mm)
            if not point.located:
                operating_point = point
                break
            operating_point = point
            xt_value = point.xt
            limiting_ratio = fg * xt_value
            x_effective = min(x, limiting_ratio)
            is_choked = x >= limiting_ratio
            y = 1.0 - x_effective / (3.0 * fg * xt_value)
            kv_bare = q / (N7 * p1 * y * math.sqrt(
                x_effective / (relative_density * temperature_k * compressibility)))
            if abs(kv_bare - previous) <= CONVERGENCE_TOLERANCE * max(kv_bare, 1e-12):
                break
            previous = kv_bare
        else:
            converged = False

        if operating_point.located:
            # Re-locate on the settled coefficient so the reported operating
            # point describes the answer that shipped, not an intermediate
            # estimate. Without this the result contradicted itself: the
            # operating point said 34 percent of rated while the opening
            # check on the same object said 18 percent.
            operating_point = locate(
                valve_style, kv_bare / piping.fp, rated_kv, valve_diameter_mm)
            xt_value = operating_point.xt
            settled = 'converged' if converged else (
                f'DID NOT CONVERGE in {MAX_PASSES} passes, treat with caution')
            xt_source = (
                f'read off the published curve at '
                f'{operating_point.capacity_fraction * 100:.0f} percent of rated '
                f'capacity, against {operating_point.xt_wide_open:.3g} wide open. '
                f'{settled} in {passes} passes'
            )
            if operating_point.substituted_from:
                xt_source += f'. Curve measured on {operating_point.substituted_from}'
            expansion_source = 'from xT at the operating point'

    kv = kv_bare / piping.fp

    # Velocity, evaluated at the OUTLET. Gas expands through the valve, so
    # the outlet is where density is lowest and velocity highest, and that is
    # where erosion and noise are decided. Density from the ideal gas law
    # with the supplied compressibility factor.
    #
    #   rho2 = p2 * M / (Z * R * T2)
    #
    # T2 uses the Joule-Thomson estimate when one exists, because a gas that
    # has cooled 60 K is denser than the inlet temperature would suggest.
    outlet_velocity = VELOCITY_NOT_CHECKED
    if pipe_diameter_mm:
        molar_mass_kg = relative_density * MOLAR_MASS_AIR / 1000.0
        t2_k = temperature_k
        if jt_estimate is not None and jt_estimate.estimated:
            t2_k = jt_estimate.outlet_temperature_c + 273.15
        rho2 = (p2 * 1.0e5) * molar_mass_kg / (compressibility * 8.31446 * t2_k)
        # Normal conditions to outlet conditions, ideal gas.
        q_actual = q * (1.01325 / p2) * (t2_k / 273.15)
        outlet_velocity = check_velocity(
            flow_rate_m3h=q_actual,
            pipe_diameter_mm=pipe_diameter_mm,
            density_kg_m3=rho2,
            is_gas=True,
        )


    inlet_c = convert_temperature(temperature, resolved['temperature'], 'c')
    if jt_estimate.estimated:
        materials = screen_materials(
            minimum_c=jt_estimate.outlet_temperature_c,
            maximum_c=inlet_c,
        )
    else:
        # Without a Joule-Thomson estimate the coldest metal temperature is
        # unknown, and screening on the inlet alone would report a carbon
        # steel clearance the expansion may well have destroyed. A 55 bar
        # letdown can take the body 20 to 60 degrees below its inlet.
        materials = NOT_SCREENED

    return GasSizingResult(
        kv=kv,
        cv=kv_to_cv(kv),
        is_choked=is_choked,
        choked_check_performed=check_performed,
        pressure_basis=pressure_basis.strip().lower(),
        inlet_pressure_bar_a=p1,
        outlet_pressure_bar_a=p2,
        pressure_drop_ratio=x,
        effective_pressure_drop_ratio=x_effective,
        expansion_factor=y,
        limiting_ratio=limiting_ratio,
        gamma=gamma,
        gamma_factor=fg,
        relative_density=relative_density,
        temperature_k=temperature_k,
        compressibility=compressibility,
        xt=xt_value,
        xt_source=xt_source,
        expansion_factor_source=expansion_source,
        fluid=fluid_obj.name if fluid_obj else None,
        joule_thomson=jt_estimate,
        operating_point=operating_point,
        materials=materials,
        piping=piping,
        kv_bare_valve=kv_bare,
        velocity=outlet_velocity,
        opening=check_opening(kv, rated_kv),
    )


# Retained so existing imports keep working. N7 is the correct name.
N9 = N7
