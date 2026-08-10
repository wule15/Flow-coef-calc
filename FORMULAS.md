# Formulas, the pre-implementation record

**Status: historical. This is the document the physics was checked against
before any code existed, kept because it is the record of that review. It is
not a description of the library as it stands.**

Five things were built after it was written and are not in it: the piping
geometry factor Fp and FLP, the Reynolds flow regime screening, the fluid
property table, the material screening, and the travel curves that read FL
and xT off published data at the duty's own operating point.

Two numbers in it were later found wrong and are corrected in the code, not
here. N9 in the gas equation shipped 185 times too small before being derived
properly and then verified against the tabulated standard value. N2 in the
piping factor was 1.79 times too large because a Cv to Kv conversion was
applied backwards.

**For what the library actually does, read the README and the module
docstrings, which are kept current. For what is still open, read
RESEARCH.md.**

The original text follows unchanged.

---

Nothing is implemented yet. This document exists so the physics is checked
before any code is written, which is the order the brief sets.

Source standard throughout: **EN IEC 60534-2-1:2011**, *Industrial-process control
valves, Part 2-1: Flow capacity, Sizing equations for fluid flow under
installed conditions*. Clause numbers are given where the equation maps to
one cleanly, and marked as such where the mapping is looser.

Read the **Questions for you** section at the end first. Those are the five
places where I want your judgement rather than your confirmation.

---

## 1. Kv and Cv conversion

Two definitions of the same physical idea, differing only in the units they
were defined in.

- **Kv** is the flow of water in m3/h through the valve at a pressure drop
  of 1 bar, at 5 to 40 degrees C.
- **Cv** is the flow of water in US gallons per minute at a pressure drop of
  1 psi, at 60 degrees F.

```
Cv = 1.156 x Kv
Kv = 0.865 x Cv
```

**Where the number comes from.** It is the unit conversion, not a fitted
constant:

```
1 m3/h  = 4.40287 US gpm
1 bar   = 14.5038 psi
Cv/Kv   = 4.40287 / sqrt(14.5038) = 4.40287 / 3.80839 = 1.1561
```

Note `1.156 x 0.865 = 1.00`, so the pair round-trips. I intend to keep both
constants rather than deriving one from the other, because these are the two
values printed in manufacturer literature and an engineer checking the
library should find what they expect. There is a test asserting the
round-trip closes to within 0.1 percent.

**Check for you:** some sources give 1.16 and 0.86. I have used the more
precise pair. Tell me if your practice uses different rounding.

---

## 2. Liquid flow, non-choked

EN IEC 60534-2-1:2011, clause 6.1, turbulent non-choked flow.

```
              /  rho1 / rho0
C = Q  x  sqrt| ---------------
              \   p1 - p2
```

written for the calculation as

```
C = Q / ( N1 x sqrt( (p1 - p2) / (rho1 / rho0) ) )
```

Where

| Symbol | Meaning | Unit I intend to use internally |
|---|---|---|
| C | flow coefficient, Kv | m3/h at 1 bar |
| Q | volumetric flow rate | m3/h |
| p1 | inlet absolute pressure | bar |
| p2 | outlet absolute pressure | bar |
| rho1/rho0 | relative density, water at 15 C = 1.0 | dimensionless |
| N1 | numerical constant | 0.0865 for Q in m3/h and p in kPa, **1.0** for Q in m3/h and p in bar |

**The N1 point matters and it is where I expect sizing code to go wrong.**
N1 is not a physical constant, it is a units bookkeeping factor, and it takes
a different value for every unit combination. My proposal is that the library
works internally in m3/h and bar, where N1 = 1, and converts at the boundary.
That way there is exactly one constant in the physics and the unit handling
is visibly separate from it.

**Worked example I intend to use in the docstring:**
Water, 25 m3/h, p1 = 6 bar a, p2 = 4 bar a, relative density 1.0.

```
C = 25 / sqrt(2.0 / 1.0) = 25 / 1.4142 = 17.68 Kv
```

