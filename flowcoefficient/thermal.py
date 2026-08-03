"""
Thermal duty as a sizing input, and Joule-Thomson cooling as an output.

Two separate things that both involve temperature, kept apart on purpose.

Thermal duty, an input path
---------------------------
A valve does not produce a designed temperature change. It is a restriction,
not a heat exchanger. But a temperature rise or drop is very often the
process requirement that fixes the flow, and the flow is what the valve is
sized for. Cooling water is the standard case: you must remove 250 kW and
you are allowed a 10 C rise, which fixes the flow at about 21.5 m3/h, and
that is the number the sizing equation wants.

    Q = m * cp * dT      ->      flow      ->      Kv

So a temperature difference is a legitimate input. It just enters one step
upstream of the valve equation, and the valve equation never sees it.

Joule-Thomson cooling, an output warning
----------------------------------------
Throttling a gas is close to isenthalpic, so the gas cools as it expands.
On natural gas this is roughly 0.45 K per bar, which turns a 40 bar letdown
into an 18 degree drop. That is why letdown stations ice up and why hydrate
inhibition exists.

This is a consequence of the pressure drop, never an input. It is estimated
here so the result can warn about it, and the estimate is deliberately
labelled as an estimate: the Joule-Thomson coefficient varies strongly with
temperature and pressure, and a single tabulated value gives an order of
magnitude rather than a number to design to.
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import InvalidFluidPropertyError, InvalidFlowRateError
from .fluids import WATER_DENSITY_15C, Fluid

# Below this, carbon steel is outside its normal service range and a low
# temperature material is required. ASME B31.3 impact test exemption limit.
CARBON_STEEL_LIMIT_C = -29.0

# Below this, any water present freezes, and hydrates can form well above it
# in a gas stream carrying moisture.
FREEZING_C = 0.0


def flow_from_thermal_duty(
    duty_kw: float,
    temperature_in_c: float,
    temperature_out_c: float,
    specific_heat_kj_kgk: float,
    relative_density: float,
) -> float:
    """
    Volumetric flow in m3/h needed to carry a thermal duty over a temperature change.

    Energy balance on the process, not on the valve:

        m [kg/s]   = duty [kW] / (cp [kJ/kg K] * dT [K])
        V [m3/h]   = m / rho * 3600

    Cooling water, 250 kW removed with a 10 C rise:

    >>> round(flow_from_thermal_duty(250, 10, 20, 4.186, 1.0), 2)
    21.52
    """
    delta_t = abs(temperature_out_c - temperature_in_c)
    if delta_t == 0:
        raise InvalidFlowRateError(
            'inlet and outlet temperature are equal, so no flow carries the '
            'duty. A thermal duty needs a temperature change to define a flow.'
        )
    if duty_kw <= 0:
        raise InvalidFlowRateError(f'thermal duty must be positive, got {duty_kw} kW')
    if specific_heat_kj_kgk <= 0:
        raise InvalidFluidPropertyError(
            f'specific heat capacity must be positive, got {specific_heat_kj_kgk}'
        )
    if relative_density <= 0:
        raise InvalidFluidPropertyError(
            f'relative density must be positive, got {relative_density}'
        )

    mass_flow_kg_s = duty_kw / (specific_heat_kj_kgk * delta_t)
    density = relative_density * WATER_DENSITY_15C
    return mass_flow_kg_s / density * 3600.0


@dataclass(frozen=True)
class JouleThomsonEstimate:
    """
    Estimated cooling across the valve, with the warnings that follow from it.

    estimated is True only when a coefficient was available. A result with
    estimated=False has not been checked, which is not the same as safe.
    """

    estimated: bool
    temperature_drop_k: float | None
    outlet_temperature_c: float | None
    coefficient_k_per_bar: float | None
    warnings: tuple[str, ...]
    basis: str

    def __str__(self) -> str:
        if not self.estimated:
            return 'Joule-Thomson cooling not estimated'
        text = (
            f'approx {self.temperature_drop_k:.1f} K cooling, '
            f'outlet approx {self.outlet_temperature_c:.0f} C'
        )
        if self.warnings:
            text += ' | ' + ' | '.join(self.warnings)
        return text


NOT_ESTIMATED = JouleThomsonEstimate(
    estimated=False,
    temperature_drop_k=None,
    outlet_temperature_c=None,
    coefficient_k_per_bar=None,
    warnings=(),
    basis='no Joule-Thomson coefficient available for this fluid',
)


def estimate_joule_thomson(
    fluid: Fluid | None,
    inlet_temperature_c: float,
    pressure_drop_bar: float,
    coefficient_k_per_bar: float | None = None,
) -> JouleThomsonEstimate:
    """
    Estimate cooling across the valve and flag what it puts at risk.

    Natural gas letting down 40 bar from 20 C, which is the case that ices
    up real stations:

    >>> from .fluids import get_fluid
    >>> e = estimate_joule_thomson(get_fluid('methane'), 20.0, 40.0)
    >>> round(e.temperature_drop_k, 1), round(e.outlet_temperature_c, 1)
    (18.0, 2.0)
    """
    mu = coefficient_k_per_bar
    basis = 'supplied coefficient'
    if mu is None and fluid is not None:
        mu = fluid.jt_coefficient_k_per_bar
        basis = f'tabulated for {fluid.name}, {fluid.jt_reference}'
    if mu is None:
        return NOT_ESTIMATED

    drop = mu * pressure_drop_bar
    outlet = inlet_temperature_c - drop

    warnings: list[str] = []
    if outlet <= CARBON_STEEL_LIMIT_C:
        warnings.append(
            f'outlet below {CARBON_STEEL_LIMIT_C:.0f} C, carbon steel is '
            f'outside its impact test exemption and a low temperature '
            f'material is required'
        )
    elif outlet <= FREEZING_C:
        warnings.append(
            'outlet below freezing, expect icing on the valve body and check '
            'hydrate risk if the stream carries any moisture'
        )

    return JouleThomsonEstimate(
        estimated=True,
        temperature_drop_k=drop,
        outlet_temperature_c=outlet,
        coefficient_k_per_bar=mu,
        warnings=tuple(warnings),
        basis=(
            f'{basis}. Estimate only: the coefficient varies strongly with '
            f'temperature and pressure, so this is an order of magnitude and '
            f'not a number to design to.'
        ),
    )
