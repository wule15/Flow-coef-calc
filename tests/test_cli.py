"""
Command line interface.

Two things worth pinning. The CLI must not invent behaviour the library
refuses to have, in particular it must not default the pressure basis. And it
must not crash on its own output, which is not hypothetical: the first
version used a box drawing character and died on the Windows console
codepage, which is the machine it was written for.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flowcoefficient.cli import main  # noqa: E402


class TestOutputIsAsciiOnly:
    """
    The Windows console defaults to cp1252. Anything outside it raises
    UnicodeEncodeError at print time, so a sizing tool that emits a box
    drawing character crashes instead of answering.
    """

    @pytest.mark.parametrize('argv', [
        ['valves'],
        ['fluids'],
        ['convert', '--kv', '17.68'],
        ['liquid', '--flow', '25', '--p1', '6', '--p2', '4', '--basis', 'absolute'],
        ['gas', '--flow', '500', '--p1', '7', '--p2', '5', '--basis', 'absolute',
         '--temp', '20', '--fluid', 'air', '--style', 'globe'],
    ])
    def test_every_command_encodes_in_cp1252(self, argv, capsys):
        assert main(argv) == 0
        out = capsys.readouterr().out
        assert out
        out.encode('cp1252')      # raises if the output would crash on Windows


class TestPressureBasisIsStillRequired:
    def test_omitting_it_exits_rather_than_assuming(self):
        with pytest.raises(SystemExit) as exc:
            main(['liquid', '--flow', '25', '--p1', '6', '--p2', '4'])
        assert exc.value.code != 0

    def test_an_invalid_basis_is_rejected_by_the_parser(self):
        with pytest.raises(SystemExit):
            main(['liquid', '--flow', '25', '--p1', '6', '--p2', '4',
                  '--basis', 'barg'])


class TestRefusalsReachTheUser:
    def test_a_refused_calculation_exits_non_zero(self, capsys):
        code = main(['liquid', '--flow', '25', '--p1', '4', '--p2', '6',
                     '--basis', 'absolute'])
        assert code == 2
        assert 'refused' in capsys.readouterr().err

    def test_the_reason_is_printed_not_just_a_code(self, capsys):
        main(['liquid', '--flow', '25', '--p1', '4', '--p2', '6',
              '--basis', 'absolute'])
        assert 'pressure gradient' in capsys.readouterr().err


class TestItReportsWhatItDidNotCheck:
    """
    Same rule as the library. A blank line reads as a clean bill of health,
    so the absence of a check has to be stated.
    """

    def test_liquid_without_valve_data_says_the_check_was_skipped(self, capsys):
        main(['liquid', '--flow', '25', '--p1', '6', '--p2', '4',
              '--basis', 'absolute'])
        assert 'NOT CHECKED' in capsys.readouterr().out

    def test_gas_without_xt_says_the_check_was_skipped(self, capsys):
        main(['gas', '--flow', '500', '--p1', '7', '--p2', '6.7',
              '--basis', 'absolute', '--temp', '20', '--fluid', 'air'])
        assert 'NOT CHECKED' in capsys.readouterr().out

    def test_gas_without_xt_at_high_x_refuses_with_a_reason(self, capsys):
        code = main(['gas', '--flow', '500', '--p1', '7', '--p2', '5',
                     '--basis', 'absolute', '--temp', '20', '--fluid', 'air'])
        assert code == 2
        assert 'undersizes' in capsys.readouterr().err

    def test_a_choked_valve_says_so_in_capitals(self, capsys):
        main(['gas', '--flow', '2000', '--p1', '60', '--p2', '5',
              '--basis', 'absolute', '--temp', '20', '--fluid', 'co2',
              '--style', 'globe'])
        assert 'CHOKED' in capsys.readouterr().out


class TestAlternativeInputs:
    def test_pressure_drop_instead_of_outlet(self, capsys):
        assert main(['liquid', '--flow', '25', '--p1', '6', '--dp', '2',
                     '--basis', 'absolute']) == 0
        assert 'Kv' in capsys.readouterr().out

    def test_thermal_duty_instead_of_flow(self, capsys):
        assert main(['liquid', '--duty', '250', '--t-in', '10', '--t-out', '20',
                     '--fluid', 'water', '--p1', '4', '--dp', '1.5',
                     '--basis', 'gauge']) == 0
        assert 'thermal duty' in capsys.readouterr().out
