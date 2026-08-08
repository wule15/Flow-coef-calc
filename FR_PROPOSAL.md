# FR (Reynolds number factor) implementation proposal

Status: PROPOSAL. Nothing here is implemented. Verify the physics before I write code.

Source: ANSI/ISA-75.01.01-2002 (IEC 60534-2-1 Mod), clause 8.2 and Annex G.
Cross-checked against the standard's own worked example (clause example, valve
sized in Cv), where I reproduced FR = 0.715 by hand from Eq. G.3a.

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

Decided by Ci/d^2 at the operating point (d in mm, Ci as Kv):

    Ci/d^2 >= 0.016   ->  full-size trim   (Eq. G.1a / G.2)
    Ci/d^2 <  0.016   ->  reduced trim     (Eq. G.3a / G.4)

The 0.016 is 0.016 * N18 with N18 = 1.00 for Kv (Table 1, confirmed in the
worked example). NOTE 3 of Annex G: Ci/d^2 must not exceed 0.04 for Kv; past
that the FR curves are not valid.

## 4. The FR equations (Annex G), in Kv units

FULL-SIZE TRIM, Rev >= 10:

    n1 = N2 / (Ci/d^2)^2                                       (Eq. G.1b)

    transitional (G.1a):  FR = 1 + ( 0.33 * sqrt(FL) / n1^(1/4) ) * log10(Rev/10000)
    laminar      (G.2):   FR = (0.026 / FL) * sqrt(n1 * Rev)          capped at 1

    Use the LOWER of the two. If Rev < 10, use G.2 only.

REDUCED TRIM, Rev >= 10:

    n2 = 1 + N32 * (Ci/d^2)^(2/3)                              (Eq. G.3b)

    transitional (G.3a):  FR = 1 + ( 0.33 * sqrt(FL) / n2^(1/4) ) * log10(Rev/10000)
    laminar      (G.4):   FR = (0.026 / FL) * sqrt(n2 * Rev)          capped at 1

    Use the LOWER of the two. If Rev < 10, use G.4 only.

The one new constant: N32 = 1.40e2 = 140 for Kv (Table 1). The worked example
uses the Cv value 127; I confirmed 127 reproduces its n2 = 1.235, and 140 is
the Kv column of the same row. N18 = 1.00 also new but only as the 0.016 and
0.04 thresholds.

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

DECISION FOR YOU: fixed-point to tolerance (my recommendation, more accurate),
or the standard's literal 30-percent-step method (conservative, matches a hand
calculation exactly). I will implement whichever you want and cite it.

## 6. Acceptance test, from the standard

The worked example (segmented ball, Cv basis) gives a check I will encode:

    FL = 0.98, Ci/d^2 small (reduced trim), Rev = 1202, n2 = 1.235
    G.3a -> FR = 0.715
    G.4  -> FR = 1.022 (capped to 1)
    use FR = 0.715

I reproduced 0.715 by hand. The Kv version of this case becomes a unit test, so
the implementation is pinned to the standard's own number, not to itself. This
is the outside-source check this codebase has learned to require.

## 7. Where it plugs in

liquid.py already has the turbulent coefficient, FL, Fd, rated_kv and d, and
already calls screen(). FR slots in right after the coefficient settles: screen,
and if correction_needed, run the FR iteration and divide. The result object
gains an FR field and its provenance string. Gas (clause 7.2) uses the same FR
from Annex G; I propose liquid first, then gas in the same shape.

## 8. Three weakest parts of this plan

1. Annex G is informative, not normative, and its NOTE 2 says the equations are
   fitted at rated travel and "may not be fully accurate at lower valve
   travels". The library reads FL and Fd off the travel curve at the operating
   point, so at low opening the FR it computes inherits that stated inaccuracy.
   It should say so rather than imply the curve equation is exact everywhere.

2. Fd drives Rev and the library carries one Fd per style, catalogue-derived,
   not per-valve tested. IEC requires a type test for 5 percent accuracy on Fd.
   A wrong Fd moves Rev and therefore FR. This is the same single-manufacturer
   caveat the travel curves already carry, and the FR result should repeat it.

3. The full-vs-reduced split and the 0.04 cap are evaluated on Ci, which moves
   during the iteration. A duty that crosses the 0.016 boundary between passes
   could oscillate between the G.1 and G.3 branches. I need to prove the
   iteration is stable across that boundary, or fix the branch on the first
   pass and note it. Convergence must be swept, as it was for the operating
   point.

## Sources

- ANSI/ISA-75.01.01-2002 (IEC 60534-2-1 Mod), clause 8.2 (Eq. 28, 29),
  Annex G (Eq. G.1a, G.1b, G.2, G.3a, G.3b, G.4), Table 1 (N2, N4, N18, N32),
  Table 2 and Annex A (Fd).
- Worked example in the standard, segmented ball valve, giving FR = 0.715.
