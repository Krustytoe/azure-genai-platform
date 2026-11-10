"""Offline provider: lexical retrieval over local Markdown and an extractive "model".

Used for local development, unit tests and the CI eval run. It exercises every
part of the pipeline (redaction, score gating, citations, metrics) without
cloud credentials. It says nothing about model quality; point the eval suite
at a real deployment for that.
"""

import re
from pathlib import Path

from ..chunking import chunk_corpus
from .base import Completion, Passage

_WORD = re.compile(r"[a-z0-9$]+(?:[.'][a-z0-9]+)*")
_STOPWORDS = """
a an and are as at be by can do does for from how i if in is it many may me much my of on or
our should the to us we what when where which who why will with you your
"""
_STOP = frozenset(_STOPWORDS.split())
_SOURCE = re.compile(r'<source id="(\d+)"[^>]*>\n(.*?)\n</source>', re.DOTALL)


def _stem(word: str) -> str:
    # Crude plural folding so "passwords" matches "password". Real deployments use embeddings.
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def _terms(text: str) -> set[str]:
    return {_stem(w) for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 1}


class FakeRetriever:
    def __init__(self, corpus_dir: Path) -> None:
        self._chunks = [(c.text, c.source, _terms(c.text)) for c in chunk_corpus(corpus_dir)]
        if not self._chunks:
            raise ValueError(f"no Markdown content found in {corpus_dir}")

    def retrieve(self, query: str, top_k: int) -> list[Passage]:
        q = _terms(query)
        if not q:
            return []
        scored = [
            Passage(text=text, source=source, score=len(q & terms) / len(q))
            for text, source, terms in self._chunks
        ]
        scored.sort(key=lambda p: p.score, reverse=True)
        return [p for p in scored[:top_k] if p.score > 0]


class FakeChatModel:
    system = "fake"
    model_id = "fake-extractive"

    def generate(
        self,
        *,
        system_prompt: str,
        context: str,
        question: str,
        max_tokens: int,
        temperature: float,
    ) -> Completion:
        sources = _SOURCE.findall(context)
        if sources:
            # Extractive answer: the sentence of the top source that best matches the question.
            source_id, body = sources[0]
            sentences = re.split(r"(?<=[.!?])\s+", body.split(": ", 1)[-1])
            q = _terms(question)
            best = max(sentences, key=lambda sent: len(q & _terms(sent)))
            text = f"{best} [{source_id}]"
        else:
            text = "No sources."
        prompt_words = len((system_prompt + context + question).split())
        return Completion(
            text=text,
            input_tokens=int(prompt_words * 1.3),
            output_tokens=int(len(text.split()) * 1.3),
        )
