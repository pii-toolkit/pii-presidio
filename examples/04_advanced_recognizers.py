"""Advanced recognizer setup: opt-in detectors, custom context, mixing with Presidio built-ins.

Demonstrates three knobs:

1. ``include_opt_in=True`` -- enables KRS and postal-code recognizers (excluded
   by default because their raw regexes match ordinary numeric text).
2. Custom context words -- override the default Polish context for a recognizer
   so tokens get a confidence boost only when surrounded by your own
   domain-specific keywords.
3. Mixing our recognizers with Presidio's built-in ones -- for example,
   keeping Presidio's English-trained ``EmailRecognizer`` while still using
   our Polish PESEL/NIP detectors.

Run:

    python examples/04_advanced_recognizers.py
"""

from __future__ import annotations

from pii_core import PlPeselDetector
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider

from pii_presidio import PiiCoreRecognizer, get_recognizers


def example_opt_in_detectors() -> None:
    print("--- Opt-in: KRS + postal code ---")
    base = get_recognizers(["pl"])
    extended = get_recognizers(["pl"], include_opt_in=True)
    base_entities = {r.supported_entities[0] for r in base}
    extra = {r.supported_entities[0] for r in extended} - base_entities
    print(f"  default recognizers: {len(base)}")
    print(f"  with include_opt_in: {len(extended)}  (added: {sorted(extra)})")


def example_custom_context() -> None:
    print("\n--- Custom context words ---")
    # Replace the default ['pesel'] context with your own keywords -- handy
    # when the documents you analyse use jargon ('numer ewidencyjny', etc.).
    pesel_recognizer = PiiCoreRecognizer(
        PlPeselDetector(),
        supported_language="pl",
        score=0.85,
        context=["numer", "ewidencyjny", "pesel"],
    )
    print(f"  context: {pesel_recognizer.context}")


def example_mixed_with_presidio_builtins() -> None:
    print("\n--- Mix our recognizers with Presidio's built-in EmailRecognizer ---")
    nlp_engine = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "pl", "model_name": "pl_core_news_sm"}],
        }
    ).create_engine()

    # Take only the Polish-specific recognizers from us; let Presidio handle
    # email via its bundled recognizer.
    registry = RecognizerRegistry(supported_languages=["pl"])
    registry.load_predefined_recognizers(languages=["pl"])  # adds Presidio's defaults

    for recognizer in get_recognizers(["pl"]):
        # Skip our email + credit_card -- we only want Polish IDs from us.
        if recognizer.supported_entities[0] in {"EMAIL_ADDRESS", "CREDIT_CARD"}:
            continue
        registry.add_recognizer(recognizer)

    analyzer = AnalyzerEngine(
        registry=registry,
        nlp_engine=nlp_engine,
        supported_languages=["pl"],
    )
    text = "PESEL 44051401359, kontakt: jan@example.pl"
    results = analyzer.analyze(text=text, language="pl")
    print(f"  detected from {text!r}:")
    for r in sorted(results, key=lambda x: x.start):
        print(f"    {r.entity_type:15s} score={r.score:.2f}  {text[r.start : r.end]!r}")


def main() -> None:
    example_opt_in_detectors()
    example_custom_context()
    example_mixed_with_presidio_builtins()


if __name__ == "__main__":
    main()
