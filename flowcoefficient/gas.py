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

The N9 constant, and why it is derived here rather than quoted
--------------------------------------------------------------
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

VERIFIED against the ISA/IEC equation constants table, 3 August 2026, as
reproduced in Fisher Catalog 12 Section 2 Table 2. The standard tabulates

    N9 = 21.2   Q in m3/h at normal conditions, p in kPa, T in K, C as Cv

for the IEC form of the equation, which uses **molecular weight M** where
this library uses relative density Gg. Converting:

    21.2 (kPa, Cv)  x100      = 2120   (bar, Cv)
    2120            x1.156    = 2450.7 (bar, Kv)
    2450.7 / sqrt(28.96546)   = 455.36 (bar, Kv, Gg form)

against 455.336 derived here, a difference of 0.005 percent. Two further
agreements from the same table confirm the working rather than one number
happening to land: N1 tabulates as 0.865 for Cv, which is 1.000 for Kv and
matches the liquid module, and the ratio of the standard to normal condition
constants, 22.4/21.2 = 1.0566, matches 288.65/273.15 = 1.0567, confirming the
reference temperature handling.

The derivation is kept rather than replaced by the tabulated number, because
the working is what makes the constant checkable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .coefficients import kv_to_cv
from .errors import InvalidFlowRateError, InvalidFluidPropertyError, InvalidPressureError, OutOfRangeError
from .fluids import get_fluid
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
from .valves import resolve_xt

# ── N9, derived rather than quoted. See the module docstring. ───────────────
# Established imperial form: Q[scfh] = 1360 * Cv * p1[psia] * Y * sqrt(...)
_IMPERIAL_GAS_CONSTANT = 1360.0

# A normal cubic metre is at 0 C, a standard cubic foot at 60 F. Same
# pressure reference to within 0.03 percent, so this is the temperature
# ratio times the volume conversion.
NM3_TO_SCF = (288.706 / 273.15) * 35.31467

# Q[Nm3/h], p1[bar absolute], T[K], coefficient expressed as Kv.
N9 = (
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
    fluid: str | None = None
    joule_thomson: JouleThomsonEstimate = NOT_ESTIMATED
    materials: MaterialGuidance = NOT_SCREENED

    def __str__(self) -> str:
        state = 'CHOKED' if self.is_choked else (
            'not choked' if self.choked_check_performed else 'choked check not performed'
        )
        fluid = f', {self.fluid}' if self.fluid else ''
        jt = ''
        if self.joule_thomson.estimated and self.joule_thomson.warnings:
            jt = f" | {self.joule_thomson.warnings[0]}"
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

    kv = q / (N9 * p1 * y * math.sqrt(x_effective / (relative_density * temperature_k * compressibility)))

    jt = estimate_joule_thomson(
        fluid_obj,
        convert_temperature(temperature, resolved['temperature'], 'c'),
        p1 - p2,
    )

    inlet_c = convert_temperature(temperature, resolved['temperature'], 'c')
    if jt.estimated:
        materials = screen_materials(
            minimum_c=jt.outlet_temperature_c,
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
        joule_thomson=jt,
        materials=materials,
    )