which is Cv 20.4. A DN50 globe valve, which is a realistic answer.

---

## 3. Liquid flow, choked

EN IEC 60534-2-1:2011, clause 6.2.2 and 6.2.3.

Liquid chokes when the pressure drop is large enough that the fluid
flashes or cavitates at the vena contracta. Beyond that point, increasing
the pressure drop does not increase flow, and sizing on the full pressure
drop **oversizes the valve**.

Choked when

```
p1 - p2  >=  FL^2 x ( p1 - FF x pv )
```

and the pressure drop used in the sizing equation is then capped at

```
dP_max = FL^2 x ( p1 - FF x pv )
```

Liquid critical pressure ratio factor, clause 6.2.3:

```
FF = 0.96 - 0.28 x sqrt( pv / pc )
```

| Symbol | Meaning |
|---|---|
| FL | liquid pressure recovery factor, from the valve manufacturer, typically 0.85 to 0.95 globe, 0.6 to 0.7 ball and butterfly |
| pv | vapour pressure of the liquid at inlet temperature, absolute |
| pc | thermodynamic critical pressure of the liquid, absolute |
| FF | liquid critical pressure ratio factor |

**Design intent:** if `fl` and `vapour_pressure` are not supplied, the
library does the non-choked calculation and returns `is_choked=False` with a
flag saying the check was not performed. It does **not** silently assume
non-choked. Assuming would be the dangerous default, because the failure
mode is an undersized answer that looks fine.

**Check for you:** is 0.96 and 0.28 the pairing you use, and do you want pc
defaulted for water (221.2 bar a) or always required?

---

## 4. Gas and vapour flow

EN IEC 60534-2-1:2011, clause 7.

```
                        /       x
C = Q / ( N9 x p1 x Y x sqrt| ------------------ |
                        \  Gg x T1 x Z
```

Pressure differential ratio:

```
x = ( p1 - p2 ) / p1
```

Expansion factor, clause 7.4:

```
Y = 1 - x / ( 3 x Fgamma x xT )
```

Specific heat ratio factor, clause 7.3:

```
Fgamma = gamma / 1.40
```

| Symbol | Meaning |
|---|---|
| Q | volumetric flow at standard conditions, Nm3/h |
| p1 | inlet absolute pressure, bar |
| x | pressure differential ratio, dimensionless |
| xT | pressure differential ratio factor at choked flow, from the manufacturer, 0.75 typical for globe |
| gamma | ratio of specific heats, 1.40 air, 1.31 methane, 1.30 steam |
| Gg | gas relative density, air = 1.0 |
| T1 | inlet absolute temperature, K |
| Z | compressibility factor, 1.0 for ideal |
| N9 | numerical constant, unit dependent |

### Choked gas flow

Gas chokes when

```
x  >=  Fgamma x xT
```

At and beyond that point:

- `x` used in the equation is **clamped** to `Fgamma x xT`
- `Y` takes its limiting value of **2/3**, which falls out of the Y equation
  at `x = Fgamma x xT`

This is the single most important behaviour in the library. Sizing a choked
service on the actual pressure drop rather than the limited one gives a
**smaller** coefficient than reality requires, and the valve is undersized in
service. This is why I want the function returning a result object carrying
`is_choked` rather than a bare number.

**Sanity check on Y:** at `x = Fgamma x xT`,
`Y = 1 - (Fgamma x xT) / (3 x Fgamma x xT) = 1 - 1/3 = 0.667`. Consistent.

---

## 4a. Non-turbulent flow, the Reynolds factor FR

Source: EN IEC 60534-2-1:2011 Annex A (normative), Equations A.6, A.7, A.8.
Implemented on the liquid path only. The gas path additionally needs the
non-turbulent expansion factor Y of Eq. A.5, which is not implemented.

Below Rev = 10 000 the turbulent equations overstate what the valve passes, so
the required coefficient becomes `C_turbulent / FR`, FR <= 1 (Eq. A.2). Trim is
classified on the RATED coefficient so the branch cannot flip mid-iteration
(Eq. A.8):

