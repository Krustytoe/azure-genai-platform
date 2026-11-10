from ragapi.chunking import chunk_corpus, chunk_markdown

from .conftest import CORPUS


def test_paragraphs_carry_their_heading(tmp_path) -> None:
    doc = tmp_path / "policy.md"
    doc.write_text("# Title\n\nIntro.\n\n## Meals\n\nPer diem is $75.\n\nNo alcohol.\n")
    chunks = chunk_markdown(doc)
    assert [c.text for c in chunks] == [
        "Title: Intro.",
        "Meals: Per diem is $75.",
        "Meals: No alcohol.",
    ]
    assert [c.index for c in chunks] == [0, 1, 2]
    assert {c.source for c in chunks} == {"policy.md"}


def test_long_paragraphs_split_on_sentences(tmp_path) -> None:
    doc = tmp_path / "long.md"
    doc.write_text(" ".join(f"Sentence number {i} is here." for i in range(40)))
    chunks = chunk_markdown(doc, max_chars=200)
    assert len(chunks) > 1
    assert all(len(c.text) <= 200 for c in chunks)
    assert all(c.text.endswith(".") for c in chunks)


def test_sample_corpus_chunks() -> None:
    chunks = chunk_corpus(CORPUS)
    assert len({c.source for c in chunks}) == 5
    assert any("$75 per day" in c.text for c in chunks)
