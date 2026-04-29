"""Presidio PatternRecognizer wrappers around ``pii-core`` detectors.

Each ``pii_core`` detector class becomes a ``PatternRecognizer`` instance with
a confidence score, an entity name aligned with Presidio's conventions, and
the detector's checksum (when present) wired through ``validate_result``.

Entity name choices:

- Polish-specific identifiers keep the ``PL_`` prefix (``PL_PESEL``, ``PL_NIP``,
  ...). They have no Presidio-standard equivalent, and the prefix matches what
  Microsoft's own country recognizers do (``IT_FISCAL_CODE``, ``ES_NIE``).
- Cross-language entities use Presidio's well-known names (``EMAIL_ADDRESS``,
  ``CREDIT_CARD``) so existing pipelines that filter ``entities=[...]`` by
  those strings pick our recognizers up without changes.
- ``PL_IBAN`` and ``PL_PHONE`` map to Presidio's ``IBAN_CODE`` /
  ``PHONE_NUMBER`` for the same reason. The patterns are Polish-only, but the
  entity label is what matters for downstream filtering.

Confidence scale:

- 0.85 for detectors with checksum validation (PESEL, NIP, REGON, IBAN,
  credit card). A regex match plus a passing weighted-sum / mod-97 / Luhn check
  is high-confidence PII.
- 0.4 for regex-only detectors (ID card, passport, phone, email, KRS,
  postal code). The regex alone admits false positives -- context boost lifts
  these into actionable territory.

KRS and postal-code recognizers are excluded from the default factory output;
their raw regexes (``\\b\\d{10}\\b`` and ``\\b\\d{2}-\\d{3}\\b``) collide with
ordinary numeric text. ``include_opt_in=True`` enables them; pair with a
context-word filter to avoid noise.
"""

from __future__ import annotations

from collections.abc import Iterable

from pii_core import (
    CreditCardDetector,
    EmailDetector,
    PIIType,
    PlIbanDetector,
    PlIdCardDetector,
    PlKrsDetector,
    PlNipDetector,
    PlPassportDetector,
    PlPeselDetector,
    PlPhoneDetector,
    PlPostalCodeDetector,
    PlRegonDetector,
    RegexDetector,
)
from presidio_analyzer import Pattern, PatternRecognizer

ENTITY_FOR_PII_TYPE: dict[PIIType, str] = {
    PIIType.PL_PESEL: "PL_PESEL",
    PIIType.PL_NIP: "PL_NIP",
    PIIType.PL_REGON: "PL_REGON",
    PIIType.PL_ID_CARD: "PL_ID_CARD",
    PIIType.PL_PASSPORT: "PL_PASSPORT",
    PIIType.PL_KRS: "PL_KRS",
    PIIType.PL_POSTAL_CODE: "PL_POSTAL_CODE",
    PIIType.PL_PHONE: "PHONE_NUMBER",
    PIIType.PL_IBAN: "IBAN_CODE",
    PIIType.EMAIL: "EMAIL_ADDRESS",
    PIIType.CREDIT_CARD: "CREDIT_CARD",
}

_HIGH_CONFIDENCE = 0.85
_LOW_CONFIDENCE = 0.4

_CONTEXT_FOR_NAME: dict[str, list[str]] = {
    "pl_pesel": ["pesel"],
    "pl_nip": ["nip", "podatk", "podatkowy"],
    "pl_regon": ["regon"],
    "pl_id_card": ["dowód", "dowod", "osobisty"],
    "pl_passport": ["paszport", "passport"],
    "pl_iban": ["iban", "konto", "rachunek"],
    "pl_phone": ["telefon", "tel", "kom", "phone"],
    "pl_krs": ["krs"],
    "pl_postal_code": ["kod", "pocztowy"],
    "email": ["email", "e-mail", "mail"],
    "credit_card": ["card", "karta", "credit"],
}

# Detectors whose ``_is_valid`` hook performs a real checksum (vs. the no-op
# default). Presidio calls ``validate_result`` only when this is truthy; for
# regex-only detectors we leave it alone so Presidio doesn't waste a call.
_HAS_CHECKSUM: frozenset[str] = frozenset(
    {"pl_pesel", "pl_nip", "pl_regon", "pl_iban", "credit_card"}
)

