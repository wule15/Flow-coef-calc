# Flow Coefficient

Valve sizing to EN IEC 60534-2-1. Works out the flow coefficient a duty needs, and tells you when the answer stopped meaning what you think it means.

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

**Liquid sizing**, EN IEC 60534-2-1:2011 clause 6, with the choked flow check from clauses 6.2.2 and 6.2.3 using the liquid pressure recovery factor FL and the critical pressure ratio FF.

**Gas and vapour sizing**, clause 8, with the choked condition, the expansion factor Y, and the specific heat ratio correction.

**Kv and Cv on every result.** No manual conversion, ever. You work in bar and cubic metres per hour, American catalogues publish Cv, and converting by hand is where mistakes happen.

**Absolute or gauge**, and you must say which. There is no default. A gauge reading treated as absolute produces a confident wrong answer with nothing in the output to reveal it, and stating the basis costs one word.

**Metric or imperial in.** Inputs are converted to bar and cubic metres per hour on entry, so there is one set of equations rather than a constants table per unit system. Results are always reported in bar and m3/h whatever went in, and always carry both Kv and Cv.

**Seven fluids**, water, steam, air, nitrogen, methane, carbon dioxide and ammonia. Vapour pressure is stored as Antoine constants rather than a single number, because water at 20 C is 0.023 bar and at 80 C is 0.474 bar, and vapour pressure feeds straight into the cavitation check. Outside the range the constants were fitted over, the fluid table raises rather than extrapolating. The sizing functions catch that, skip the cavitation check and report `choked_check_performed=False`, rather than refusing an otherwise ordinary duty: water above 100 C is a common service and used to fail outright.

**Nine valve styles** with placeholder FL, xT and Fd. Read the next section before relying on them.

**Coefficients that follow the valve opening.** FL and xT are published against Cv/d², not as one number per style, and a full bore ball's xT spans a factor of sixteen across its own travel. Give a valve bore and a candidate rated Kv and the duty is placed on the published curve and the coefficients read off it, iterating to a tolerance because the coefficient and xT depend on each other. The result then says where the duty landed, and whether the valve will merely pass the flow or actually suit it.

**Piping geometry factor Fp**, IEC clause 5. A valve is routinely a size or two smaller than its line, and the reducers cost capacity. Give it the valve bore, the line bore and a candidate rated Kv and it corrects for them. A DN50 valve in a DN80 line loses about 9.5 percent, and a reduced bore ball in a line two sizes up can lose 40 percent. Without the correction the sizing is optimistic by exactly that much.

**Cavitation and flashing, not just choking.** Choked flow is the last event in a sequence, not the first: a valve can report "not choked" for years while eroding its trim. The library reports the ISA RP75.23 index `sigma = (p1 - pv) / (p1 - p2)` on every liquid duty, and compares it against a threshold when you supply one from a data sheet. It carries no thresholds of its own, because RP75.23 is explicit that they vary with both pressure and valve size, so a single number per style would be wrong in a way no better number could fix.

**Flashing is detected and refused rather than answered.** If the outlet sits below the vapour pressure the liquid leaves the valve as a two-phase mixture. EN IEC 60534-2-1 does not cover multiphase flow and ANSI/ISA-75.01.01 states the same exclusion in as many words, so the result says the coefficient describes a liquid that is not what is actually flowing, and points you at a package with a homogeneous equilibrium model.

**Flow regime screening.** Give it a viscosity and it works out the valve Reynolds number and tells you if the flow left the turbulent range the equations assume.

**Joule-Thomson cooling** estimated on gas, so a 60 bar CO2 letdown reports an outlet around -41 C instead of quietly handing you a valve body that will be brittle.

**Material screening** by temperature, ASME grade and EN number side by side, because the same casting is called A216 WCB in one datasheet and 1.0619 GP240GH in another.

**Velocity and oversizing checks** when you supply a pipe diameter or a candidate valve's rated coefficient. On gas, velocity is evaluated at the outlet, where the gas has expanded and is moving fastest, and it carries the rho v squared criterion for noise and erosion.