```
Crated / (d^2 x N18) >= 0.016   ->  full-size trim
Crated / (d^2 x N18) <  0.016   ->  reduced trim
```

The intermediate n, then FR (Eq. A.8, A.6, A.7):

```
full-size:      n = N2 / (C/d^2)^2
reduced:        n = 1 + N32 x (C/d^2)^(2/3)

laminar,   Rev < 10:   FR = Min[ (0.026/FL) x sqrt(n x Rev) , 1 ]
transitional, Rev>=10: FR = Min[ 1 + (0.33 x sqrt(FL) / n^0.25) x log10(Rev/10000) ,
                                 (0.026/FL) x sqrt(n x Rev) , 1 ]
```

| Symbol | Meaning | Value / unit |
|---|---|---|
| Rev | valve Reynolds number, from section on regime screening (Eq. 23) | dimensionless |
| n | intermediate variable, Eq. A.8 | dimensionless |
| FL | liquid pressure recovery factor | dimensionless |
| N2 | numerical constant, D in mm, C as Kv | 1.60e-3 |
| N18 | trim-classification constant, C as Kv | **0.865** (Cv column is 1.00) |
| N32 | reduced-trim n constant, C as Kv | **140** (Cv column is 127) |

FR depends on the coefficient through Rev, so it is solved by fixed point:
`C_next = C_turbulent / FR(C)`, to the same tolerance the operating-point loop
uses. The Kv constants differ from the Cv figures printed in the standard's
worked example: N18 scales linearly (0.865 x 1.00 = 0.865), N32 by the 2/3
power (127 / 0.865^(2/3) = 139.9), because C enters n to the 2/3 power. Using
the Cv figure in a Kv library is the column swap that produced the old N9 error.

**Pinned example.** The standard's segmented-ball case, FL = 0.98, Rev = 1202,
n = 1.235, is transitional and gives FR = 0.715. The transitional term alone is
0.71487; the laminar term is 1.022, capped to 1; the Min is 0.715. Reproduced
in the test suite. Note it is the sqrt(FL) form: plain FL gives 0.718.

---

## 5. Unit conversion

No standard governs these, they are definitions.

**Pressure**, internal unit bar:

```
1 bar = 100 kPa = 0.1 MPa = 100000 Pa = 14.503774 psi
```

**Flow**, internal unit m3/h:

```
1 m3/h = 16.6667 L/min = 4.402868 US gpm
```

**Temperature**, internal unit K:

```
K = C + 273.15
K = (F + 459.67) x 5/9
```

**Gauge and absolute is the trap.** Every equation above uses absolute
pressure. Plant instruments read gauge. My intent is that the API takes
absolute only, names every parameter `..._absolute`, and provides an explicit
`gauge_to_absolute(value, atmospheric=1.01325)` helper so a conversion is
always visible in the calling code rather than assumed.

**Check for you:** do you want 1.01325 bar as the default atmospheric, or
1.0 because that is what people use on site?

---

## 6. Validation, what raises rather than returns

| Condition | Behaviour |
|---|---|
| p2 > p1 | raise, flow cannot go up a pressure gradient |
| p1 or p2 <= 0 absolute | raise, absolute pressure cannot be zero or negative |
| flow rate <= 0 | raise |
| relative density <= 0 | raise |
| xT outside 0 to 1 | raise |
| FL outside 0 to 1 | raise |
| gamma outside 1.0 to 2.0 | raise |
| temperature <= 0 K | raise |
| choked condition reached | **return normally**, with `is_choked=True` |

Choking is a physical operating state, not an input error, so it is reported
and not raised. Everything else in that table is a nonsensical input and the
library refuses rather than guessing.

---

---

# Decisions taken, 3 August 2026

Your answers, and what they mean for the design.

## Atmospheric pressure

**1.01325 bar.** Settled. It is the standard value and it is what the
conversion should use. A site engineer wanting 1.0 can pass it explicitly.

## Absolute and gauge, both accepted

