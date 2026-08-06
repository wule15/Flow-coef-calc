"""
Command line interface. Standard library only, argparse.

    flowcoeff liquid --flow 25 --p1 6 --p2 4 --basis absolute
    flowcoeff gas --flow 500 --p1 7 --p2 5 --basis absolute --temp 20 \
                  --fluid air --style globe
    flowcoeff convert --kv 17.68
    flowcoeff fluids
    flowcoeff valves

The output is written for someone checking a number, not for a machine. Every
figure that fed the answer is shown, and anything the library declined to
check is stated rather than left blank, on the same principle as the result
objects: a silent omission reads as a clean bill of health.
"""

from __future__ import annotations

import argparse
import sys

from .checks import OPENING_BAND_HIGH, OPENING_BAND_LOW
from .coefficients import cv_to_kv, kv_to_cv
from .errors import FlowCoefficientError
from .fluids import FLUIDS
from .gas import gas_flow_coefficient
from .liquid import liquid_flow_coefficient
from .valves import VALVE_STYLES

# ASCII only. The Windows console defaults to cp1252, which cannot encode
# box drawing characters, and a sizing tool that crashes on its own output
# is worse than a plain one.
RULE = '-' * 62


def _line(label: str, value: str) -> str:
    return f'  {label:<26} {value}'


def _warnings(*checks) -> list[str]:
    out = []
    for check in checks:
        for warning in getattr(check, 'warnings', ()):
            out.append(warning)
    return out


def _print_common(result) -> None:
    print(RULE)
    print(f'  Kv {result.kv:>10.4g}        Cv {result.cv:>10.4g}')
    print(RULE)
    print(_line('pressure basis', result.pressure_basis))
    print(_line('inlet', f'{result.inlet_pressure_bar_a:.4g} bar absolute'))
    print(_line('outlet', f'{result.outlet_pressure_bar_a:.4g} bar absolute'))


def _report_liquid(result) -> None:
    _print_common(result)
    print(_line('flow', f'{result.flow_rate_m3h:.4g} m3/h ({result.flow_source})'))
    print(_line('relative density', f'{result.relative_density:.4g}'))
    if result.fluid:
        print(_line('fluid', result.fluid))
    if result.vapour_pressure_bar is not None:
        print(_line('vapour pressure', f'{result.vapour_pressure_bar:.4g} bar'))
    if result.ff is not None:
        print(_line('FF', f'{result.ff:.4g}'))
    if result.fl is not None:
        print(_line('FL', f'{result.fl:.4g} ({result.fl_source})'))

    print()
    if result.choked_check_performed:
        state = 'CHOKED, sized on the limited pressure drop' if result.is_choked else 'not choked'
        print(_line('choked flow', state))
        if result.is_choked:
            print(_line('  pressure drop used',
                        f'{result.effective_pressure_drop_bar:.4g} bar '
                        f'of {result.pressure_drop_bar:.4g} available'))
    else:
        print(_line('choked flow', 'NOT CHECKED, no FL or vapour pressure given'))

    if result.piping.checked:
        print(_line('Fp', str(result.piping)))
    if result.operating_point.located:
        print(_line('operating point', str(result.operating_point)))
    if result.cavitation.computed:
        print(_line('cavitation', str(result.cavitation)))
    print(_line('flow regime', str(result.flow_regime)))
    if result.velocity.checked:
        print(_line('line velocity', str(result.velocity)))
    if result.opening.checked:
        print(_line('valve opening', str(result.opening)))
    _print_warnings(
        _warnings(result.velocity, result.opening, result.cavitation), result)