---

## The case that shows why the result object exists

Same duty, same pressures, two valve styles:

```python
duty = dict(flow_rate=800, inlet_pressure=10.0, outlet_pressure=5.0,
            pressure_basis='absolute', temperature=20, fluid='air')

gas_flow_coefficient(**duty, xt=0.75)   # globe
# Cv  6.32 | x 0.500, Y 0.778 | not choked

gas_flow_coefficient(**duty, xt=0.20)   # full bore ball
# Cv 11.66 | x 0.500, Y 0.667 | CHOKED
```

At a pressure drop ratio of 0.5 the ball is choked and the globe is not, so the ball needs substantially more capacity for the identical duty. A library that defaulted xT to the globe figure would report the same coefficient for both, and you would install a valve that cannot pass the flow.

Published xT for a full bore ball runs from about 0.42 down to 0.05 over its normal control range, so **this conclusion holds anywhere a ball is realistically operated.** That is the point: it does not depend on which single figure you trust, only on a ball's xT being far below a globe's. It is also why the library refuses to default xT at all.

That is why xT has no default, and why the result carries `is_choked` instead of returning a bare number.

---

## The valve data is the weakest thing in here, and it says so

**FL and xT are not constants. They vary across the valve travel, and for a rotary valve they vary enormously.**

Measured figures, from the Valmet/Neles sizing coefficients catalogue 10CV20EN, which publishes them against Cv/d² at ten travel points from nearly closed to fully open:

| valve | FL | xT |
|---|---|---|
| RotaryGlobe, linear trim | 0.93 to 0.83 | 0.72 down to 0.61 and back to 0.70 |
| V-port segment ball | 0.94 to 0.42 | 0.64 to 0.16 |
| Full bore ball, trunnion | 0.91 to 0.28 | **0.82 to 0.05** |
| Eccentric rotary plug | 0.91 to 0.76 | 0.62 to 0.40 |
| Triple eccentric disc | 0.87 to 0.36 | 0.53 to 0.11 |
| Butterfly, soft seated | 0.87 to 0.40 | 0.68 to 0.15 |
| Butterfly, concentric disc | 0.83 to 0.48 | 0.46 to 0.28 |

A full bore ball's xT spans a **factor of sixteen** across its own travel. Any single number for it is a point on a curve, not a property of the style.

So the figures in this library are **mid-travel placeholders**, picked inside the published range so it can answer when you have no data sheet. They are not from a standard and are not cited as if they were. Every result carries the published span next to the value it used:

```
xT used   : 0.2
xT source : placeholder for ball at mid travel. Published span 0.05 to 0.82
            across the travel, so take the data sheet figure for a sizing
            that has to be right
```

EN IEC 60534-2-3 defines the flow test a manufacturer runs to measure these. EN IEC 60534-2-1 Annex D, Table D.1 gives its own typical values and is marked **informative**, not normative, for the same reason.

---

## What it does not do

- **The Reynolds number factor FR is not implemented.** Viscous flow is screened and reported, not corrected. A transitional or laminar answer comes back labelled and should not be trusted as it stands.
- No noise prediction, no two-phase or flashing flow, no valve travel or characteristic modelling.
- Material screening is on temperature alone, and runs on the gas path only, since it exists to catch Joule-Thomson cooling. It excludes grades, it does not select one.
- Liquid density is not corrected for temperature. The result says so when the flowing temperature is far from the tabulated one.
- The Joule-Thomson figure is an order of magnitude estimate, not a design number.
- No graphical or web interface yet. There is a library and a command line tool.
- The CLI does not expose every API parameter. `vapour_pressure`, `critical_pressure`, `specific_heat`, `downstream_diameter_mm`, `intermittent_service` and `atmospheric_pressure_bar` are library-only, so an error message suggesting you pass one of them is addressed to the API rather than the command line.

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
  flow                       21.52 m3/h (from thermal duty 250.0 kW over 10 C, cp 4.186 kJ/kg K)
  relative density           1
  fluid                      water
  vapour pressure            0.01201 bar
  FF                         0.9579
  FL                         0.9 (placeholder for globe at mid travel. Published span 0.83
                             to 0.93 across the travel, so take the data sheet figure for a
                             sizing that has to be right)

  choked flow                not choked
  flow regime                flow regime not checked, turbulent assumed
  line velocity              2.76 m/s (erosional limit 3.9 m/s)
  valve opening              required Kv 17.57 is 28 percent of rated 63