Every pressure input accepts either basis, and the choice is recorded and
reported rather than assumed.

```python
result = liquid_flow_coefficient(
    flow_rate=25,
    inlet_pressure=5.0,
    outlet_pressure=3.0,
    pressure_basis='gauge',        # or 'absolute'
    ...
)

result.pressure_basis          # 'gauge'   what you gave it
result.inlet_pressure_absolute # 6.01325   what the physics used
print(result)
# Kv 17.7 (Cv 20.4) | inputs gauge, converted to absolute | not choked
```

Three rules make this safe:

1. `pressure_basis` has **no default**. You state it every time. A default
   here is exactly the assumption that produces a silently wrong answer, and
   the cost of typing it is one word.
2. The result object carries both the basis you supplied and the absolute
   values actually used, so a review of the calculation shows the conversion
   rather than hiding it.
3. `__str__` on the result prints the basis. If the number ends up pasted
   into an email, the basis goes with it.

Gauge inputs are converted immediately on entry and every equation downstream
sees absolute only. There is no code path where a gauge value reaches a
formula.

## Metric and imperial, both accepted

Same principle, applied to units.

```python
liquid_flow_coefficient(
    flow_rate=110,                 # US gpm
    inlet_pressure=87,             # psi
    outlet_pressure=58,            # psi
    units='imperial',              # or 'metric'
    pressure_basis='gauge',
)
```

**What actually happens, and why the formulas do not change.** The equations
are identical in both systems. What changes is the numerical constant N,
which is not physics, it is units bookkeeping. IEC publishes a table of N
values precisely because the equation stays put while the units move.

Two ways to build this:

| Approach | What it means |
|---|---|
| Carry an N table per unit set | Several constants, several code paths, each needing its own test. This is what most reference implementations do, and it is where their bugs live |
| Convert at the boundary, one constant | Inputs converted to bar and m3/h on entry, N1 = 1, one physics path, conversion tested separately from physics |

**I am building the second**, and both give identical answers. The reason is
testability. With one physics path, a sizing bug and a units bug cannot
disguise each other, and the unit conversions can be tested to a tolerance
without touching the flow equations at all.

The docstrings will still list the IEC N values for each unit set, so an
engineer checking the library against a catalogue can follow the standard's
own presentation. The library does not use them; it shows them.

Output carries both systems, so no manual conversion is ever needed:

```python
result.kv        # 17.68
result.cv        # 20.44
```

## Kv and Cv: both, always

See the explanation section below. The decision is that the result object
carries both, so the question of which is internal never reaches the caller.
Internally the library works in Kv because it works in SI, but nothing
outside the module depends on that.

## xT and FL

See the explanation below. The decision is:

- **No silent defaults.** Passing neither is allowed, but then the choked
  check is not performed and the result says so explicitly with
  `choked_check_performed=False`. It never returns `is_choked=False` when it
  simply did not look.
- **A valve style shortcut exists** for when you do not have catalogue data:
  `valve_style='globe'` fills in typical values, and the result records that
  the figures were typical rather than measured.

```python
result.fl_source     # 'typical for globe' | 'supplied' | 'not provided'
```

The distinction between "checked and not choked" and "did not check" is the
whole point. They are not the same statement and the library must not
conflate them.

---

# Explanations

## FL, the liquid pressure recovery factor

**The physical picture.** Fluid passing through a valve accelerates through
the narrowest section, the vena contracta, just downstream of the seat. Where
velocity is highest, static pressure is lowest. Downstream the passage opens
out, velocity falls and pressure partially recovers.

So the lowest pressure in the whole valve is not the outlet pressure. It is
lower, and it happens somewhere you cannot put a gauge.

```
p1 ─────╮                    ╭────── p2
         ╲                  ╱
          ╲________________╱          ← recovery
                    ↑
              vena contracta
              lowest pressure in the valve
```

FL measures how much of that dip comes back.