def _report_gas(result) -> None:
    _print_common(result)
    print(_line('temperature', f'{result.temperature_k:.4g} K'))
    print(_line('relative density', f'{result.relative_density:.4g}'))
    print(_line('gamma', f'{result.gamma:.4g} (Fg {result.gamma_factor:.4g})'))
    if result.fluid:
        print(_line('fluid', result.fluid))
    print(_line('x', f'{result.pressure_drop_ratio:.4g}'))
    print(_line('Y', f'{result.expansion_factor:.4g}'))
    if result.xt is not None:
        print(_line('xT', f'{result.xt:.4g} ({result.xt_source})'))

    print()
    if result.choked_check_performed:
        if result.is_choked:
            print(_line('choked flow',
                        f'CHOKED, x limited to {result.limiting_ratio:.4g}'))
        else:
            print(_line('choked flow',
                        f'not choked, limit is x = {result.limiting_ratio:.4g}'))
    else:
        print(_line('choked flow', 'NOT CHECKED, no xT given'))

    if result.piping.checked:
        print(_line('Fp', str(result.piping)))
    if result.operating_point.located:
        print(_line('operating point', str(result.operating_point)))
    if result.velocity.checked:
        print(_line('outlet velocity', str(result.velocity)))
    if result.opening.checked:
        print(_line('valve opening', str(result.opening)))
    if result.joule_thomson.estimated:
        print(_line('Joule-Thomson', str(result.joule_thomson)))
    if result.materials.checked:
        print()
        print(_line('material', result.materials.headline))
        for m in result.materials.candidates[:4]:
            print(_line('  suitable', f'{m.asme:<10} / {m.en_number} {m.en_name}'))
        for m in result.materials.excluded[:4]:
            print(_line('  excluded', f'{m.asme:<10} / {m.en_number} {m.en_name}'))
        if result.materials.excluded:
            print()
            print('  ' + result.materials.caveat)

    _print_warnings(_warnings(result.joule_thomson), result)


def _print_warnings(warnings: list[str], result) -> None:
    regime = getattr(result, 'flow_regime', None)
    if regime is not None and regime.correction_needed:
        warnings = warnings + [regime.note]
    if warnings:
        print()
        for w in warnings:
            print(f'  !  {w}')
    print(RULE)


