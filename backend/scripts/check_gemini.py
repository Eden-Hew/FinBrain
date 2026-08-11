from app.config import get_settings


def main() -> None:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise SystemExit(
            "GEMINI_API_KEY is empty. Add the key to backend/.env, then rerun this command."
        )

    from google import genai

    client = genai.Client(api_key=settings.gemini_api_key)
    model = client.models.get(model=settings.gemini_reasoning_model)
    embedding = client.models.embed_content(
        model=settings.gemini_embedding_model,
        contents="FinBrain Gemini connectivity check",
        config={"output_dimensionality": 768},
    )
    response = client.models.generate_content(
        model=settings.gemini_reasoning_model,
        contents="Reply with exactly: FinBrain Gemini ready",
    )

    print(f"Reasoning model: {model.name}")
    print(f"Embedding model: {settings.gemini_embedding_model}")
    print(f"Embedding dimensions: {len(embedding.embeddings[0].values)}")
    print(f"Generation response: {response.text}")


if __name__ == "__main__":
    main()
