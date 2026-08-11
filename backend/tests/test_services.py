from app.services.embeddings import embed_text
from app.services.reasoning import answer_query, unknown_tokens


def test_offline_embedding_is_deterministic():
    first, mode = embed_text("protected customer record")
    second, _ = embed_text("protected customer record")
    assert mode == "offline-demo"
    assert first == second
    assert len(first) == 128


def test_offline_reasoning_preserves_tokens():
    answer, mode = answer_query("Who needs attention?", ["PHONE_aabbccddee owes AMOUNT_BAND_2"])
    assert mode == "offline-demo"
    assert "PHONE_aabbccddee" in answer
    assert "AMOUNT_BAND_2" in answer


def test_unknown_token_detection():
    assert unknown_tokens("Contact PHONE_aabbccddee", {"PHONE_0011223344"}) == {"PHONE_aabbccddee"}