_POLISH_DETECTORS: tuple[type[RegexDetector], ...] = (
    PlPeselDetector,
    PlNipDetector,
    PlRegonDetector,
    PlIdCardDetector,
    PlPassportDetector,
    PlIbanDetector,
    PlPhoneDetector,
)
_OPT_IN_POLISH_DETECTORS: tuple[type[RegexDetector], ...] = (
    PlKrsDetector,
    PlPostalCodeDetector,
)
_CROSS_DETECTORS: tuple[type[RegexDetector], ...] = (
    EmailDetector,
    CreditCardDetector,
)


class PiiCoreRecognizer(PatternRecognizer):
    """A Presidio ``PatternRecognizer`` driven by a ``pii_core`` detector.

    The detector instance is held privately so ``validate_result`` can call its
    checksum hook. Presidio invokes ``validate_result`` only on detectors that
    declared a real checksum (see ``_HAS_CHECKSUM``); regex-only detectors
    leave it as ``None`` and rely on Presidio's regex match alone, scaled by
    the configured score and any context boost.
    """

    def __init__(
        self,
        detector: RegexDetector,
        *,
        supported_language: str,
        score: float,
        context: list[str] | None = None,
    ) -> None:
        entity = ENTITY_FOR_PII_TYPE[detector.pii_type]
        super().__init__(
            supported_entity=entity,
            patterns=[
                Pattern(
                    name=detector.name,
                    regex=detector.pattern.pattern,
                    score=score,
                ),
            ],
            context=context if context is not None else _CONTEXT_FOR_NAME.get(detector.name, []),
            supported_language=supported_language,
        )
        self._detector = detector

    def validate_result(self, pattern_text: str) -> bool | None:
        # Calls the same checksum the detector applies in
        # ``RegexDetector.detect``; pii-core and pii-presidio are
        # version-pinned siblings, so reaching across the underscore here is
        # acceptable rather than duplicating each validator inline.
        if self._detector.name not in _HAS_CHECKSUM:
            return None
        return self._detector._is_valid(pattern_text)


def _build_for_detectors(
    detector_classes: Iterable[type[RegexDetector]],
    language: str,
) -> list[PatternRecognizer]:
    out: list[PatternRecognizer] = []
    for cls in detector_classes:
        det = cls()
        score = _HIGH_CONFIDENCE if det.name in _HAS_CHECKSUM else _LOW_CONFIDENCE
        out.append(PiiCoreRecognizer(det, supported_language=language, score=score))
    return out


def get_recognizers(
    languages: Iterable[str] = ("pl",),
    *,
    include_opt_in: bool = False,
) -> list[PatternRecognizer]:
    """Build PatternRecognizer instances for the requested languages.

    Args:
        languages: Language codes to register recognizers under. ``"pl"``
            yields the Polish identifier set (PESEL, NIP, REGON, ID card,
            passport, IBAN, phone) plus the cross-language detectors (email,
            credit card) tagged with ``supported_language="pl"``. Any other
            code yields the cross-language detectors only, tagged with that
            code -- useful for ``AnalyzerEngine(supported_languages=["en"])``
            pipelines that want our Luhn-validated card detector.
        include_opt_in: Add KRS and postal-code recognizers (Polish only).
            Excluded by default because their raw regexes match ordinary
            10-digit and ``XX-XXX`` strings; pair them with a context-word
            filter elsewhere in your pipeline.

    Returns:
        Concrete ``PatternRecognizer`` instances ready to register via
        ``AnalyzerEngine.registry.add_recognizer(...)``.
    """
    out: list[PatternRecognizer] = []
    for lang in languages:
        if lang == "pl":
            out.extend(_build_for_detectors(_POLISH_DETECTORS, lang))
            if include_opt_in:
                out.extend(_build_for_detectors(_OPT_IN_POLISH_DETECTORS, lang))
        out.extend(_build_for_detectors(_CROSS_DETECTORS, lang))
    return out


__all__ = [
    "ENTITY_FOR_PII_TYPE",
    "PiiCoreRecognizer",
    "get_recognizers",
]
