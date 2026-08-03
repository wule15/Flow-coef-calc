"""
Exceptions raised when an input cannot be honoured.

The rule this module exists to enforce: the library refuses rather than
guesses. A silently clamped input produces a number that looks like an
answer, and a valve sized from it is wrong in service with nothing in the
output to say so.

Choked flow is deliberately not in here. Choking is a physical operating
state, not a bad input, so it is reported on the result object and never
raised.
"""

from __future__ import annotations


class FlowCoefficientError(Exception):
    """Base for everything this library raises. Catch this to catch all."""


class UnknownUnitError(FlowCoefficientError):
    """A unit string the library does not recognise."""

    def __init__(self, unit: str, kind: str, known: tuple[str, ...]) -> None:
        self.unit = unit
        self.kind = kind
        self.known = known
        super().__init__(
            f"unknown {kind} unit {unit!r}. Known units: {', '.join(sorted(known))}"
        )


class OutOfRangeError(FlowCoefficientError):
    """
    A value outside the range where the library can answer honestly.

    Used for correlations fitted over a stated range. Extrapolating an
    Antoine vapour pressure beyond its fit produces a confident wrong number
    that feeds straight into a cavitation prediction, so the library stops
    instead.
    """

    def __init__(
        self,
        name: str,
        value: float,
        low: float,
        high: float,
        unit: str = '',
        context: str = '',
    ) -> None:
        self.name = name
        self.value = value
        self.low = low
        self.high = high
        suffix = f' {unit}' if unit else ''
        message = (
            f"{name} is {value}{suffix}, outside the valid range "
            f"{low} to {high}{suffix}"
        )
        if context:
            message += f". {context}"
        super().__init__(message)


class InvalidPressureError(FlowCoefficientError):
    """A pressure that cannot describe a real flow condition."""


class InvalidFlowRateError(FlowCoefficientError):
    """A flow rate that cannot describe a real flow condition."""


class InvalidFluidPropertyError(FlowCoefficientError):
    """A fluid property outside the range where the sizing equations hold."""


class UnknownFluidError(FlowCoefficientError):
    """A fluid name that is not in the table."""

    def __init__(self, name: str, known: tuple[str, ...]) -> None:
        self.name = name
        self.known = known
        super().__init__(
            f"unknown fluid {name!r}. Known fluids: {', '.join(sorted(known))}. "
            f"Pass the properties explicitly to size a fluid that is not listed."
        )
