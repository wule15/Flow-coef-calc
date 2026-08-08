# Research notes, 5 August 2026

Written while you were out. Nothing here is implemented. It is a decision
document: what I found, what it would cost, and what I would and would not
build.

Sources are named inline. Where I could not get the primary standard, I say
so rather than paraphrasing a secondary and presenting it as the standard.

---

## 1. Two-phase and mixed medium flow

**The headline: the standard this library implements explicitly excludes it.**

ANSI/ISA-75.01.01 and EN IEC 60534-2-1 both state that the compressible flow
equations are not intended for multiphase streams, naming gas-liquid,
vapour-liquid and gas-solid mixtures. That is not an omission in the library.
It is the boundary of the standard.

So anyone sizing a flashing line, a wet gas, a slurry or a cryogenic
two-phase service is outside EN IEC 60534-2-1:2011 entirely, and into proprietary
methods and engineering judgement.

### What practice actually does

Two approaches dominate, and they differ in rigour.

**Homogeneous model.** Treat the mixture as one fluid with a density weighted
by vapour quality:

    rho_mix = x * rho_gas + (1 - x) * rho_liquid

with x the vapour mass fraction, then size with the liquid equation. Cheap,
crude, and it assumes the phases move at the same velocity and stay mixed.

**Homogeneous Equilibrium Model, HEM.** Compute the quality from the inlet
and outlet enthalpies, so the flashing that happens across the valve is part
of the calculation rather than an input. Blend the phase specific volumes
into a two-phase specific volume that varies through the expansion. This is
what commercial sizing packages use and it is materially better, because in a
flashing service the quality at the outlet is not the quality at the inlet,
and the homogeneous model silently assumes it is.

### What it would cost to build honestly

HEM needs enthalpy and saturation properties as a function of pressure and
temperature for every fluid. That is a full thermophysical property library,
which this project explicitly is not, and which cannot be done in the
standard library for anything except water.

**My recommendation: do not implement two-phase sizing.**

Not because it is hard, but because a two-phase number produced from a
seven-fluid hand-entered table would be the most confidently wrong thing in
the library, in the service where being wrong destroys trim fastest.

**What I would do instead**, and this is small: **detect the condition and
refuse.** The library already computes vapour pressure and knows the outlet
pressure. If `p2 < pv` the liquid is flashing across the valve and the liquid
equations do not describe it. Right now the library returns `is_choked=True`
and a coefficient, which is a defensible answer for choked liquid flow but
says nothing about the fact that what leaves the valve is a two-phase
mixture.

A `flashing=True` flag with a note saying the outlet is below vapour
pressure, that the service is two-phase, that EN IEC 60534-2-1:2011 does not cover
it, and that a HEM-based package should be used, is about forty lines and is
honest. It is the same rule as everywhere else: report the condition, refuse
to guess the number.

---

## 2. Cavitation before choking

The reviewer flagged this and the research confirms it is a real gap with a
real standard behind it.

**ISA RP75.23-1995, Considerations for Evaluating Control Valve Cavitation.**
It defines a cavitation index:

    sigma = (p1 - pv) / (p1 - p2)

and then a series of thresholds, each of which is a *different valve
property* supplied by the manufacturer:

| coefficient | meaning |
|---|---|
| sigma_i | incipient cavitation, first detectable bubbles |
| sigma_c | constant cavitation, steady and audible |
| sigma_id | incipient cavitation damage, where metal loss starts |
| sigma_mr | manufacturer's recommended minimum |
| sigma_ch | choking cavitation, the point the library already detects |

**The important part: the library currently only detects the last one.** By
the time flow chokes, the valve has been through incipient cavitation,
constant cavitation and the onset of damage. A valve can report "not choked"
and be eroding its trim.

There is a second complication I did not know and would have got wrong. These
coefficients **are not constant with pressure or valve size.** RP75.23 names
the two effects explicitly: pressure scale effect and size scale effect. A
sigma measured on a DN50 valve at 5 bar does not transfer to a DN200 valve at
40 bar without correction.

**My recommendation: implement sigma, but only as a reported index, not as a
verdict.**

Computing `sigma = (p1 - pv) / (p1 - p2)` is arithmetic the library already
has the inputs for. Reporting it costs nothing and is genuinely useful,
because an engineer with a manufacturer's sigma curve can compare directly.

What I would **not** do is invent threshold values per valve style. That is
the valve style table mistake again, in a service where the failure is
eroded trim rather than a slightly wrong number. If you supply `sigma_mr`
from a data sheet, the library can compare and warn. If you do not, it
reports the index and says it has no threshold to judge it against.

---

## 3. Noise

**EN IEC 60534-8-3** covers aerodynamic noise prediction, and **60534-8-4**
hydrodynamic. I found the standards but not their content.

This is a substantial calculation, an octave-band sound power model, not a
single formula. It also needs valve-specific acoustic data.

**Recommendation: out of scope, and say so.** The library already carries the
rho v squared criterion, which is the crude proxy the industry uses for "this
will be noisy". That is honest. A full 8-3 implementation would be a project
of its own and I would not attempt it from secondary sources.

---

## 4. Valve geometries

The travel curve work today added nine geometries. What is still missing, in
order of how often you would meet it:

**Multistage and multipath trim.** Anti-cavitation and low-noise trims that
take the pressure drop in stages. EN IEC 60534-2-1:2011 Annex B covers these and it
is a genuinely different equation, not a coefficient adjustment. Worth doing
eventually because it is the standard answer to a cavitating or noisy
service, so the library currently detects a problem it cannot then help you
solve.

**Characterised trims.** Equal percentage against linear against quick
opening. This affects where in its travel the valve sits at a given duty,
which now matters because the coefficients follow the travel. The library
currently reports capacity fraction and is careful to call it capacity rather
than travel, which is correct but incomplete.

**Angle and Y-pattern bodies**, currently approximated with the eccentric
rotary plug curve, which is honest in the docstring but is a substitute.

---

## 5. Other flow criteria found while looking

**Reynolds factor FR**, EN IEC 60534-2-1:2011 Annex A. Still the largest genuine gap. Screened
and labelled, not corrected. Implicit, needs iteration.

**Pressure recovery and the vena contracta.** Already handled through FL.

**Erosional velocity**, API RP 14E. Implemented.

**Outlet velocity limits for gas**, rho v squared. Implemented, now reachable
from the gas path.

**Thermal binding and cryogenic seat effects.** Real, valve-specific, not a
sizing calculation. Out of scope.

---

## What I would build next, ranked

1. **Flashing detection.** Small, honest, closes the two-phase question by
   refusing rather than guessing. Forty lines.
2. **Sigma reported as an index**, with comparison only when you supply a
   threshold. Small, and it is the gap between "not choked" and "not
   damaging".
3. **FR**, the Reynolds correction. The largest gap, and the one that needs
   the most care because it iterates.
4. **Multistage trim**, Annex B. Larger, and the natural answer to a service
   the library already flags as a problem.

I would not build two-phase sizing or noise prediction. Both need data the
project does not have, and both would produce confident numbers in exactly
the services where a wrong number costs the most.

---

## One thing worth saying about method

Every item above came from checking a source rather than from what I already
believed. That is deliberate. In two days this project has had three numbers
wrong that I was confident about, and every one was caught by an outside
check rather than by reasoning harder.

The pattern is consistent enough to be a rule: **in this library, confidence
is not evidence.** Where I could not reach a primary source, I have said so
above rather than filling the gap.
