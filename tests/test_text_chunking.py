import re


def test_chunk_faq_single_chunk_stable_id():
    from src.common.text_chunking import chunk_faq

    faq = {"Hours": "We are open 8-20"}
    chunks1 = chunk_faq(faq, max_chars=10_000)
    chunks2 = chunk_faq(faq, max_chars=10_000)

    assert len(chunks1) == 1
    assert chunks1[0].text.startswith("Q: Hours")
    assert "A: We are open" in chunks1[0].text
    # deterministyczny ID (reindex nadpisuje wektory)
    assert chunks1[0].chunk_id == chunks2[0].chunk_id
    assert re.fullmatch(r"[0-9a-f]{40}", chunks1[0].chunk_id)


def test_chunk_faq_splits_long_text_into_multiple_chunks():
    from src.common.text_chunking import chunk_faq

    long_answer = " ".join(["lorem ipsum"] * 200)  # długi tekst
    faq = {"Long": long_answer}

    chunks = chunk_faq(faq, max_chars=200, overlap_chars=40)
    assert len(chunks) >= 2
    assert all(len(c.text) <= 200 for c in chunks)

    # wszystkie chunk-i mają to samo faq_key (po normalizacji)
    assert all(c.faq_key == "Long" for c in chunks)

    # stabilność: dwa kolejne wywołania dają te same chunk_id w tej samej kolejności
    chunks2 = chunk_faq(faq, max_chars=200, overlap_chars=40)
    assert [c.chunk_id for c in chunks] == [c.chunk_id for c in chunks2]
