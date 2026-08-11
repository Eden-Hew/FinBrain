import os

os.environ.setdefault("ENABLE_GLINER", "false")
os.environ.setdefault("ALLOW_OFFLINE_DEMO", "true")
os.environ.setdefault("TOKEN_ROOT_SECRET", "test-secret-that-is-longer-than-32-characters")
os.environ["GEMINI_API_KEY"] = ""