--------------------------------------------------------------
```

Add `--bore` alongside `--rated-kv` and the FL line changes from a placeholder to a figure read off the published curve at the duty's own operating point, and an `operating point` line appears saying where that is.

Every figure that fed the answer is shown, and anything the library declined to check says so rather than being left blank, because a blank line reads as a clean bill of health.

`flowcoeff gas` does the same for compressible flow and adds the Joule-Thomson estimate and the material screening. `flowcoeff fluids` and `flowcoeff valves` print the tables. `flowcoeff convert --kv 17.68` is the two second answer.

Output is ASCII only, and there is a test that encodes every command's output as cp1252, because the first version used a box drawing character and crashed on the Windows console it was written for.

---

## Install

```bash
git clone https://github.com/wule15/Flow-coef-calc.git
cd Flow-coef-calc
pip install -e .
```

Nothing is installed alongside it. To run the tests:

```bash
pip install -e ".[dev]"
pytest
```

---

## Tests

299 tests, no network, no files, nothing mocked.

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
| EN IEC 60534-2-1:2011 | Sizing equations for fluid flow under installed conditions. Clause 6 liquid, 7 gas, 8 piping geometry, 9 Reynolds number, Annex A non-turbulent flow. Identical text to IEC 60534-2-1:2011 |
| EN IEC 60534-2-3 | Flow capacity test procedures. Defines how FL and xT are measured. The values here are **not** taken from it |
| EN 13480-2 | Metallic industrial piping, materials. Low temperature requirement under PED 2014/68/EU |
| EN 13445-2 | Unfired pressure vessels, materials |
| EN 10213 | Steel castings for pressure purposes. Primary source for the body grades |
| API RP 14E | Erosional velocity limit for piping |
| ISA RP75.23 | Considerations for evaluating control valve cavitation. The sigma index and its thresholds |
| ASME B31.3 | American counterpart to EN 13480 for the -29 C impact test boundary |
| ASTM A216, A217, A351, A352 | American cast grades, given beside the EN numbers |
| Valmet 10CV20EN | Manufacturer sizing coefficients catalogue, source of the published FL and xT spans |
| NIST Chemistry WebBook | Antoine constants and critical properties |

---

## Known weaknesses

The three I would raise first if you were reviewing this.

**A numerical constant was wrong by 185x and nothing internal caught it.** That was found by luck, not by process. There is now a cross-check and a magnitude assertion guarding the gas path, but the episode says something about the shape of the risk here: this library can be entirely self-consistent and wrong, and the only defence is comparison against outside sources. There are five such comparisons. There should be more.

**The valve style table is a set of placeholders, not measurements.** FL and xT vary by up to a factor of sixteen across a rotary valve's travel, so a single number per style is a convenience and nothing more. The library states the published span on every result and refuses to default xT, but a caller who ignores both will get a number built on a placeholder.

**Fluid property data is a small hand-entered table.** Seven fluids, each cited, each with a validity range that is enforced. But a wrong Antoine constant would be invisible until somebody's cavitation prediction was wrong, and only water and ammonia are checked against published vapour pressures.

**FR is still not implemented.** Viscous service is screened and labelled but not corrected, so a transitional or laminar answer is a number the library has told you not to trust. That correction is implicit, the Reynolds number depends on the coefficient you are solving for, so it needs iteration. Doing it badly would produce a wrong answer that looks exactly as confident as a right one, which is why it is still outstanding rather than rushed.

---

## Licence

MIT. See [LICENSE](LICENSE).
