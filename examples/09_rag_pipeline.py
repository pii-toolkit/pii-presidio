"""RAG pipeline with redaction at three points: ingest, prompt, answer.

The flow:

1. Documents are tokenized before they enter the vector store, so the index
   itself never sees real PII.
2. Retrieval works on tokenized text -- token shapes are deterministic, so
   the same value yields the same token across documents.
3. The prompt sent to the LLM contains only tokens. The LLM's answer is
   tokenized too; we deanonymize only that final answer for the end user.

This is the pattern Elastic, LlamaIndex, and Private AI describe for RAG over
private corpora. Reversibility matters because the citation/quoted snippets
shown to the authorized end-user must contain real names, but the LLM call
must not.

Run:

    python examples/09_rag_pipeline.py
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from pii_veil import Mapping, Shield
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine

from pii_presidio import (
    ReversibleReplaceOperator,
    get_recognizers,
    reversible_operators,
)

# Tiny in-memory "vector store". Real deployments use Chroma / Qdrant /
# pgvector / Elastic; the redaction contract is identical -- tokens go into
# the index, tokens come back out.

_WORD = re.compile(r"\w+", re.UNICODE)


@dataclass
class IndexedDoc:
    doc_id: str
    tokenized_text: str
    bag: Counter[str]


def _bag_of_words(text: str) -> Counter[str]:
    return Counter(w.lower() for w in _WORD.findall(text))


def _cosine(a: Counter[str], b: Counter[str]) -> float:
    common = set(a) & set(b)
    if not common:
        return 0.0
    dot = sum(a[w] * b[w] for w in common)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    return dot / (norm_a * norm_b)


def retrieve(query: str, index: list[IndexedDoc], k: int = 2) -> list[IndexedDoc]:
    q_bag = _bag_of_words(query)
    scored = [(d, _cosine(q_bag, d.bag)) for d in index]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [d for d, _ in scored[:k]]


CORPUS = [
    (
        "ticket-001",
        "Klient Jan Kowalski (PESEL 44051401359) zgłasza problem z przelewem "
        "na konto PL61109010140000071219812874.",
    ),
    ("ticket-002", "Anna Nowak (email anna@example.pl) prosi o zmianę adresu rozliczeniowego."),
    ("ticket-003", "Faktura dla firmy NIP 526-000-12-46: nieopłacona od 30 dni."),
    (
        "ticket-004",
        "Jan Kowalski ponownie kontaktuje się; chce potwierdzenia, "
        "że PESEL 44051401359 został zaktualizowany.",
    ),
]


def fake_llm(prompt: str) -> str:
    """Pretend the LLM produced a grounded answer that quotes tokens."""
    if "PESEL" in prompt and "[PL_PESEL_001]" in prompt:
        return (
            "Klient o numerze [PL_PESEL_001] zgłaszał dwa zgłoszenia "
            "(ticket-001 oraz ticket-004). Konto powiązane: [PL_IBAN_001]."
        )
    return "Brak danych w kontekście."


def build_pipeline() -> tuple[AnalyzerEngine, AnonymizerEngine]:
    nlp_engine = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "pl", "model_name": "pl_core_news_sm"}],
        }
    ).create_engine()
    registry = RecognizerRegistry(supported_languages=["pl"])
    for r in get_recognizers(["pl"]):
        registry.add_recognizer(r)
    analyzer = AnalyzerEngine(registry=registry, nlp_engine=nlp_engine, supported_languages=["pl"])
    anonymizer = AnonymizerEngine()
    anonymizer.add_anonymizer(ReversibleReplaceOperator)
    return analyzer, anonymizer


def main() -> None:
    analyzer, anonymizer = build_pipeline()
    mapping = Mapping()  # one mapping for the whole corpus -> stable tokens.

    print("=== Stage 1: ingest. Tokenize before indexing. ===")
    index: list[IndexedDoc] = []
    for doc_id, text in CORPUS:
        results = analyzer.analyze(text=text, language="pl")
        anon_text = anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators=reversible_operators(mapping),
        ).text
        index.append(IndexedDoc(doc_id, anon_text, _bag_of_words(anon_text)))
        print(f"  {doc_id}: {anon_text}")

    print("\n=== Stage 2: query. Retrieval works on tokens. ===")
    user_query = "Jakie zgłoszenia złożył klient z PESEL 44051401359?"
    # Tokenize the query with the same Mapping so the PESEL in the question
    # turns into the same token that's in the index.
    q_results = analyzer.analyze(text=user_query, language="pl")
    anon_query = anonymizer.anonymize(
        text=user_query,
        analyzer_results=q_results,
        operators=reversible_operators(mapping),
    ).text
    print(f"  Query (tokenized): {anon_query}")

    hits = retrieve(anon_query, index, k=2)
    print(f"  Top {len(hits)} hits:")
    for h in hits:
        print(f"    {h.doc_id}: {h.tokenized_text[:80]}...")

    print("\n=== Stage 3: prompt the LLM with tokens only. ===")
    context = "\n".join(f"- {h.tokenized_text}" for h in hits)
    prompt = f"Pytanie: {anon_query}\n\nKontekst:\n{context}\n\nOdpowiedź:"
    print("  Prompt (truncated):")
    for line in prompt.splitlines():
        print(f"    {line}")

    llm_answer = fake_llm(prompt)
    print(f"\n  LLM answer (still tokenized): {llm_answer}")

    print("\n=== Stage 4: deanonymize the final answer for the end user. ===")
    final = Shield(mapping=mapping).deanonymize(llm_answer)
    print(f"  {final}")


if __name__ == "__main__":
    main()
