# FR (Reynolds number factor) implementation proposal

Status: IMPLEMENTED on the liquid path (flowcoefficient/reynolds_factor.py),
2026-08-10, after physics sign-off. The FR equation is pinned to the standard's
FR = 0.715 worked example, and the Kv constants N18 = 0.865 and N32 = 140 are
cross-checked against the Cv-basis figures by the unit conversion (linear for
N18, the 2/3 power for N32). The GAS path is now ALSO implemented (2026-08-11): the
Eq. A.4 volumetric non-turbulent equation with N22 = 1.73e3 (verified against the
primary IEC:2011 and ISA:2002 Table 1, and cross-checked as unit-consistent with
the verified turbulent N7), and the Eq. A.5 expansion factor with the laminar
term (1 - x)/2 read directly off the rendered standard. The physics record below
is retained as the derivation.

Source: EN IEC 60534-2-1:2011 (Edition 2), Annex A (normative), "Sizing
equations for non-turbulent flow", Equations A.1 to A.8. This is the current
edition and the one to cite. There is no later revision.

The FR method was ALSO read from ANSI/ISA-75.01.01-2002 (based on IEC's 1998
first edition), where it sits in clause 8.2 and Annex G. Edition 2 restructured
the presentation (one intermediate variable n instead of n1/n2, an explicit Min
function, and a new non-turbulent gas expansion factor), but the FR equations
themselves are MATHEMATICALLY IDENTICAL between the two editions. This was
confirmed by rendering and reading both. So the hand-check below still holds.

All equations below were read from RENDERED pages of both editions (page
images, not the flattened text layer), so superscripts, fraction bars and
radicals are as printed. Cross-checked against the 1998-edition worked example,
where FR = 0.715 reproduces by hand.

---

## 1. What it is and when it fires

The turbulent sizing equations assume Rev >= 10,000. Below that the flow is
transitional or laminar and the valve passes less than the turbulent equation
predicts. The required coefficient becomes C_turbulent / FR, with FR <= 1. The
library already computes Rev (regime.py, Eq. 28) and already flags the duty as
transitional or laminar. This proposal adds the correction FR and applies it.

Applies when Rev < 10,000. Needs kinematic viscosity and FL, exactly the inputs
the screening already needs, so the trigger conditions do not change.

## 2. The valve Reynolds number (already in the library)

Eq. 28, unchanged, already in regime.py:

    Rev = (N4 * Fd * Q) / (nu * sqrt(Ci * FL)) * ( (FL^2 * Ci^2)/(N2 * d^4) + 1 )^(1/4)

N4 = 7.07e4 (Kv, m3/h, cSt, mm), N2 = 1.60e-3 (Kv, mm). Both present and
fact-checked. Fd is the valve style modifier, already held per style in
valves.py.

## 3. The split: full-size vs reduced trim

The 2011 edition classifies trim by the RATED coefficient, not the operating
one (Annex A, A.8a/A.8b), which matters: it is a fixed property of the valve,
so the branch cannot flip mid-iteration. d in mm, Crated as Kv:

    Crated / (d^2 * N18) >= 0.016   ->  full-size trim   (Eq. A.8a)
    Crated / (d^2 * N18) <  0.016   ->  reduced trim     (Eq. A.8b)

N18 = 8.65e-1 = 0.865 for Kv (Table 1, read off the rendered page). The 1998
worked example's N18 = 1.00 is the Cv value, not the Kv value; this is a
Kv-vs-Cv column swap of exactly the kind that produced the old N9 error, caught
only by reading the actual table. Restriction A.4(3) gives the validity cap:
C / (N18 * d^2) <= 0.047, which for Kv (N18 = 0.865) is C/d^2 <= 0.04.

## 4. The FR equations (EN IEC 60534-2-1:2011, Annex A), in Kv units

n depends on trim style. C here is the coefficient being solved for:

    full-size trim:  n = N2 / (C/d^2)^2                        (Eq. A.8a)
    reduced trim:    n = 1 + N32 * (C/d^2)^(2/3)               (Eq. A.8b)

LAMINAR, Rev < 10 (Eq. A.6):

    FR = Min[ (0.026 / FL) * sqrt(n * Rev) ,  1.00 ]

TRANSITIONAL, Rev >= 10 (Eq. A.7):

    FR = Min[ 1 + ( 0.33 * sqrt(FL) / n^(1/4) ) * log10(Rev/10000) ,
              (0.026 / FL) * sqrt(n * Rev) ,
              1.00 ]

This is the same math as the 1998 Annex G (G.1a/G.2 for full trim, G.3a/G.4 for
reduced), reorganised into a single n and an explicit Min. The FR = 0.715
worked-example check was done against that identical form.