| FL | Behaviour | Typical valve |
|---|---|---|
| 0.90 to 0.98 | Little recovery. Vena contracta pressure stays near p2 | Globe, tortuous path, high friction |
| 0.80 to 0.90 | Moderate | Angle, eccentric plug |
| 0.50 to 0.70 | Strong recovery. Deep dip, then a large rebound | Ball, butterfly, streamlined |

**Why it decides when choking starts.** Cavitation and flashing begin when
the pressure at the vena contracta falls to the vapour pressure of the
liquid. Because a low-FL valve dips much further for the same overall
pressure drop, it reaches vapour pressure sooner. Two valves on identical
duty, same p1 and p2, and the butterfly can be cavitating while the globe is
not.

That is why FL cannot be defaulted honestly. Using 0.9 on a butterfly valve
tells you the valve is fine when it is eroding.

**Where the number comes from.** Measured by flow test to EN IEC 60534-2-3 and
published by the manufacturer, usually per valve size and per travel
position. It is a property of that valve, not of your process.

## xT, the pressure differential ratio factor

The gas equivalent, and the same physics.

For compressible flow the limit is not vapour pressure, it is sonic
velocity. Gas accelerating through the vena contracta eventually reaches the
speed of sound there, and once it does, lowering the downstream pressure
further cannot increase the mass flow. The valve is choked.

xT is the value of `x = (p1 - p2) / p1` at which that happens, measured with
air.

| xT | Typical valve |
|---|---|
| 0.70 to 0.75 | Globe |
| 0.30 to 0.50 | Butterfly |
| 0.15 to 0.25 | Ball, segmented |

**Read that table again, because the spread is the point.** A ball valve can
choke at a pressure drop ratio of 0.2, where a globe valve is nowhere near
it. Size a ball valve using the globe default of 0.75 and the library would
report not choked at x = 0.5 when the valve has in fact been choked since
0.2. You would then size on a pressure drop the valve cannot use, get a
coefficient that is too small, and install a valve that cannot pass the
required flow.

That is the specific accident the no-default rule exists to prevent.

`Fgamma` corrects xT from air to another gas: `Fgamma = gamma / 1.40`, since
xT is measured on air, whose gamma is 1.40.

## Kv or Cv "internally": what the question actually meant

It is a question about where the conversion happens, not about the physics.

The library computes one number and everything else derives from it. If that
number is Kv, the sizing functions produce Kv and anyone wanting Cv converts.
If it is Cv, the reverse. The concern is that the IEC constants differ
depending on which coefficient and which units you are solving in, so mixing
the two inside the calculation is a real source of error.

**The resolution is to stop making it a choice.** Internally the library
works in Kv, because it works in SI and Kv is the SI-native coefficient. But
every result object carries both:

```python
result.kv    # 17.68
result.cv    # 20.44
```

So a caller never converts anything and never needs to know which one is
"internal". Given you work in bar and m3/h but catalogues from American
manufacturers publish Cv, having both on every result removes a conversion
step from your actual work, which is where mistakes get made.

---

---

# Fluid properties

Decided 3 August 2026: build it, as a module inside this library rather than
a separate tool, and scope it deliberately.

## Why not default pc to water

Defaulting the critical pressure to water means a wrong number appears
silently the moment somebody sizes for ammonia. It fails the same test FL and
xT failed. The alternative, requiring pc on every call, is honest but makes
the library tedious to use for the case it should handle best.

A fluid table solves both. You name the medium, the properties arrive, and
each one is traceable to a source.

## Scope, and the line that keeps this bounded

**This is not a thermophysical property library.** It is the properties the
EN IEC 60534 sizing equations need, for common industrial fluids, cited, with
stated validity ranges.

That framing matters. A general property library is a far larger project,
already exists in better forms, and would need dependencies this project
should not have. Everything below is arithmetic and fits the standard library
rule.

Properties held, and nothing else:

| Property | Used by | Nature |
|---|---|---|
| Critical pressure, pc | Liquid choked, FF | Constant per fluid |
| Vapour pressure, pv | Liquid choked | **Function of temperature** |
| Relative density | Liquid sizing | Function of temperature |
| Ratio of specific heats, gamma | Gas, Fgamma | Near constant over normal ranges |
| Molar mass | Gas relative density | Constant |

