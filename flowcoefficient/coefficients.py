"""
Kv and Cv, the two conventions for flow coefficient.

Both describe the same physical property. They differ only in the units they
were defined in.

    Kv  flow of water in m3/h through the valve at a pressure drop of 1 bar,
        between 5 and 40 degrees C.
    Cv  flow of water in US gallons per minute at a pressure drop of 1 psi,
        at 60 degrees F.

The ratio is a unit conversion, not a fitted constant:

    Cv / Kv = (m3/h to US gpm) / sqrt(bar to psi)
            = 4.402868 / sqrt(14.503774)
            = 4.402868 / 3.808382
            = 1.15606

The square root appears because flow goes with the square root of pressure
drop, so the pressure unit conversion enters under the root.

The library works internally in Kv because it works in SI. Nothing outside
this module depends on that, because every result object carries both.
"""

from __future__ import annotations

# Published pair, used in manufacturer literature. Kept as two constants
# rather than deriving one from the other, so an engineer checking this
# against a datasheet finds the numbers they expect. The round trip is
# asserted in the tests.
CV_PER_KV = 1.156
KV_PER_CV = 0.865

# The unrounded ratio, from the unit definitions. Used by the test that
# proves the published pair is the conversion and not an arbitrary factor.
EXACT_CV_PER_KV = 4.402868 / 14.503774 ** 0.5


def kv_to_cv(kv: float) -> float:
    """
    Convert Kv to Cv.

    >>> round(kv_to_cv(17.68), 2)
    20.44
    """
    return kv * CV_PER_KV


def cv_to_kv(cv: float) -> float:
    """
    Convert Cv to Kv.

    >>> round(cv_to_kv(20.44), 2)
    17.68
    """
    return cv * KV_PER_CV