def _add_shared(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--p1', type=float, required=True, help='inlet pressure')
    parser.add_argument('--p2', type=float, help='outlet pressure')
    parser.add_argument('--dp', type=float, help='pressure drop, instead of --p2')
    parser.add_argument('--basis', required=True, choices=['absolute', 'gauge'],
                        help='required, there is no default')
    parser.add_argument('--units', choices=['metric', 'imperial'], default='metric')
    parser.add_argument('--fluid',
                        help=f'one of: {", ".join(sorted(FLUIDS))}. '
                             f'Aliases co2, nh3, n2, ch4, h2o and '
                             f'"natural gas" are also accepted')
    parser.add_argument('--style', dest='valve_style',
                        help=f'one of: {", ".join(sorted(VALVE_STYLES))}')
    parser.add_argument('--bore', dest='valve_diameter_mm', type=float,
                        help='valve bore in mm. With --rated-kv this places '
                             'the duty on the published FL and xT curve')
    parser.add_argument('--pipe', dest='pipe_diameter_mm', type=float,
                        help='line bore in mm, for Fp and the velocity check')
    parser.add_argument('--rated-kv', dest='rated_kv', type=float,
                        help="candidate valve's rated Kv, from the catalogue")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='flowcoeff',
        description='Valve flow coefficient calculation to IEC 60534-2-1.',
        epilog='Pressure basis is always required. Assuming it is the error '
               'most likely to produce a confident wrong answer.',
    )
    sub = parser.add_subparsers(dest='command', required=True)

    liq = sub.add_parser('liquid', help='size for an incompressible liquid')
    _add_shared(liq)
    liq.add_argument('--flow', type=float, help='volumetric flow rate')
    liq.add_argument('--duty', type=float, help='thermal duty in kW, instead of --flow')
    liq.add_argument('--t-in', dest='t_in', type=float, help='supply temperature, with --duty')
    liq.add_argument('--t-out', dest='t_out', type=float, help='return temperature, with --duty')
    liq.add_argument('--temp', type=float, help='fluid temperature, for vapour pressure')
    liq.add_argument('--sg', dest='relative_density', type=float, help='relative density')
    liq.add_argument('--fl', type=float, help='liquid pressure recovery factor')
    liq.add_argument('--viscosity', type=float, help='kinematic viscosity in cSt')
    liq.add_argument('--sigma-min', dest='sigma_threshold', type=float,
                     help='manufacturer cavitation threshold, sigma_mr or '
                          'sigma_id from the data sheet. Without it the index '
                          'is reported but not judged')

    gas = sub.add_parser('gas', help='size for a gas or vapour')
    _add_shared(gas)
    gas.add_argument('--flow', type=float, required=True, help='flow at normal conditions')
    gas.add_argument('--temp', type=float, required=True, help='inlet temperature')
    gas.add_argument('--sg', dest='relative_density', type=float, help='relative to air')
    gas.add_argument('--gamma', type=float, help='ratio of specific heats')
    gas.add_argument('--xt', type=float, help='pressure differential ratio factor')
    gas.add_argument('--z', dest='compressibility', type=float, default=1.0,
                     help='compressibility factor Z, default 1.0 for ideal gas')

    conv = sub.add_parser('convert', help='Kv and Cv conversion')
    group = conv.add_mutually_exclusive_group(required=True)
    group.add_argument('--kv', type=float)
    group.add_argument('--cv', type=float)

    sub.add_parser('fluids', help='list the fluid table')
    sub.add_parser('valves', help='list valve styles with FL, xT and Fd')
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        if args.command == 'convert':
            if args.kv is not None:
                print(f'Kv {args.kv:.6g}  =  Cv {kv_to_cv(args.kv):.6g}')
            else:
                print(f'Cv {args.cv:.6g}  =  Kv {cv_to_kv(args.cv):.6g}')
            return 0

        if args.command == 'fluids':
            print(f'{"fluid":<16}{"M g/mol":>9}{"pc bar":>9}{"gamma":>8}  vapour pressure range')
            print(RULE)
            for name, f in sorted(FLUIDS.items()):
                rng = (f'{f.antoine.min_k:.0f} to {f.antoine.max_k:.0f} K'
                       if f.antoine else 'not held')
                gamma = f'{f.gamma:.3g}' if f.gamma else '-'
                print(f'{name:<16}{f.molar_mass:>9.2f}{f.critical_pressure_bar:>9.1f}'
                      f'{gamma:>8}  {rng}')
            return 0

        if args.command == 'valves':
            print(f'{"style":<16}{"FL":>7}{"xT":>7}{"Fd":>7}  note')
            print(RULE)
            for name, v in sorted(VALVE_STYLES.items()):
                print(f'{name:<16}{v.fl:>7.2f}{v.xt:>7.2f}{v.fd:>7.2f}  {v.note}')
            print()
            print('  Placeholders at mid travel, not values from a standard.')
            print('  FL and xT vary across the valve travel, by a factor of')
            print('  sixteen on a full bore ball, so one figure per style is a')
            print('  convenience and nothing more. Give --bore and --rated-kv')
            print('  and the duty is placed on the published curve instead of')
            print('  using the numbers above.')
            return 0

        if args.command == 'liquid':
            result = liquid_flow_coefficient(
                flow_rate=args.flow, thermal_duty=args.duty,
                temperature_in=args.t_in, temperature_out=args.t_out,
                inlet_pressure=args.p1, outlet_pressure=args.p2,
                pressure_drop=args.dp, pressure_basis=args.basis,
                relative_density=args.relative_density, fluid=args.fluid,
                temperature=args.temp, fl=args.fl, valve_style=args.valve_style,
                kinematic_viscosity=args.viscosity,
                sigma_threshold=args.sigma_threshold,
                sigma_threshold_name='the supplied sigma threshold',
                pipe_diameter_mm=args.pipe_diameter_mm,
                valve_diameter_mm=args.valve_diameter_mm,
                rated_kv=args.rated_kv, units=args.units,
            )
            _report_liquid(result)
            return 0

        if (args.p2 is None) == (args.dp is None):
            print('\n  refused: give either --p2 or --dp, not both and not '
                  'neither\n', file=sys.stderr)
            return 2
        result = gas_flow_coefficient(
            flow_rate=args.flow, inlet_pressure=args.p1,
            outlet_pressure=args.p2 if args.p2 is not None else args.p1 - args.dp,
            pressure_basis=args.basis, temperature=args.temp,
            relative_density=args.relative_density, fluid=args.fluid,
            gamma=args.gamma, xt=args.xt, valve_style=args.valve_style,
            compressibility=args.compressibility,
            pipe_diameter_mm=args.pipe_diameter_mm,
            valve_diameter_mm=args.valve_diameter_mm,
            rated_kv=args.rated_kv, units=args.units,
        )
        _report_gas(result)
        return 0

    except FlowCoefficientError as exc:
        print(f'\n  refused: {exc}\n', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
