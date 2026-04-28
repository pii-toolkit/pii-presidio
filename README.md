# pii-presidio

Microsoft Presidio plugin: multi-language PII recognizers with optional reversible anonymization, built on top of `pii-detect`.

> **Pre-release placeholder.** No implementation has shipped yet. The `0.0.0` release on PyPI exists only to reserve the package name. Watch this space for the first functional release.

## Planned scope

- `get_recognizers(languages=["pl", ...])` — `PatternRecognizer` instances ready to register with `AnalyzerEngine`.
- Confidence scale 0.4 / 0.85 / +context boost, mirroring Presidio's built-in behavior.
- Optional `ReversibleReplaceOperator` for `AnonymizerEngine` — when enabled, replacement emits a mapping you can use to deanonymize later.
- Pluggable mapping store (in-memory by default; file or callback on opt-in).

## Sibling packages

- [`pii-detect`](https://github.com/pii-toolkit/pii-detect) — multi-language detection primitives this plugin reuses.
- [`pii-cloak`](https://github.com/pii-toolkit/pii-cloak) — non-Presidio reversible anonymization with the same mapping format.

## License

Apache-2.0. See `LICENSE`.
