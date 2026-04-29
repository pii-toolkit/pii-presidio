"""Build script for demo.ipynb. Run once; executes the notebook to populate outputs.

Generates a single curated notebook at the package root that walks through
the headline use cases. Output cells are committed so GitHub renders the
demo without anyone having to install anything.

Usage:
    python scripts/build_demo.py

Requires the dev tooling in addition to the runtime deps:
    pip install jupyter nbformat nbconvert ipykernel
    python -m spacy download pl_core_news_sm
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf
from nbconvert.preprocessors import ExecutePreprocessor

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "demo.ipynb"


def md(text: str) -> nbf.notebooknode.NotebookNode:
    return nbf.v4.new_markdown_cell(text)


def code(text: str) -> nbf.notebooknode.NotebookNode:
    return nbf.v4.new_code_cell(text)


CELLS = [
    md(
        """\
# pii-presidio — reversible PII anonymization for LLM workflows

Microsoft Presidio plugin in the `pii-toolkit` family. Detect Polish identifiers
(PESEL, NIP, REGON, ID card, passport, IBAN) with checksum validation, plus
cross-language email and credit card. The headline feature: a
`ReversibleReplaceOperator` that swaps detected values for stable
`[PL_PESEL_001]`-style tokens via a `pii_veil.Mapping`, so anonymize → LLM →
deanonymize round trips work across processes.

This notebook walks through:

1. A 30-second round trip via `pii-veil` only (no Presidio).
2. A realistic Polish KYC document with checksum acceptance/rejection.
3. RAG pipeline with redaction at three points (ingest, prompt, answer).
4. GDPR Art. 15 DSAR with selective reversibility.

For more, see [`examples/`](examples) — 13 runnable scripts covering CLI, batch,
audit-only, multilingual, agent tool calls, DataFrames, and more.
"""
    ),
    md(
        """\
## Setup

In Colab the cell below installs the package and the Polish spaCy model.
Locally, when `pii-presidio` is already installed, it no-ops.
"""
    ),
    code(
        """\
import sys
import warnings

warnings.filterwarnings("ignore")

IN_COLAB = "google.colab" in sys.modules
if IN_COLAB:
    !pip install -q pii-presidio pandas
    !python -m spacy download pl_core_news_sm
"""
    ),
    md(
        """\
## 1. 30-second round trip with `pii-veil`

`pii-veil` is the language-neutral core: regex + checksum detection plus the
reversible `Mapping`. No Presidio, no spaCy — just import `Shield`, anonymize,
deanonymize.
"""
    ),
    code(
        """\
from pii_veil import Shield

shield = Shield()
text = "Mój PESEL: 44051401359, kontakt: jan@example.pl, telefon +48 600 123 456."

result = shield.anonymize(text)
print("Anonymized:", result.text)

restored = shield.deanonymize(result.text)
print("Restored:  ", restored)
"""
    ),
    md(
        """\
## 2. Polish KYC document — checksum validation in action

The Polish UODO (data protection authority) has ruled that a hashed PESEL is
*not* anonymous: the search space (~10¹¹ with structural constraints) is
brute-forceable. Reversible tokenization with an out-of-band Mapping is the
regulator-defensible posture.

The document below contains a deliberately bad-checksum PESEL
(`44051401358`, last digit perturbed). The toolkit's checksum validators
reject it via Presidio's `validate_result` hook so it doesn't appear in the
detection report.
"""
    ),
    code(
        """\
from pii_veil import Mapping, Shield
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine

from pii_presidio import (
    ReversibleReplaceOperator,
    get_recognizers,
    reversible_operators,
)


def build_pipeline():
    nlp_engine = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "pl", "model_name": "pl_core_news_sm"}],
        }
    ).create_engine()
    registry = RecognizerRegistry(supported_languages=["pl"])
    for r in get_recognizers(["pl"], include_opt_in=True):
        registry.add_recognizer(r)
    analyzer = AnalyzerEngine(
        registry=registry, nlp_engine=nlp_engine, supported_languages=["pl"]
    )
    anonymizer = AnonymizerEngine()
    anonymizer.add_anonymizer(ReversibleReplaceOperator)
    return analyzer, anonymizer


analyzer, anonymizer = build_pipeline()
print("Pipeline ready.")
"""
    ),
    code(
        """\
