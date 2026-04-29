"""Custom Presidio Operator that allocates reversible tokens via ``pii_veil.Mapping``.

Plug it into ``AnonymizerEngine.anonymize(...)`` so each detected value gets
replaced with a stable ``[<TYPE>_<NNN>]`` token. The same Mapping can later be
handed to ``pii_veil.Deanonymizer`` (or ``Shield.deanonymize``) to round-trip
the substitution -- the token format is identical, by design.

Why not just use Presidio's built-in ``replace`` operator? Because it can't
guarantee that the same value gets the same token across calls, and it has no
way to expose the substitution back to the caller. ``Mapping`` solves both:
``token_for(value, type)`` is idempotent, and the caller already holds the
Mapping handle.
"""

from __future__ import annotations

from typing import Any

from pii_core import PIIType
from pii_veil import Mapping
from presidio_anonymizer.entities import OperatorConfig
from presidio_anonymizer.operators import Operator, OperatorType

from pii_presidio.recognizers import ENTITY_FOR_PII_TYPE

OPERATOR_NAME = "reversible"

# Inverse of ENTITY_FOR_PII_TYPE -- two pii_core types map to the same
# Presidio entity (PL_PHONE -> PHONE_NUMBER, PL_IBAN -> IBAN_CODE), but the
# inverse direction is unique because the operator only sees Presidio's
# entity name; we always pick the country-specific PIIType for those, since
# our recognizers are the only ones emitting them with this entity label.
_PII_TYPE_FOR_ENTITY: dict[str, PIIType] = {
    entity: pii_type for pii_type, entity in ENTITY_FOR_PII_TYPE.items()
}


class ReversibleReplaceOperator(Operator):
    """Replaces a detected value with a Mapping-allocated token.

    Required ``params``:

    - ``mapping``: a ``pii_veil.Mapping`` instance. Mutated in place; hold a
      reference to deanonymize the result later.
    - ``entity_type``: the Presidio entity string (e.g. ``"PL_PESEL"``).
      Baked into the params dict by :func:`reversible_operators`; pass it
      manually only if you build the OperatorConfig yourself.

    The operator is stateless -- all per-call state lives in the Mapping --
    so a single registration handles every entity type your pipeline emits.
    """

    def operate(self, text: str, params: dict[str, Any] | None = None) -> str:
        params = params or {}
        mapping = params.get("mapping")
        entity_type = params.get("entity_type")
        if not isinstance(mapping, Mapping):
            raise ValueError(
                "ReversibleReplaceOperator requires 'mapping' param of type pii_veil.Mapping"
            )
        if not isinstance(entity_type, str):
            raise ValueError(
                "ReversibleReplaceOperator requires 'entity_type' param (Presidio entity name)"
            )
        pii_type = _PII_TYPE_FOR_ENTITY.get(entity_type)
        if pii_type is None:
            raise ValueError(
                f"ReversibleReplaceOperator does not handle entity_type {entity_type!r}; "
                f"supported: {sorted(_PII_TYPE_FOR_ENTITY)}"
            )
        return mapping.token_for(text, pii_type)

    def validate(self, params: dict[str, Any] | None = None) -> None:
        params = params or {}
        if not isinstance(params.get("mapping"), Mapping):
            raise ValueError("'mapping' must be a pii_veil.Mapping instance")
        entity_type = params.get("entity_type")
        if not isinstance(entity_type, str):
            raise ValueError("'entity_type' must be a Presidio entity name string")
        if entity_type not in _PII_TYPE_FOR_ENTITY:
            raise ValueError(
                f"unsupported entity_type {entity_type!r}; "
                f"supported: {sorted(_PII_TYPE_FOR_ENTITY)}"
            )

    def operator_name(self) -> str:
        return OPERATOR_NAME

    def operator_type(self) -> OperatorType:
        return OperatorType.Anonymize


def reversible_operators(
    mapping: Mapping,
    *,
    entities: list[str] | None = None,
) -> dict[str, OperatorConfig]:
    """Build the per-entity ``OperatorConfig`` dict for ``AnonymizerEngine.anonymize``.

    Args:
        mapping: The ``pii_veil.Mapping`` that will accumulate tokens. The same
            Mapping is referenced by every config so a single
            ``anonymize(...)`` call produces a coherent reversible result.
        entities: Optional whitelist of Presidio entity names to include. By
            default, every entity in :data:`ENTITY_FOR_PII_TYPE` is wired up.
            Useful when your pipeline mixes our recognizers with Presidio
            built-ins and you want only ours to use the reversible operator.

    Returns:
        A dict suitable for ``AnonymizerEngine.anonymize(operators=...)``.
    """
    selected = entities if entities is not None else list(_PII_TYPE_FOR_ENTITY)
    out: dict[str, OperatorConfig] = {}
    for entity in selected:
        if entity not in _PII_TYPE_FOR_ENTITY:
            raise ValueError(
                f"unsupported entity {entity!r}; supported: {sorted(_PII_TYPE_FOR_ENTITY)}"
            )
        out[entity] = OperatorConfig(
            OPERATOR_NAME,
            {"mapping": mapping, "entity_type": entity},
        )
    return out


__all__ = [
    "OPERATOR_NAME",
    "ReversibleReplaceOperator",
    "reversible_operators",
]
