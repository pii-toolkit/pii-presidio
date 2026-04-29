# Changelog

All notable changes to `pii-presidio` are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-04-29

Initial functional release. Microsoft Presidio plugin for `pii-core`
recognizers and `pii-veil` reversible anonymization.

### Added

- `get_recognizers(languages, *, include_opt_in)` -- factory returning
  Presidio `PatternRecognizer` instances for each detector in `pii-core`.
  Confidence is 0.85 for checksum-validated detectors and 0.4 for
  regex-only ones; per-detector context words are pre-set to common
  Polish keywords. KRS and postal-code recognizers are gated behind
  `include_opt_in=True` because their raw patterns collide with
  ordinary text.
- `PiiCoreRecognizer` -- the `PatternRecognizer` subclass that wires a
  `pii_core` detector's checksum hook through Presidio's
  `validate_result`.
- `ReversibleReplaceOperator` -- custom Presidio `Operator` that
  substitutes detected values with stable tokens via a
  `pii_veil.Mapping`. Mapping format is identical to standalone
  `pii-veil`, so anonymization performed through Presidio is fully
  reversible by `pii_veil.Shield.deanonymize`.
- `reversible_operators(mapping, *, entities=None)` -- helper that
  produces the per-entity `OperatorConfig` dict
  `AnonymizerEngine.anonymize(operators=...)` expects.
- `ENTITY_FOR_PII_TYPE` -- the canonical mapping from `pii_core.PIIType`
  to Presidio entity name strings. Polish-specific types keep their
  `PL_` prefix; cross-language types use Presidio's standard names
  (`EMAIL_ADDRESS`, `CREDIT_CARD`, `PHONE_NUMBER`, `IBAN_CODE`).
- Test suite covering recognizer construction, end-to-end
  Analyzer + Anonymizer round-trip via `pii_veil.Shield.deanonymize`,
  operator parameter validation, and the public-API guardrail.