KYC = '''KARTA KLIENTA -- ONBOARDING

Klient indywidualny:
  Imię i nazwisko: Anna Maria Nowak
  PESEL: 02070803628
  Numer dowodu osobistego: ABC123456
  Adres email: anna.nowak@example.pl
  Telefon: +48 600 123 456

Powiązany podmiot gospodarczy:
  Nazwa: Nowak Consulting Sp. z o.o.
  NIP: 526-000-12-46
  REGON: 123456785
  KRS: 0000123456
  Konto rozliczeniowe: PL61109010140000071219812874

Uwagi compliance:
  Numer 44051401358 podany przez klienta jako alternatywny PESEL nie został
  potwierdzony (suma kontrolna nieprawidłowa).'''

results = analyzer.analyze(text=KYC, language="pl")

print("Detection report:")
for r in sorted(results, key=lambda x: x.start):
    print(f"  {r.entity_type:18s} score={r.score:.2f}  {KYC[r.start:r.end]!r}")

# Confirm the bad-checksum PESEL was rejected.
bad = [r for r in results if KYC[r.start:r.end] == "44051401358" and r.entity_type == "PL_PESEL"]
assert not bad, "checksum-bad PESEL was incorrectly accepted"
print("\\n  ✓ '44051401358' rejected (PESEL checksum failed)")
"""
    ),
    code(
        """\
mapping = Mapping()
anon = anonymizer.anonymize(
    text=KYC,
    analyzer_results=results,
    operators=reversible_operators(mapping),
).text

print("Anonymized KYC:")
print(anon)
print(f"\\nMapping: {len(mapping)} entries")

restored = Shield(mapping=mapping).deanonymize(anon)
assert restored == KYC
print("Round trip succeeded.")
"""
    ),
    md(
        """\
## 3. RAG pipeline — redaction at three points

The pattern Elastic, LlamaIndex, and Private AI describe for RAG over
private corpora:

1. **Ingest:** documents tokenized before they enter the vector store.
2. **Prompt:** the LLM sees only tokens.
3. **Answer:** deanonymize the model's output for the authorized end user.

The same `Mapping` is shared across all three points, so the same value
yields the same token everywhere — retrieval and prompting work as if no
anonymization had happened.
"""
    ),
    code(
        """\
import math
import re
from collections import Counter

WORD = re.compile(r"\\w+", re.UNICODE)

def bag(text):
    return Counter(w.lower() for w in WORD.findall(text))

def cosine(a, b):
    common = set(a) & set(b)
    if not common:
        return 0.0
    dot = sum(a[w] * b[w] for w in common)
    return dot / (math.sqrt(sum(v*v for v in a.values())) * math.sqrt(sum(v*v for v in b.values())))


CORPUS = [
    ("ticket-001", "Klient Jan Kowalski (PESEL 44051401359) zgłasza problem z przelewem."),
    ("ticket-002", "Anna Nowak prosi o zmianę adresu rozliczeniowego."),
    ("ticket-003", "Faktura dla NIP 526-000-12-46: nieopłacona od 30 dni."),
    ("ticket-004", "Jan Kowalski potwierdza, że PESEL 44051401359 został zaktualizowany."),
]

mapping = Mapping()
index = []
print("Stage 1 — ingest (tokens go into the index, not real PII):")
for doc_id, text in CORPUS:
    r = analyzer.analyze(text=text, language="pl")
    anon = anonymizer.anonymize(
        text=text, analyzer_results=r, operators=reversible_operators(mapping)
    ).text
    index.append((doc_id, anon, bag(anon)))
    print(f"  {doc_id}: {anon}")
"""
    ),
    code(
        """\
question = "Jakie zgłoszenia złożył klient z PESEL 44051401359?"
qr = analyzer.analyze(text=question, language="pl")
anon_q = anonymizer.anonymize(
    text=question, analyzer_results=qr, operators=reversible_operators(mapping)
).text

print(f"Stage 2 — query (tokenized): {anon_q}")

scores = [(d, cosine(bag(anon_q), b)) for d, _, b in index]
top = sorted([(d, s) for d, s in scores if s > 0], key=lambda x: -x[1])[:2]
print(f"Top hits: {[d for d, _ in top]}")

