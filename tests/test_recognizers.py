"""Tests for the recognizer factory and PiiCoreRecognizer wrapper."""

from __future__ import annotations

import pytest
from pii_core import PIIType, PlPeselDetector
from presidio_analyzer import PatternRecognizer

from pii_presidio.recognizers import (
    ENTITY_FOR_PII_TYPE,
    PiiCoreRecognizer,
    get_recognizers,
)


class TestGetRecognizers:
    def test_polish_default_returns_full_set(self) -> None:
        recs = get_recognizers(["pl"])
        # 7 Polish detectors (PESEL, NIP, REGON, ID card, passport, IBAN,
        # phone) + 2 cross-language (email, credit card) = 9.
        assert len(recs) == 9

    def test_all_recognizers_are_pattern_recognizers(self) -> None:
        for r in get_recognizers(["pl"]):
            assert isinstance(r, PatternRecognizer)

    def test_polish_recognizers_tagged_with_pl_language(self) -> None:
        for r in get_recognizers(["pl"]):
            assert r.supported_language == "pl"

    def test_include_opt_in_adds_krs_and_postal_code(self) -> None:
        without = get_recognizers(["pl"])
        with_opt = get_recognizers(["pl"], include_opt_in=True)
        # KRS + postal code = 2 extra recognizers.
        assert len(with_opt) == len(without) + 2
        added_entities = {r.supported_entities[0] for r in with_opt} - {
            r.supported_entities[0] for r in without
        }
        assert added_entities == {"PL_KRS", "PL_POSTAL_CODE"}

    def test_non_polish_language_returns_cross_only(self) -> None:
        recs = get_recognizers(["en"])
        # Only the 2 cross-language detectors should be returned.
        entities = sorted(r.supported_entities[0] for r in recs)
        assert entities == ["CREDIT_CARD", "EMAIL_ADDRESS"]
        for r in recs:
            assert r.supported_language == "en"

    def test_multi_language_emits_cross_per_language(self) -> None:
        recs = get_recognizers(["pl", "en"])
        # Polish: 7 detectors + 2 cross. English: 2 cross. Total 11.
        assert len(recs) == 11
        en_recs = [r for r in recs if r.supported_language == "en"]
        assert sorted(r.supported_entities[0] for r in en_recs) == [
            "CREDIT_CARD",
            "EMAIL_ADDRESS",
        ]

    def test_empty_languages_yields_empty_list(self) -> None:
        assert get_recognizers([]) == []

    def test_entity_names_aligned_with_presidio_conventions(self) -> None:
        recs = {r.supported_entities[0] for r in get_recognizers(["pl"])}
        # Presidio's well-known names used for cross-language types.
        assert "EMAIL_ADDRESS" in recs
        assert "CREDIT_CARD" in recs
        assert "PHONE_NUMBER" in recs
        assert "IBAN_CODE" in recs
        # Polish-specific keep PL_ prefix.
        assert "PL_PESEL" in recs
        assert "PL_NIP" in recs


class TestEntityMapping:
    def test_every_default_pii_type_has_entity(self) -> None:
        # All non-NLP PIIType values used by pii-core detectors must be mapped.
        required = {
            PIIType.PL_PESEL,
            PIIType.PL_NIP,
            PIIType.PL_REGON,
            PIIType.PL_ID_CARD,
            PIIType.PL_PASSPORT,
            PIIType.PL_KRS,
            PIIType.PL_POSTAL_CODE,
            PIIType.PL_PHONE,
            PIIType.PL_IBAN,
            PIIType.EMAIL,
            PIIType.CREDIT_CARD,
        }
        assert required.issubset(ENTITY_FOR_PII_TYPE.keys())


class TestValidateResult:
    def test_checksum_detector_validates_through_pii_core(self) -> None:
        rec = PiiCoreRecognizer(
            PlPeselDetector(),
            supported_language="pl",
            score=0.85,
        )
        # 44051401359 is a valid PESEL (used as test fixture across the toolkit).
        assert rec.validate_result("44051401359") is True
        # Same digits with last digit perturbed should fail the weighted checksum.
        assert rec.validate_result("44051401358") is False

    def test_regex_only_detector_returns_none(self) -> None:
        from pii_core import PlIdCardDetector

        rec = PiiCoreRecognizer(
            PlIdCardDetector(),
            supported_language="pl",
            score=0.4,
        )
        # PL_ID_CARD has no checksum hook; validate_result returns None so
        # Presidio relies on the regex score alone.
        assert rec.validate_result("ABC123456") is None

    def test_custom_context_overrides_default(self) -> None:
        rec = PiiCoreRecognizer(
            PlPeselDetector(),
            supported_language="pl",
            score=0.85,
            context=["myword"],
        )
        assert rec.context == ["myword"]


class TestRecognizerScores:
    @pytest.mark.parametrize(
        "entity,expected_score",
        [
            ("PL_PESEL", 0.85),  # checksum
            ("PL_NIP", 0.85),  # checksum
            ("PL_REGON", 0.85),  # checksum
            ("IBAN_CODE", 0.85),  # checksum
            ("CREDIT_CARD", 0.85),  # Luhn checksum
            ("PL_ID_CARD", 0.4),  # regex only
            ("PL_PASSPORT", 0.4),  # regex only
            ("PHONE_NUMBER", 0.4),  # regex only
            ("EMAIL_ADDRESS", 0.4),  # regex only
        ],
    )
    def test_score_matches_confidence_tier(self, entity: str, expected_score: float) -> None:
        rec = next(r for r in get_recognizers(["pl"]) if r.supported_entities[0] == entity)
        assert rec.patterns[0].score == expected_score