Two new constants, both read off the rendered Table 1:
- N32 = 1.40e2 = 140 for Kv (Cv column is 127, which reproduces the worked
  example's n = 1.235).
- N18 = 8.65e-1 = 0.865 for Kv, used only in the trim-classification boundary.
  The 1.00 in the worked example is the Cv value. Getting this wrong is the
  Kv-vs-Cv column swap that produced the old N9 error.

## 4a. Gas non-turbulent flow needs its own Y (new in 2011)

The 2011 edition adds an expansion factor for non-turbulent compressible flow
(Annex A, Eq. A.5) that the 1998 edition did not have. It blends toward the
turbulent Y as Rev rises:

    Rev >= 1000:  Y = (Rev - 1000)/9000 * ( (1 - x_sizing/(3*x_choked)) - (1 - x)/2 )
                      + (1 - x)/2
    Rev <  1000:  Y = (1 - x)/2

    CORRECTED 2026-08-11: the laminar term is (1 - x)/2, read directly off the
    rendered Eq. A.5 (p.20 of EN IEC 60534-2-1:2011). This proposal originally
    transcribed it as sqrt(1 - x/2), which was wrong and would have oversized the
    valve differently by up to a factor of two. Now implemented as (1 - x)/2.

The gas non-turbulent model is W = C*N27*FR*Y*sqrt(dp*(p1+p2)*M/T1) (Eq. A.3),
or the Qs form with N22 (Eq. A.4). Implement the liquid FR path first, then the
gas path with this Y. N22 and N27 need adding, verified against Table 1.

## 5. The iteration

FR depends on Rev, Rev depends on the coefficient, so it iterates. The standard
(clause 8.2, Eq. 29) does it in coarse manual steps: start Ci = C_turbulent,
compute FR, test C_turbulent/FR <= Ci; if not, raise Ci by 30 percent and
repeat.

PROPOSED INSTEAD: a fixed-point iteration to a tolerance,
Ci_next = C_turbulent / FR(Ci), converged when it moves less than 1e-4
relative. This lands on the exact coefficient the 30 percent staircase brackets
from above, is not conservative-by-rounding, and matches how the library
already iterates the operating point. It reports pass count and whether it
converged, same as the existing loops.

DECISION (made): fixed-point to tolerance, matching the existing operating-point
loop. The standard's literal 30-percent-step method was the alternative.

## 6. Acceptance test, from the standard

The 1998-edition worked example (segmented ball, Cv basis) gives a check I will
encode:

    FL = 0.98, C/d^2 small (reduced trim), Rev = 1202, n = 1.235
    transitional (A.7 / old G.3a) -> FR = 0.715
    laminar      (A.6 / old G.4)  -> FR = 1.022, capped to 1
    Min -> FR = 0.715

I reproduced 0.715 by hand. The Kv version of this case becomes a unit test, so
the implementation is pinned to the standard's own number, not to itself. This
is the outside-source check this codebase has learned to require.

## 7. Where it plugs in

liquid.py already has the turbulent coefficient, FL, Fd, rated_kv and d, and
already calls screen(). FR slots in right after the coefficient settles: screen,
and if correction_needed, run the FR iteration and divide (Eq. A.2). The result
object gains an FR field and its provenance string. The gas path (main-body
clause 7.6, Annex A) uses the same FR plus the non-turbulent Y of Eq. A.5. Do
liquid first, then gas in the same shape.

## 8. Weakest parts of this plan

1. Annex A is NORMATIVE in the 2011 edition (it was informative Annex G in
   1998), but it still states the equations are fitted at rated travel and
   "may not be fully accurate at lower valve travels". The library reads FL and
   Fd off the travel curve at the operating point, so at low opening the FR it
   computes inherits that stated inaccuracy. It should say so rather than imply
   the curve equation is exact everywhere.

2. Fd drives Rev and the library carries one Fd per style, catalogue-derived,
   not per-valve tested. IEC requires a type test for 5 percent accuracy on Fd.
   A wrong Fd moves Rev and therefore FR. This is the same single-manufacturer
   caveat the travel curves already carry, and the FR result should repeat it.

3. RESOLVED by moving to the 2011 edition. The full-vs-reduced split is
   classified on Crated (the rated coefficient, fixed), not on the iterating C,
   so the branch cannot oscillate. The 0.04 cap is a validity check, not a
   branch. Convergence of the fixed-point loop still gets swept, as the
   operating-point loop was.

## Sources

- EN IEC 60534-2-1:2011 (Edition 2), Annex A (normative), Eq. A.1 (Rev),
  A.2-A.4 (non-turbulent models), A.5 (non-turbulent gas Y), A.6/A.7 (FR),
  A.8a/A.8b (n by trim). Read from rendered pages.
- ANSI/ISA-75.01.01-2002 (IEC 60534-2-1 Mod, 1998 basis), clause 8.2 and
  Annex G, read from rendered pages as a cross-check. FR equations identical.
- Table 1 for N2, N4, N18, N32 (and N22, N27 for the gas path), read from the
  rendered table. Worked example (segmented ball) giving FR = 0.715.
