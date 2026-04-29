"""Tests for ReversibleReplaceOperator and reversible_operators helper."""

from __future__ import annotations

import pytest
from pii_veil import Mapping, Shield
from presidio_anonymizer.entities import OperatorConfig
from presidio_anonymizer.operators import OperatorType

from pii_presidio.operator import (
    OPERATOR_NAME,
    ReversibleReplaceOperator,
    reversible_operators,
)


class TestOperatorMetadata:
    def test_operator_name(self) -> None:
        assert ReversibleReplaceOperator().operator_name() == OPERATOR_NAME
        assert OPERATOR_NAME == "reversible"

    def test_operator_type_is_anonymize(self) -> None:
        assert ReversibleReplaceOperator().operator_type() is OperatorType.Anonymize


class TestOperate:
    def test_returns_token_for_known_entity(self) -> None:
        mapping = Mapping()
        result = ReversibleReplaceOperator().operate(
            "44051401359",
            {"mapping": mapping, "entity_type": "PL_PESEL"},
        )
        assert result == "[PL_PESEL_001]"
        assert len(mapping) == 1

    def test_same_value_yields_same_token(self) -> None:
        mapping = Mapping()
        op = ReversibleReplaceOperator()
        first = op.operate("jan@x.pl", {"mapping": mapping, "entity_type": "EMAIL_ADDRESS"})
        second = op.operate("jan@x.pl", {"mapping": mapping, "entity_type": "EMAIL_ADDRESS"})
        assert first == second
        assert len(mapping) == 1

    def test_different_values_get_different_tokens(self) -> None:
        mapping = Mapping()
        op = ReversibleReplaceOperator()
        a = op.operate("a@x.pl", {"mapping": mapping, "entity_type": "EMAIL_ADDRESS"})
        b = op.operate("b@x.pl", {"mapping": mapping, "entity_type": "EMAIL_ADDRESS"})
        assert a != b
        assert len(mapping) == 2

    def test_email_entity_uses_email_pii_type(self) -> None:
        mapping = Mapping()
        token = ReversibleReplaceOperator().operate(
            "jan@x.pl", {"mapping": mapping, "entity_type": "EMAIL_ADDRESS"}
        )
        assert token == "[EMAIL_001]"

    def test_phone_entity_resolves_to_pl_phone(self) -> None:
        mapping = Mapping()
        token = ReversibleReplaceOperator().operate(
            "+48 600 123 456", {"mapping": mapping, "entity_type": "PHONE_NUMBER"}
        )
        # PHONE_NUMBER -> PL_PHONE inverse mapping; check token prefix.
        assert token == "[PL_PHONE_001]"

    def test_iban_entity_resolves_to_pl_iban(self) -> None:
        mapping = Mapping()
        token = ReversibleReplaceOperator().operate(
            "PL61109010140000071219812874",
            {"mapping": mapping, "entity_type": "IBAN_CODE"},
        )
        assert token == "[PL_IBAN_001]"


class TestOperateValidation:
    def test_missing_mapping_raises(self) -> None:
        with pytest.raises(ValueError, match="mapping"):
            ReversibleReplaceOperator().operate("x", {"entity_type": "PL_PESEL"})

    def test_non_mapping_object_raises(self) -> None:
        with pytest.raises(ValueError, match="mapping"):
            ReversibleReplaceOperator().operate(
                "x", {"mapping": "not a mapping", "entity_type": "PL_PESEL"}
            )

    def test_missing_entity_type_raises(self) -> None:
        with pytest.raises(ValueError, match="entity_type"):
            ReversibleReplaceOperator().operate("x", {"mapping": Mapping()})

    def test_unsupported_entity_type_raises(self) -> None:
        with pytest.raises(ValueError, match="does not handle entity_type"):
            ReversibleReplaceOperator().operate(
                "x", {"mapping": Mapping(), "entity_type": "US_SSN"}
            )

    def test_none_params_treated_as_empty(self) -> None:
        with pytest.raises(ValueError):
            ReversibleReplaceOperator().operate("x", None)


class TestValidate:
    def test_passes_for_well_formed_params(self) -> None:
        # Should not raise.
        ReversibleReplaceOperator().validate({"mapping": Mapping(), "entity_type": "PL_PESEL"})

    def test_rejects_missing_mapping(self) -> None:
        with pytest.raises(ValueError, match="mapping"):
            ReversibleReplaceOperator().validate({"entity_type": "PL_PESEL"})

    def test_rejects_missing_entity_type(self) -> None:
        with pytest.raises(ValueError, match="entity_type"):
            ReversibleReplaceOperator().validate({"mapping": Mapping()})

    def test_rejects_unsupported_entity_type(self) -> None:
        with pytest.raises(ValueError, match="unsupported"):
            ReversibleReplaceOperator().validate({"mapping": Mapping(), "entity_type": "US_SSN"})

    def test_handles_none_params(self) -> None:
        with pytest.raises(ValueError):
            ReversibleReplaceOperator().validate(None)


class TestReversibleOperatorsHelper:
    def test_returns_config_for_every_supported_entity(self) -> None:
        mapping = Mapping()
        configs = reversible_operators(mapping)
        # 11 entities total in ENTITY_FOR_PII_TYPE.
        assert len(configs) == 11
        for entity, config in configs.items():
            assert isinstance(config, OperatorConfig)
            assert config.params["entity_type"] == entity
            assert config.params["mapping"] is mapping

    def test_entity_whitelist_filters_output(self) -> None:
        mapping = Mapping()
        configs = reversible_operators(mapping, entities=["PL_PESEL", "EMAIL_ADDRESS"])
        assert set(configs) == {"PL_PESEL", "EMAIL_ADDRESS"}

    def test_unknown_entity_in_whitelist_raises(self) -> None:
        with pytest.raises(ValueError, match="unsupported entity"):
            reversible_operators(Mapping(), entities=["US_SSN"])

    def test_all_configs_share_same_mapping(self) -> None:
        mapping = Mapping()
        configs = reversible_operators(mapping)
        mappings = {id(c.params["mapping"]) for c in configs.values()}
        assert mappings == {id(mapping)}


class TestRoundTripViaShield:
    """The operator's output must be deanonymizable by pii_veil.Shield."""

    def test_token_round_trips(self) -> None:
        mapping = Mapping()
        op = ReversibleReplaceOperator()
        token = op.operate("44051401359", {"mapping": mapping, "entity_type": "PL_PESEL"})
        # Use Shield to confirm the cross-package contract.
        restored = Shield(mapping=mapping).deanonymize(f"PESEL: {token}.")
        assert restored == "PESEL: 44051401359."
