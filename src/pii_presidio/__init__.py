"""pii-presidio: Microsoft Presidio plugin for the pii-toolkit.

Wraps ``pii-core`` detectors as Presidio ``PatternRecognizer`` instances and
adds a ``ReversibleReplaceOperator`` that substitutes detected values with
stable tokens from a ``pii_veil.Mapping``. The same mapping format is used by
the standalone ``pii-veil`` package, so anonymization performed via Presidio
can be deanonymized by ``pii_veil.Shield`` (and vice versa).

Public API:

- :func:`get_recognizers` -- factory for ``PatternRecognizer`` instances.
- :class:`ReversibleReplaceOperator` -- custom Presidio operator that allocates
  reversible tokens via :class:`pii_veil.Mapping`.
- :func:`reversible_operators` -- helper that builds the per-entity
  ``OperatorConfig`` dict ``AnonymizerEngine.anonymize`` expects.
- :data:`ENTITY_FOR_PII_TYPE` -- mapping from ``pii_core.PIIType`` to the
  Presidio entity strings emitted by our recognizers.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

from pii_presidio.operator import (
    OPERATOR_NAME,
    ReversibleReplaceOperator,
    reversible_operators,
)
from pii_presidio.recognizers import (
    ENTITY_FOR_PII_TYPE,
    PiiCoreRecognizer,
    get_recognizers,
)

try:
    __version__ = _version("pii-presidio")
except PackageNotFoundError:
    __version__ = "0.0.0+local"

__all__ = [
    "ENTITY_FOR_PII_TYPE",
    "OPERATOR_NAME",
    "PiiCoreRecognizer",
    "ReversibleReplaceOperator",
    "__version__",
    "get_recognizers",
    "reversible_operators",
]
