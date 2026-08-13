import re

from app.config import get_settings
from app.security.detect import contains_known_pii
from app.services.morpheus import morpheus_chat

SYSTEM_INSTRUCTION = (
    "You are FinBrain OS's reasoning assistant. Answer only from the supplied context. "
    "Never invent values. Placeholders matching TYPE_xxxxxxxxxx or AMOUNT_BAND_n represent "
    "hidden values. Copy every relevant token exactly; never guess or reformat it."
)

TOKEN_PATTERN = re.compile(r"(?:[A-Z]+_[0-9a-f]{10}|AMOUNT_BAND_\d+)")


def _offline_answer(question: str, chunks: list[str]) -> str:
    if not chunks:
        return "No matching records are available yet. Run the seed command first."
    return (
        "Offline demo mode is active. The most relevant protected records are:\n\n- "
        + "\n- ".join(chunks)
    )


def answer_query(question: str, chunks: list[str]) -> tuple[str, str]:
    context = "\n\n".join(chunks)
    if contains_known_pii(question) or contains_known_pii(context):
        raise ValueError("Refusing to send recognized PII to the reasoning service")
    settings = get_settings()
    if settings.morpheus_api_key:
        try:
            response = morpheus_chat(
                [
                    {"role": "system", "content": SYSTEM_INSTRUCTION},
                    {
                        "role": "user",
                        "content": f"Context:\n{context}\n\nQuestion: {question}",
                    },
                ]
            )
            return response, "morpheus"
        except Exception:
            if not settings.allow_offline_demo:
                raise
    if settings.gemini_api_key:
        try:
            from google import genai

            client = genai.Client(api_key=settings.gemini_api_key)
            response = client.models.generate_content(
                model=settings.gemini_reasoning_model,
                contents=f"Context:\n{context}\n\nQuestion: {question}",
                config={"system_instruction": SYSTEM_INSTRUCTION},
            )
            return response.text or "No answer was generated.", "gemini"
        except Exception:
            if not settings.allow_offline_demo:
                raise
    if not settings.allow_offline_demo:
        raise RuntimeError("A reasoning API key is required when offline demo mode is disabled")
    return _offline_answer(question, chunks), "offline-demo"


def unknown_tokens(text: str, known_tokens: set[str]) -> set[str]:
    output_tokens = {
        token for token in TOKEN_PATTERN.findall(text) if not token.startswith("AMOUNT_BAND_")
    }
    return output_tokens - known_tokens
