# Flow Coefficient

Valve sizing to IEC 60534-2-1. Works out the flow coefficient a duty needs, and tells you when the answer stopped meaning what you think it means.

Python 3.10 or newer. No dependencies, and there is a test that enforces that.

---

## Why it exists

A sizing calculation returns a number. The number does not tell you that the valve is choked, that the fluid is about to cavitate, that the flow went laminar and the equations no longer apply, or that Joule-Thomson cooling just took the body below the temperature its material is rated for.

Every one of those produces a valve that is wrong in service, and none of them look wrong on the page.

So this library returns a result object rather than a float, and the rule it follows throughout is that **it says when it did not check something**. `is_choked=False` and `choked_check_performed=False` mean the library had no valve data and did not look. That is a different statement from looking and finding the valve clear, and confusing the two is how somebody installs a valve that cavitates.

---

## What it does

```python
from flowcoefficient import liquid_flow_coefficient

result = liquid_flow_coefficient(
    thermal_duty=250,          # kW to remove
    temperature_in=10,         # C supply
    temperature_out=20,        # C return, the allowed rise
    fluid='water',
    inlet_pressure=4.0,
    pressure_drop=1.5,
    pressure_basis='gauge',
    valve_style='globe',
    pipe_diameter_mm=52.5,
    rated_kv=63,
)

print(result)
# Kv 17.57 (Cv 20.31) | inputs gauge, water | not choked | 2.76 m/s

print(result.flow_source)
# from thermal duty 250 kW over 10 C, cp 4.186 kJ/kg K

print(result.opening)
# required Kv 17.57 is 28 percent of rated 63
```

**Liquid sizing**, IEC 60534-2-1 clause 7, with the choked flow check from clauses 7.2 and 7.3 using the liquid pressure recovery factor FL and the critical pressure ratio FF.

**Gas and vapour sizing**, clause 8, with the choked condition, the expansion factor Y, and the specific heat ratio correction.

**Kv and Cv on every result.** No manual conversion, ever. You work in bar and cubic metres per hour, American catalogues publish Cv, and converting by hand is where mistakes happen.

**Absolute or gauge**, and you must say which. There is no default. A gauge reading treated as absolute produces a confident wrong answer with nothing in the output to reveal it, and stating the basis costs one word.

**Metric or imperial** in and out. Inputs are converted to bar and cubic metres per hour on entry, so there is one set of equations rather than a constants table per unit system.

**Seven fluids**, water, steam, air, nitrogen, methane, carbon dioxide and ammonia. Vapour pressure is stored as Antoine constants rather than a single number, because water at 20 C is 0.023 bar and at 80 C is 0.474 bar, and vapour pressure feeds straight into the cavitation check. Outside the range the constants were fitted over, the library raises rather than extrapolating.

**Seven valve styles** with typical FL, xT and Fd. Supplying your own beats the typical value, and the result records which it used.

**Flow regime screening.** Give it a viscosity and it works out the valve Reynolds number and tells you if the flow left the turbulent range the equations assume.

**Joule-Thomson cooling** estimated on gas, so a 60 bar CO2 letdown reports an outlet around -41 C instead of quietly handing you a valve body that will be brittle.

**Material screening** by temperature, ASME grade and EN number side by side, because the same casting is called A216 WCB in one datasheet and 1.0619 GP240GH in another.

**Velocity and oversizing checks** when you supply a pipe diameter or a candidate valve's rated coefficient.

---

## The case that shows why the result object exists

Same duty, same pressures, two valve styles:

```python
duty = dict(flow_rate=500, inlet_pressure=7.0, outlet_pressure=5.0,
            pressure_basis='absolute', temperature=20, fluid='air')

gas_flow_coefficient(**duty, valve_style='globe')
# Kv 5.756 (Cv 6.654) | x 0.286, Y 0.873 | not choked

gas_flow_coefficient(**duty, valve_style='ball')
# Kv 9.009 (Cv 10.41) | x 0.286, Y 0.667 | CHOKED
```

The ball valve is choked and needs 57 percent more capacity. xT is around 0.75 for a globe and around 0.20 for a ball, so a ball chokes at a far smaller pressure drop. A library that defaulted xT to the globe figure would report the same coefficient for both, and you would install a valve that cannot pass the flow.

That is why xT has no default, and why the result carries `is_choked` instead of returning a bare number.

---

## What it does not do

- **The Reynolds number factor FR is not implemented.** Viscous flow is screened and reported, not corrected. A transitional or laminar answer comes back labelled and should not be trusted as it stands.
- **The piping geometry factor Fp is not implemented.** Valves fitted between reducers will size slightly optimistically.
- Cavitation is detected at full choking only. Damage can begin before that point and the library will not flag it.
- No noise prediction, no two-phase or flashing flow, no valve travel or characteristic modelling.
- Material screening is on temperature alone. It excludes grades, it does not select one.
- The Joule-Thomson figure is an order of magnitude estimate, not a design number.
- No graphical or web interface yet. There is a library and a command line tool.

---

## The constant that was wrong, and how it was caught

Worth reading, because it shaped the test suite.

During development N9 in the gas equation was hardcoded from memory as 2.46. The correct value is 455.336. The library returned **Cv 1232 where the answer is Cv 6.65**, the difference between specifying a DN300 valve and a DN25 one.