## Vapour pressure is not a constant, and this is the part to get right

This is the one thing that would make a naive fluid table dangerous. Water at
20 C has a vapour pressure of 0.0234 bar. At 100 C it is 1.013 bar. At 180 C
it is about 10 bar. A table holding one number for water is wrong almost
everywhere.

So pv is stored as a correlation, not a value. The **Antoine equation**:

```
log10(P) = A - B / (C + T)
```

Three constants per fluid, published for every common industrial fluid, valid
over a stated temperature range, and pure arithmetic. Source: NIST Chemistry
WebBook, which publishes the constants and the range each set is fitted over.

**Outside the fitted range the library raises.** It does not extrapolate.
Antoine constants fitted between 1 and 100 C give confidently wrong answers at
200 C, and an extrapolated vapour pressure feeds straight into a cavitation
prediction. Refusing is the only defensible behaviour, and it is consistent
with how the rest of this library treats inputs it cannot honour.

## Shape

```python
@dataclass(frozen=True)
class Fluid:
    name: str
    critical_pressure_bar: float
    molar_mass: float
    gamma: float | None
    antoine: AntoineConstants | None
    relative_density_15c: float | None
    source: str
    valid_range_k: tuple[float, float]
```

Used like this:

```python
result = liquid_flow_coefficient(
    flow_rate=25,
    inlet_pressure=6.0,
    outlet_pressure=4.0,
    pressure_basis='absolute',
    fluid='water',
    temperature=80,               # C
    fl=0.90,
)

result.vapour_pressure_bar    # 0.4736, computed at 80 C
result.fluid_source           # 'NIST WebBook, Antoine 273-373 K'
result.is_choked              # False
```

**Every property remains overridable.** Passing `vapour_pressure=` explicitly
beats the table, and the result records which was used. Someone with better
data for their actual fluid must never be forced to accept a book value.

## Proposed starting set

Seven fluids, chosen to cover industrial process work rather than to be
comprehensive:

| Fluid | Why |
|---|---|
| Water | The default case, and the reference for relative density |
| Steam | Different equations territory, but the properties are needed |
| Air | The reference for gas relative density, and xT is measured on it |
| Nitrogen | Utility and blanketing |
| Methane | Natural gas, the closest single-component stand-in |
| Carbon dioxide | Process and utility, and it behaves badly enough to matter |
| Ammonia | Refrigeration, and the case where a water default would hurt most |

Say which of these you do not need and which are missing. Adding one later is
a table entry and a citation, not a code change.

## The honest cost

This does complicate the build. Three specific costs, stated plainly:

1. **It roughly doubles the test surface.** Each fluid needs its correlation
   checked against published values at two or three temperatures, and each
   validity boundary needs a test asserting it raises.
2. **The data has to be right, and engineers will check it.** A wrong Antoine
   constant is invisible until somebody's cavitation prediction is wrong. This
   is why every entry carries a citation and why the validity range is
   enforced rather than documented.
3. **It delays a working library.** The sizing equations alone would be
   finished sooner.

Against that, it turns the library from a formula wrapper into something
usable, and looking up vapour pressure at temperature is exactly the tedious,
error-prone step that a tool should remove.

**Suggested order:** sizing equations first with fluid properties required as
explicit arguments, then the fluid table as a convenience layer over the top.
That way there is a correct, tested, useful library at the halfway point, and
the fluid work cannot leave the project stranded half-built.

---

# Still open

**The gas equation form.** I have written the volumetric version, because a
flow meter usually gives you volume. IEC also gives a mass flow form using N6
and inlet density. If your sizing is usually mass based, say so and I will
make that primary and the volumetric one the wrapper.

**FF constants**, 0.96 and 0.28.

**The fluid list above**, if seven is wrong in either direction.

**The rest of the physics in sections 1 to 4 above**, which is what still
needs your verification before I write any code.