# Stand-in for the LLM. It echoes tokens it saw in the prompt.
context = "\\n".join(t for did, t, _ in index if did in {d for d, _ in top})
fake_answer = "Klient o numerze [PL_PESEL_001] zgłosił dwa zgłoszenia (ticket-001, ticket-004)."
print(f"\\nStage 3 — LLM answer (tokenized): {fake_answer}")

final = Shield(mapping=mapping).deanonymize(fake_answer)
print(f"Stage 4 — restored for end user:   {final}")
"""
    ),
    md(
        """\
## 4. DSAR with selective reversibility

GDPR Art. 15: subject A asks for "all data we hold about me." The corpus
mentions other people too — third parties cc'd, support agents, other
customers. Their PII must be redacted from what's delivered to A, but A's
own PII stays visible (it's their data).

Strategy: pre-allocate tokens for known third-party names (regex won't catch
personal names without NER), run Presidio anonymization, then reverse the
subset of tokens that belong to the requesting subject.
"""
    ),
    code(
        """\
from pii_core import PIIType


def deliver_to_subject(text, subject_values, third_party_names, analyzer, anonymizer):
    third_party_mapping = Mapping()

    # Step 1: tokenize known names via straight string substitution.
    working = text
    for name in third_party_names:
        if name in working:
            token = third_party_mapping.token_for(name, PIIType.PERSON)
            working = working.replace(name, token)

    # Step 2: Presidio handles regex-detectable PII.
    r = analyzer.analyze(text=working, language="pl")
    anon = anonymizer.anonymize(
        text=working, analyzer_results=r, operators=reversible_operators(third_party_mapping)
    ).text

    # Step 3: reverse the subject's own values back to originals.
    subject_pairs = {(t, v) for v, t in subject_values.items()}
    for entry in third_party_mapping.to_dict()["entries"]:
        if (PIIType(entry["type"]), entry["value"]) in subject_pairs:
            anon = anon.replace(entry["token"], entry["value"])
    return anon


SUBJECT = {
    "Anna Nowak": PIIType.PERSON,
    "anna.nowak@example.pl": PIIType.EMAIL,
    "02070803628": PIIType.PL_PESEL,
}
THIRD_PARTIES = ["Bartosz Wiśniewski"]

corpus = [
    "Klient: Anna Nowak (PESEL 02070803628). Email: anna.nowak@example.pl.",
    "Anna Nowak złożyła reklamację. Sprawę przejął Bartosz Wiśniewski "
    "(bartosz@example.com), który skontaktował się z PESEL 44051401359.",
    "Faktura wystawiona dla anna.nowak@example.pl, NIP 5260001246, "
    "kopia do bartosz@example.com.",
]

print("Internal review (nothing redacted):")
for line in corpus:
    print(f"  {line}")

print("\\nExternal delivery for Anna Nowak (her PII visible, third parties tokenized):")
for line in corpus:
    print(f"  {deliver_to_subject(line, SUBJECT, THIRD_PARTIES, analyzer, anonymizer)}")
"""
    ),
    md(
        """\
## What's next

- More patterns in [`examples/`](examples) — CLI usage, batch processing,
  audit-only mode, multilingual pipeline, agent tool-call sanitization,
  DataFrame round-trip, custom recognizers.
- The non-Presidio standalone is [`pii-veil`](https://github.com/pii-toolkit/pii-veil)
  — same `Mapping` format, includes a CLI.
- Detection primitives live in
  [`pii-core`](https://github.com/pii-toolkit/pii-core) with zero runtime
  dependencies.

License: Apache-2.0.
"""
    ),
]


def main() -> None:
    nb = nbf.v4.new_notebook()
    nb.metadata = {
        "kernelspec": {"name": "python3", "display_name": "Python 3"},
        "language_info": {"name": "python"},
    }
    nb.cells = CELLS

    print(f"Executing {len(CELLS)} cells...")
    ep = ExecutePreprocessor(timeout=600, kernel_name="python3")
    ep.preprocess(nb, {"metadata": {"path": str(ROOT)}})

    nbf.write(nb, str(OUTPUT))
    print(f"Wrote {OUTPUT}")

    # Run ruff format so the committed notebook is byte-identical to what CI
    # expects. Avoids a no-op formatting commit on every rebuild.
    import subprocess
    import sys

    subprocess.run(
        [sys.executable, "-m", "ruff", "format", str(OUTPUT)],
        cwd=str(ROOT),
        check=True,
    )


if __name__ == "__main__":
    main()
