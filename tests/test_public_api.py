"""Guardrail tests for the locked public API surface."""

import pii_presidio


def test_public_api_exports_are_importable() -> None:
    from pii_presidio import (
        ENTITY_FOR_PII_TYPE,
        OPERATOR_NAME,
        PiiCoreRecognizer,
        ReversibleReplaceOperator,
        get_recognizers,
        reversible_operators,
    )

    assert ENTITY_FOR_PII_TYPE is not None
    assert OPERATOR_NAME == "reversible"
    assert PiiCoreRecognizer is not None
    assert ReversibleReplaceOperator is not None
    assert get_recognizers is not None
    assert reversible_operators is not None


def test_all_matches_expected_surface() -> None:
    assert set(pii_presidio.__all__) == {
        "ENTITY_FOR_PII_TYPE",
        "OPERATOR_NAME",
        "PiiCoreRecognizer",
        "ReversibleReplaceOperator",
        "__version__",
        "get_recognizers",
        "reversible_operators",
    }


def test_version_is_defined() -> None:
    assert isinstance(pii_presidio.__version__, str)
    assert pii_presidio.__version__