**Every internal check passed while it was wrong.** The units were right, the choked logic was right, the expansion factor was right, and the result object printed a confident number two orders of magnitude out. Nothing in a sizing result tells you its magnitude is nonsense.

It was caught by cross-checking against the imperial sizing equation, a formula from a different lineage in different units. That comparison is now a permanent test, alongside a magnitude assertion that fails if a gas answer stops being a plausible valve size.

**N9 is now verified against the standard.** The ISA/IEC equation constants table gives `N9 = 21.2` for flow in m3/h at normal conditions, pressure in kPa, temperature in K, with the coefficient as Cv, for the form of the equation using molecular weight M. This library uses relative density, so:

```
21.2 (kPa, Cv)   x100     = 2120    (bar, Cv)
2120             x1.156   = 2450.7  (bar, Kv)
2450.7 / sqrt(28.96546)   = 455.36  (bar, Kv, relative density form)
```

against 455.336 derived independently here, a difference of 0.005 percent.

Two further agreements from the same table confirm the working rather than one number happening to land. N1 tabulates as 0.865 for Cv, which is 1.000 for Kv and is why the liquid equation carries no visible constant. And the ratio of the standard to normal condition constants, 22.4/21.2, matches 288.65/273.15, confirming the reference temperature handling.

All three are tests.

---

## Command line

Installed as `flowcoeff`, or run with `python -m flowcoefficient.cli`. No dependencies, argparse is standard library.

```bash
flowcoeff liquid --duty 250 --t-in 10 --t-out 20 --fluid water                  --p1 4 --dp 1.5 --basis gauge --style globe                  --pipe 52.5 --rated-kv 63
```
```
--------------------------------------------------------------
  Kv      17.57        Cv      20.31
--------------------------------------------------------------
  pressure basis             gauge
  inlet                      5.013 bar absolute
  outlet                     3.513 bar absolute
  flow                       21.52 m3/h (from thermal duty 250.0 kW over 10 C)
  vapour pressure            0.01201 bar
  FL                         0.9 (typical for globe)

  choked flow                not choked
  flow regime                not checked, turbulent assumed
  line velocity              2.76 m/s (erosional limit 3.9 m/s)
  valve opening              required Kv 17.57 is 28 percent of rated 63
--------------------------------------------------------------
```

Every figure that fed the answer is shown, and anything the library declined to check says so rather than being left blank, because a blank line reads as a clean bill of health.

`flowcoeff gas` does the same for compressible flow and adds the Joule-Thomson estimate and the material screening. `flowcoeff fluids` and `flowcoeff valves` print the tables. `flowcoeff convert --kv 17.68` is the two second answer.

Output is ASCII only, and there is a test that encodes every command's output as cp1252, because the first version used a box drawing character and crashed on the Windows console it was written for.

---

## Install

```bash
git clone https://github.com/YOUR-USERNAME/flow-coefficient.git
cd flow-coefficient
pip install -e .
```

Nothing is installed alongside it. To run the tests:

```bash
pip install -e ".[dev]"
pytest
```

---

## Tests

81 tests, no network, no files, nothing mocked.

The ones that matter are in `tests/test_standard_examples.py`, because they compare against sources outside the library. Internal consistency is a weak claim: a library can be perfectly self-consistent and wrong by a constant factor, which is exactly what N9 was.

- Gas cross-checked against the imperial sizing equation, a different lineage in different units.
- A magnitude sanity check that fails if a gas answer stops being a plausible valve size.
- Kv and Cv derived from first principles and shown to match the published 1.156.
- Vapour pressure against steam table values at five temperatures.
- The same duty in metric and imperial, asserted to give the same coefficient.

`tests/test_refusals.py` pins the behavioural rules, including that "did not check" never reads as "checked and clear". `tests/test_no_dependencies.py` parses the package and fails if anything outside the standard library is imported, so the claim at the top of this file cannot quietly stop being true.

---

## Standards referenced

| | |
|---|---|
| IEC 60534-2-1 | Sizing equations for fluid flow under installed conditions. Clause 6 flow regime, clause 7 liquid, clause 8 gas |
| IEC 60534-2-3 | Flow capacity test procedures, the source of published FL, xT and Fd |
| API RP 14E | Erosional velocity limit for piping |
| ASME B31.3 | Impact test exemption at -29 C, the carbon steel floor |
| ASTM A216, A217, A351, A352 | Cast valve body grades |
| EN 10213 | European cast valve body grades |
| NIST Chemistry WebBook | Antoine constants and critical properties |

---

## Known weaknesses

The three I would raise first if you were reviewing this.

**A numerical constant was wrong by 185x and nothing internal caught it.** That was found by luck, not by process. There is now a cross-check and a magnitude assertion guarding the gas path, but the episode says something about the shape of the risk here: this library can be entirely self-consistent and wrong, and the only defence is comparison against outside sources. There are five such comparisons. There should be more.

**Fluid property data is a small hand-entered table.** Seven fluids, each cited, each with a validity range that is enforced. But a wrong Antoine constant would be invisible until somebody's cavitation prediction was wrong, and only water and ammonia are checked against published vapour pressures.

**The FR and Fp gaps are real, not cosmetic.** Viscous service and reducer-fitted valves are both ordinary situations, and in both the library returns a number it has told you not to fully trust. Reporting the limitation is better than hiding it, and it is not the same as handling it.

---

## Licence

MIT. See [LICENSE](LICENSE).
