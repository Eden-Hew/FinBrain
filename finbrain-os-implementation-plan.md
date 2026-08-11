# FinBrain OS — Implementation Plan

## 0. Goal

FinBrain OS is a customer-intelligence and process-optimization platform for
Malaysian MSMEs (RM1M–25M turnover) whose data — WhatsApp chats, bank CSVs,
email, meeting notes — is scattered across systems with no single source of
truth and no access control. The platform pulls that data into one place,
lets staff ask questions in plain language, and guarantees that answers
respect who is allowed to see what.

The differentiator is architectural, not procedural: sensitive values (NRIC,
phone numbers, bank details, exact amounts) are detected and replaced with
tokens **before** any text reaches an external LLM. The LLM reasons entirely
over tokens. Real values live only in an encrypted vault and are substituted
back into an answer **after** generation, gated by the requesting user's
role, with every substitution logged in a tamper-evident audit trail. PDPA
and MyInvois compliance become a property the system enforces, not a policy
document staff are trusted to follow.

This document is self-contained: it does not assume familiarity with any
prior discussion, and states every assumption it makes explicitly.

---

## 1. Scope of this build phase

This plan builds a working end-to-end slice, deliberately narrowed so the
core architecture (tokenize → store → retrieve → reason → detokenize →
audit) can be demonstrated without building live integrations first.

**Built now:**
- Full tokenization pipeline (regex + GLiNER) running on seeded sample data
- SQLite-backed storage, with schema designed to move to Postgres/Supabase
  with minimal code change
- Gemini-based retrieval-augmented answering over tokenized content
- Role-gated detokenization with a hash-chained audit log
- A minimal React frontend: role switcher, chat, audit log viewer

**Explicitly stubbed / deferred (see §17):**
- Live WhatsApp Business API and bank feed connectors — ingestion uses a
  seed script with realistic sample records instead
- Real authentication — role is chosen via a UI dropdown, not a logged-in
  session (documented swap-in point for Supabase Auth in §16)
- Supabase itself — SQLite is the database for this phase; §16 gives the
  exact migration steps and the SQL/policies needed to move over

**Assumptions made explicit:**
- Frontend: React + TypeScript + Vite + Tailwind (not specified in the
  brief, chosen for speed and Supabase's first-party JS client support)
- Backend: Python + FastAPI — required because GLiNER is a Python library;
  there is no equivalent for it in Node/Deno
- LLM reasoning: `gemini-3.6-flash` via the Gemini API
- Embeddings: `gemini-embedding-001` via the Gemini API
- Local vector search: brute-force cosine similarity in Python (SQLite has
  no native vector index); replaced with pgvector on Supabase

---

## 2. Quick start

```bash
# backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in GEMINI_API_KEY and TOKEN_ROOT_SECRET
python -m seed.seed_data    # loads sample records through the real pipeline
uvicorn app.main:app --reload --port 8000

# frontend (separate terminal)
cd frontend
npm install
npm run dev
```

---

## 3. Repository structure

```
finbrain-os/
  backend/
    app/
      main.py
      config.py
      db.py
      models.py
      schemas.py
      security/
        detect.py         # regex + GLiNER entity detection
        tokenize.py        # spans -> tokens, amount banding
        crypto.py          # AES-256-GCM, HKDF key derivation
        detokenize.py       # role check, decrypt, mask
      services/
        embeddings.py
        retrieval.py
        reasoning.py       # Gemini call
        audit.py           # hash-chained log
      routes/
        query.py
        audit_log.py
    seed/
      sample_records.py    # realistic mock inbound data
      seed_data.py          # runs records through the real pipeline
    requirements.txt
    .env.example
  frontend/
    src/
      api/client.ts
      components/
        ChatWindow.tsx
        RoleSelector.tsx
        AuditLogTable.tsx
      App.tsx
      main.tsx
    package.json
  infra/
    supabase/
      schema.sql
      rls_policies.sql
      edge-functions/
        detokenize/index.ts
```

---

## 4. Data model (SQLite now, Postgres-ready)

SQLAlchemy is used specifically so the switch to Postgres/Supabase later is
a connection-string change, not a rewrite — the same models work against
both dialects with two exceptions noted in §16 (the embedding column and
the retrieval query).

```python
# backend/app/models.py
from sqlalchemy import Column, String, Integer, Text, Boolean, LargeBinary, DateTime
from sqlalchemy.orm import declarative_base
import datetime

Base = declarative_base()

class TokenizedContent(Base):
    """Sanitized text only. Nothing in this table is ever raw."""
    __tablename__ = "tokenized_content"
    id = Column(Integer, primary_key=True)
    source_record_id = Column(String, nullable=False)
    content_text = Column(Text, nullable=False)     # tokens in place of sensitive spans
    embedding = Column(Text, nullable=False)          # JSON float list (SQLite); vector(768) on Postgres
    record_type = Column(String, nullable=True)
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class TokenVaultEntry(Base):
    """The only table holding real sensitive values, and only in encrypted form."""
    __tablename__ = "token_vault"
    token = Column(String, primary_key=True)
    entity_type = Column(String, nullable=False)
    encrypted_value = Column(LargeBinary, nullable=False)
    nonce = Column(LargeBinary, nullable=False)
    allowed_roles = Column(Text, nullable=False)       # JSON list (SQLite); text[] on Postgres
    sensitivity = Column(String, default="high")
    source_record_id = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class AuditLogEntry(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    prev_hash = Column(String, nullable=False)
    event_hash = Column(String, nullable=False)
    user_role = Column(String, nullable=False)
    token = Column(String, nullable=False)
    authorized = Column(Boolean, nullable=False)
    query_hash = Column(String, nullable=False)
    ts = Column(DateTime, default=datetime.datetime.utcnow)
```

```python
# backend/app/db.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./finbrain.db")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

Design decision worth stating outright: there is **no table for raw inbound
text**. Raw text exists only in memory for the duration of the detection
pass (§6) and is discarded once tokenized. This is deliberate — it means
even a full database dump never contains an unmasked record.

---

## 5. Seeded ingestion data

No live connectors yet. `sample_records.py` provides realistic mock
records — the shape WhatsApp Business API and bank feed exports would
actually produce — so the rest of the pipeline can be exercised end to end.

```python
# backend/seed/sample_records.py
SAMPLE_RECORDS = [
    {
        "source_type": "whatsapp",
        "text": "Hi, this is Ahmad Faizal. Calling about invoice INV-2024-0912, "
                "still owe RM4,850. My IC is 901231-14-5566, reach me at "
                "012-345 6789. Can pay by Friday.",
    },
    {
        "source_type": "whatsapp",
        "text": "Morning! Siti here from the Klang branch. The May shipment "
                "payment of RM12,300 bounced. Bank acc 1142 3390 5567, "
                "Maybank. Please advise.",
    },
    {
        "source_type": "bank_csv_row",
        "text": "Date: 2026-05-03 | Payer: Tan Wei Ming | Amount: RM7,200.00 "
                "| Ref: INV-2024-0847 | Account: 5643-0021-889",
    },
    {
        "source_type": "email",
        "text": "Subject: Overdue balance\nDear team, following up on the "
                "outstanding RM980 for Lim Chee Kean (IC 880714-08-5521, "
                "lim.ck@example.com). Please chase before month end.",
    },
]
```

```python
# backend/seed/seed_data.py
from app.db import SessionLocal, engine
from app.models import Base
from app.security.detect import detect_spans
from app.security.tokenize import tokenize_record
from app.services.embeddings import embed_text
from .sample_records import SAMPLE_RECORDS

Base.metadata.create_all(engine)

def run():
    db = SessionLocal()
    for i, record in enumerate(SAMPLE_RECORDS):
        source_id = f"seed-{i}"
        spans = detect_spans(record["text"])
        sanitized_text, vault_entries = tokenize_record(
            record["text"], spans, source_id
        )
        for entry in vault_entries:
            db.add(entry)

        embedding = embed_text(sanitized_text)
        from app.models import TokenizedContent
        import json
        db.add(TokenizedContent(
            source_record_id=source_id,
            content_text=sanitized_text,
            embedding=json.dumps(embedding),
        ))
        db.commit()
        print(f"seeded {source_id}: {sanitized_text}")

if __name__ == "__main__":
    run()
```

Note that raw text is read directly from `SAMPLE_RECORDS` into
`detect_spans` and never written to any table — this script exercises
exactly the code path a real WhatsApp/bank connector would call later,
which is the point of seeding this way rather than hand-inserting already-
tokenized rows.

---

## 6. Detection: regex + GLiNER

Two detectors, because they fail in different ways. Regex is
near-deterministic for rigidly-formatted values (NRIC, phone numbers) —
use it first and trust it. GLiNER covers everything context-dependent that
regex structurally cannot (names, addresses, informal amount mentions) —
treat it as best-effort and bias the threshold toward over-tokenizing.

```python
# backend/app/security/detect.py
import re
from dataclasses import dataclass
from gliner import GLiNER

@dataclass
class Span:
    start: int
    end: int
    text: str
    label: str
    source: str  # "regex" | "gliner"

NRIC_RE = re.compile(r"\b\d{6}-\d{2}-\d{4}\b")
PHONE_RE = re.compile(r"\b(?:\+?60|0)1[0-46-9][-\s]?\d{3,4}[-\s]?\d{4}\b")
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")

REGEX_PATTERNS = [
    (NRIC_RE, "national id"),
    (PHONE_RE, "phone number"),
    (EMAIL_RE, "email"),
]

PII_LABELS = [
    "person", "phone number", "email", "address", "amount of money",
    "bank account number", "credit card number", "national id",
    "company name",
]

_model = None
def _get_model():
    global _model
    if _model is None:
        _model = GLiNER.from_pretrained("urchade/gliner_multi_pii-v1")
    return _model

def _regex_detect(text: str) -> list[Span]:
    spans = []
    for pattern, label in REGEX_PATTERNS:
        for m in pattern.finditer(text):
            spans.append(Span(m.start(), m.end(), m.group(), label, "regex"))
    return spans

def _gliner_detect(text: str, threshold: float = 0.4) -> list[Span]:
    model = _get_model()
    entities = model.predict_entities(text, PII_LABELS, threshold=threshold)
    return [
        Span(e["start"], e["end"], e["text"], e["label"], "gliner")
        for e in entities
    ]

def _overlaps(a: Span, b: Span) -> bool:
    return a.start < b.end and b.start < a.end

def detect_spans(text: str) -> list[Span]:
    """Regex spans are trusted outright. GLiNER spans are only added
    where they don't overlap a regex match, so regex always wins ties."""
    regex_spans = _regex_detect(text)
    gliner_spans = _gliner_detect(text)
    merged = list(regex_spans)
    for g in gliner_spans:
        if not any(_overlaps(g, r) for r in regex_spans):
            merged.append(g)
    return merged
```

Run a second regex safety-net pass over the *sanitized* output before it
ever reaches Gemini (§10) — cheap defense-in-depth against anything GLiNER
missed, with a different failure mode than GLiNER's own.

---

## 7. Tokenization

Same real value → same token, always, so Gemini can still notice "this
person appears in five different chats" without ever seeing who they are.
Amounts are bucketed into bands rather than opaque tokens so numeric
reasoning (comparing deal sizes, summing a quarter) still works.

```python
# backend/app/security/tokenize.py
import hmac, hashlib, json, os
from app.security.crypto import derive_key, encrypt_value
from app.models import TokenVaultEntry

TENANT_SALT = os.environ["TOKEN_ROOT_SECRET"].encode()

LABEL_TOKEN_MAP = {
    "person": "PERSON", "national id": "NRIC", "phone number": "PHONE",
    "email": "EMAIL", "bank account number": "BANKACC",
    "credit card number": "CARD", "address": "ADDR",
    "amount of money": "AMOUNT", "company name": "ORG",
}

# Who can see the real value behind each entity type. Amount bands are
# intentionally absent — they're already generalized, so no gate is needed.
ACL_POLICY = {
    "NRIC": ["compliance", "owner_director"],
    "CARD": ["compliance"],
    "BANKACC": ["finance_ops", "owner_director", "compliance"],
    "PHONE": ["finance_ops", "owner_director", "compliance", "general_employee"],
    "PERSON": ["finance_ops", "owner_director", "compliance", "general_employee"],
    "ADDR": ["compliance", "owner_director"],
    "EMAIL": ["finance_ops", "owner_director", "compliance", "general_employee"],
}

AMOUNT_BANDS = [500, 1000, 2500, 5000, 10000, 25000, 50000, 100000]

def _parse_amount(text: str) -> float:
    digits = "".join(c for c in text if c.isdigit() or c == ".")
    return float(digits) if digits else 0.0

def _band_amount(value: float) -> str:
    for i, upper in enumerate(AMOUNT_BANDS):
        if value < upper:
            return f"AMOUNT_BAND_{i}"
    return f"AMOUNT_BAND_{len(AMOUNT_BANDS)}"

def _token_for(span, source_record_id: str) -> str:
    label_key = LABEL_TOKEN_MAP.get(span.label, "MISC")
    if label_key == "AMOUNT":
        return _band_amount(_parse_amount(span.text))
    digest = hmac.new(
        TENANT_SALT, span.text.strip().lower().encode(), hashlib.sha256
    ).hexdigest()[:10]
    return f"{label_key}_{digest}"

def tokenize_record(text: str, spans: list, source_record_id: str):
    sanitized = text
    vault_entries = []
    # right-to-left so earlier offsets stay valid as we substitute
    for span in sorted(spans, key=lambda s: s.start, reverse=True):
        token = _token_for(span, source_record_id)
        sanitized = sanitized[:span.start] + token + sanitized[span.end:]

        label_key = LABEL_TOKEN_MAP.get(span.label, "MISC")
        if label_key == "AMOUNT":
            continue  # bands need no vault entry — they're already safe to show

        key = derive_key(info=f"vault:{source_record_id}".encode())
        ciphertext, nonce = encrypt_value(span.text, key)
        vault_entries.append(TokenVaultEntry(
            token=token,
            entity_type=label_key,
            encrypted_value=ciphertext,
            nonce=nonce,
            allowed_roles=json.dumps(ACL_POLICY.get(label_key, ["compliance"])),
            sensitivity="high" if label_key in ("NRIC", "CARD") else "medium",
            source_record_id=source_record_id,
        ))
    return sanitized, vault_entries
```

---

## 8. Encryption and key derivation

**Implementation note on "query-bound rotating keys":** the vault's
encryption key has to stay stable per record — you need to be able to
decrypt the same value again for a future query, so it can't literally
rotate every time. What *is* request-scoped is the **authorization** to
invoke a decrypt for a given token: each detokenization call is logged
against a specific user, token, and query hash (§10–11), and that
authorization is single-use in the audit sense — it documents exactly one
grant of access — even though the underlying AES key is stable. This is
the accurate way to describe the mechanism if asked directly.

```python
# backend/app/security/crypto.py
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

ROOT_SECRET = os.environ["TOKEN_ROOT_SECRET"].encode()  # 32+ random bytes

def derive_key(info: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(ROOT_SECRET)

def encrypt_value(value: str, key: bytes) -> tuple[bytes, bytes]:
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    return aesgcm.encrypt(nonce, value.encode(), None), nonce

def decrypt_value(ciphertext: bytes, nonce: bytes, key: bytes) -> str:
    return AESGCM(key).decrypt(nonce, ciphertext, None).decode()
```

`TOKEN_ROOT_SECRET` is the one secret that must never leak — treat it like
a database password, not an app config value.

---

## 9. Embeddings and retrieval

Embeddings are computed once per record at seed/ingestion time and stored
— never recomputed per query. Only the incoming question needs a fresh
embedding at query time. Retrieval is brute-force cosine similarity in
Python; §16 swaps this for a native pgvector query on Supabase.

```python
# backend/app/services/embeddings.py
from google import genai

client = genai.Client()

def embed_text(text: str) -> list[float]:
    result = client.models.embed_content(
        model="gemini-embedding-001",
        contents=text,
        config={"output_dimensionality": 768},
    )
    return result.embeddings[0].values
```

```python
# backend/app/services/retrieval.py
import json
import numpy as np
from app.models import TokenizedContent

def _cosine(a, b):
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

def retrieve_top_k(db, query_embedding, k=5) -> list[str]:
    rows = db.query(TokenizedContent).all()
    scored = [(_cosine(query_embedding, json.loads(r.embedding)), r) for r in rows]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r.content_text for _, r in scored[:k]]
```

This is fine at seed-data scale (dozens to low hundreds of records). It
does not scale to a real MSME's data volume — that's precisely what
pgvector on Supabase is for (§16).

---

## 10. Reasoning (Gemini)

```python
# backend/app/services/reasoning.py
from google import genai

client = genai.Client()

SYSTEM_INSTRUCTION = (
    "You are FinBrain OS's reasoning assistant. Answer only using the "
    "provided context. Never invent values. Every placeholder in the "
    "context matching the pattern TYPE_xxxxxxxxxx or AMOUNT_BAND_n is a "
    "token standing in for a real value you cannot see. Copy these tokens "
    "exactly as written into your answer — never translate, reformat, "
    "guess at, or omit them."
)

def answer_query(question: str, chunks: list[str]) -> str:
    context = "\n\n".join(chunks)
    resp = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=f"Context:\n{context}\n\nQuestion: {question}",
        config={"system_instruction": SYSTEM_INSTRUCTION},
    )
    return resp.text
```

Validate the response against the known token pattern before passing it to
detokenization (§11) — a well-formed-looking token that doesn't exist in
the vault is a signal to flag for review, not to guess at.

---

## 11. Permission-gated detokenization

```python
# backend/app/security/detokenize.py
import re, json, hashlib
from app.models import TokenVaultEntry
from app.security.crypto import derive_key, decrypt_value
from app.services.audit import write_audit_entry

TOKEN_PATTERN = re.compile(r"[A-Z_]+_(?:[0-9a-f]{6,10}|BAND_\d)")

def hash_query(question: str) -> str:
    return hashlib.sha256(question.encode()).hexdigest()[:16]

def detokenize_response(db, text: str, role: str, query_hash: str) -> str:
    for token in set(TOKEN_PATTERN.findall(text)):
        if token.startswith("AMOUNT_BAND_"):
            text = text.replace(token, _band_label(token))
            continue

        entry = db.query(TokenVaultEntry).filter_by(token=token).first()
        if not entry:
            continue  # unknown token — leave for manual review, don't guess

        authorized = role in json.loads(entry.allowed_roles)
        if authorized:
            key = derive_key(info=f"vault:{entry.source_record_id}".encode())
            value = decrypt_value(entry.encrypted_value, entry.nonce, key)
            text = text.replace(token, value)
        else:
            text = text.replace(token, f"[{entry.entity_type.lower()} — restricted]")

        write_audit_entry(db, role, token, authorized, query_hash)
    return text

def _band_label(token: str) -> str:
    bands = ["<RM500", "RM500–1K", "RM1K–2.5K", "RM2.5K–5K", "RM5K–10K",
             "RM10K–25K", "RM25K–50K", "RM50K–100K", "RM100K+"]
    idx = int(token.split("_")[-1])
    return bands[idx] if idx < len(bands) else "RM100K+"
```

---

## 12. Audit log

```python
# backend/app/services/audit.py
import hashlib, json, time
from app.models import AuditLogEntry

def _compute_hash(prev_hash: str, event: dict) -> str:
    payload = json.dumps(event, sort_keys=True) + prev_hash
    return hashlib.sha256(payload.encode()).hexdigest()

def write_audit_entry(db, role: str, token: str, authorized: bool, query_hash: str):
    last = db.query(AuditLogEntry).order_by(AuditLogEntry.id.desc()).first()
    prev_hash = last.event_hash if last else "genesis"
    event = {"user_role": role, "token": token, "authorized": authorized,
              "query_hash": query_hash, "ts": time.time()}
    entry = AuditLogEntry(prev_hash=prev_hash, event_hash=_compute_hash(prev_hash, event), **{
        k: v for k, v in event.items() if k != "ts"
    })
    db.add(entry)
    db.commit()
```

Any tampering with a historical row breaks its `event_hash`, and every row
after it — the chain is what makes tampering detectable, not any single
row's encryption.

---

## 13. API routes

```python
# backend/app/routes/query.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.embeddings import embed_text
from app.services.retrieval import retrieve_top_k
from app.services.reasoning import answer_query
from app.security.detokenize import detokenize_response, hash_query

router = APIRouter()

class QueryRequest(BaseModel):
    question: str
    role: str  # "general_employee" | "finance_ops" | "owner_director" | "compliance"

@router.post("/query")
def query(payload: QueryRequest, db: Session = Depends(get_db)):
    query_embedding = embed_text(payload.question)
    chunks = retrieve_top_k(db, query_embedding, k=5)
    raw_answer = answer_query(payload.question, chunks)
    final_answer = detokenize_response(
        db, raw_answer, payload.role, hash_query(payload.question)
    )
    return {"answer": final_answer}
```

```python
# backend/app/routes/audit_log.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import AuditLogEntry

router = APIRouter()

@router.get("/audit-log")
def audit_log(role: str, db: Session = Depends(get_db)):
    if role != "compliance":
        raise HTTPException(status_code=403, detail="Compliance role required")
    entries = db.query(AuditLogEntry).order_by(AuditLogEntry.id.desc()).limit(200).all()
    return [{"role": e.user_role, "token": e.token, "authorized": e.authorized,
              "ts": e.ts.isoformat()} for e in entries]
```

```python
# backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import query, audit_log

app = FastAPI(title="FinBrain OS")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(query.router)
app.include_router(audit_log.router)
```

---

## 14. Frontend

```typescript
// frontend/src/api/client.ts
const BASE_URL = "http://localhost:8000";

export async function askQuestion(question: string, role: string) {
  const res = await fetch(`${BASE_URL}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, role }),
  });
  return res.json();
}

export async function fetchAuditLog(role: string) {
  const res = await fetch(`${BASE_URL}/audit-log?role=${role}`);
  if (!res.ok) return [];
  return res.json();
}
```

```tsx
// frontend/src/components/RoleSelector.tsx
const ROLES = [
  { value: "general_employee", label: "General employee" },
  { value: "finance_ops", label: "Finance / ops staff" },
  { value: "owner_director", label: "Owner / director" },
  { value: "compliance", label: "Compliance" },
];

export function RoleSelector({ role, onChange }: { role: string; onChange: (r: string) => void }) {
  return (
    <label className="flex items-center gap-2 text-sm text-neutral-600">
      Viewing as
      <select
        className="border border-neutral-300 rounded-md px-2 py-1 text-sm"
        value={role}
        onChange={(e) => onChange(e.target.value)}
      >
        {ROLES.map((r) => (
          <option key={r.value} value={r.value}>{r.label}</option>
        ))}
      </select>
    </label>
  );
}
```

```tsx
// frontend/src/components/ChatWindow.tsx
import { useState } from "react";
import { askQuestion } from "../api/client";

type Message = { role: "user" | "assistant"; text: string };

export function ChatWindow({ role }: { role: string }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  async function send() {
    if (!input.trim()) return;
    const question = input;
    setMessages((m) => [...m, { role: "user", text: question }]);
    setInput("");
    setLoading(true);
    const { answer } = await askQuestion(question, role);
    setMessages((m) => [...m, { role: "assistant", text: answer }]);
    setLoading(false);
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-2 min-h-[300px]">
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "self-end bg-neutral-900 text-white rounded-lg px-3 py-2 max-w-md" : "self-start bg-neutral-100 rounded-lg px-3 py-2 max-w-md"}>
            {m.text}
          </div>
        ))}
        {loading && <div className="text-sm text-neutral-400">Thinking…</div>}
      </div>
      <div className="flex gap-2">
        <input
          className="flex-1 border border-neutral-300 rounded-md px-3 py-2 text-sm"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Ask about a customer, invoice, or account…"
        />
        <button onClick={send} className="bg-neutral-900 text-white rounded-md px-4 py-2 text-sm">
          Send
        </button>
      </div>
    </div>
  );
}
```

```tsx
// frontend/src/components/AuditLogTable.tsx
import { useEffect, useState } from "react";
import { fetchAuditLog } from "../api/client";

export function AuditLogTable({ role }: { role: string }) {
  const [entries, setEntries] = useState<any[]>([]);

  useEffect(() => {
    if (role !== "compliance") { setEntries([]); return; }
    fetchAuditLog(role).then(setEntries);
  }, [role]);

  if (role !== "compliance") {
    return <p className="text-sm text-neutral-400">Switch to compliance to view the audit log.</p>;
  }

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-neutral-500">
          <th className="py-1">Role</th><th>Token</th><th>Authorized</th><th>Time</th>
        </tr>
      </thead>
      <tbody>
        {entries.map((e, i) => (
          <tr key={i} className="border-t border-neutral-100">
            <td className="py-1">{e.role}</td>
            <td>{e.token}</td>
            <td>{e.authorized ? "Yes" : "No"}</td>
            <td>{new Date(e.ts).toLocaleTimeString()}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

```tsx
// frontend/src/App.tsx
import { useState } from "react";
import { RoleSelector } from "./components/RoleSelector";
import { ChatWindow } from "./components/ChatWindow";
import { AuditLogTable } from "./components/AuditLogTable";

export default function App() {
  const [role, setRole] = useState("general_employee");

  return (
    <div className="max-w-2xl mx-auto py-10 px-4">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-lg font-medium">FinBrain OS</h1>
        <RoleSelector role={role} onChange={setRole} />
      </div>
      <ChatWindow role={role} />
      <div className="mt-10">
        <h2 className="text-sm font-medium text-neutral-500 mb-2">Audit log</h2>
        <AuditLogTable role={role} />
      </div>
    </div>
  );
}
```

The role switcher makes the permission gate visible in the demo itself:
ask the same question as `general_employee`, then switch to
`owner_director` and ask again — the phone number or NRIC that came back
masked the first time resolves to a real value the second, and the audit
log records both attempts.

---

## 15. Environment variables

```bash
# backend/.env.example
GEMINI_API_KEY=
TOKEN_ROOT_SECRET=          # 32+ random bytes, e.g. `openssl rand -hex 32`
DATABASE_URL=sqlite:///./finbrain.db
```

```bash
# requirements.txt
fastapi
uvicorn[standard]
sqlalchemy
gliner
google-genai
cryptography
numpy
python-dotenv
pydantic
```

---

## 16. Migration path: SQLite → Supabase

1. **Create the Supabase project** and note the Postgres connection string
   and the pgvector extension is enabled by default on new projects
   (`create extension if not exists vector;` if not).

2. **Translate the schema.** The only real differences from §4: JSON-text
   columns become native Postgres types, and the embedding column becomes
   a `vector`.

   ```sql
   -- infra/supabase/schema.sql
   create table tokenized_content (
     id bigint generated always as identity primary key,
     source_record_id text not null,
     content_text text not null,
     embedding vector(768) not null,
     record_type text,
     summary text,
     created_at timestamptz default now()
   );

   create table token_vault (
     token text primary key,
     entity_type text not null,
     encrypted_value bytea not null,
     nonce bytea not null,
     allowed_roles text[] not null,
     sensitivity text default 'high',
     source_record_id text not null,
     created_at timestamptz default now()
   );

   create table audit_log (
     id bigint generated always as identity primary key,
     prev_hash text not null,
     event_hash text not null,
     user_role text not null,
     token text not null,
     authorized boolean not null,
     query_hash text not null,
     ts timestamptz default now()
   );

   create index on tokenized_content using ivfflat (embedding vector_cosine_ops);
   ```

3. **Enable row-level security** on `token_vault` — this is what makes
   permission enforcement a database guarantee rather than an app-layer
   one: even a direct SQL query can't return a row the caller's role isn't
   cleared for.

   ```sql
   -- infra/supabase/rls_policies.sql
   alter table token_vault enable row level security;

   create policy "role_based_vault_access" on token_vault
   for select using ( (auth.jwt() ->> 'role') = any(allowed_roles) );

   alter table audit_log enable row level security;

   create policy "compliance_only_audit_read" on audit_log
   for select using ( (auth.jwt() ->> 'role') = 'compliance' );
   ```

4. **Swap `DATABASE_URL`** in `.env` from `sqlite:///./finbrain.db` to the
   Supabase Postgres connection string. Because the SQLAlchemy models are
   dialect-agnostic, application code needs no changes except:
   - `retrieval.py`: replace the Python cosine-similarity loop with a
     native query — `order by embedding <=> :query_embedding limit :k` —
     using `pgvector-sqlalchemy` for the column type.
   - `embeddings.py`: no change needed, still calls Gemini directly.

5. **Move detokenization into a Supabase Edge Function.** This step only
   applies to `detokenize.py` — it's pure crypto and a DB lookup, no ML
   dependency, so it runs fine in Deno. `detect.py` and `tokenize.py`
   **cannot** move here because GLiNER requires Python; they stay in the
   FastAPI service, deployed separately (Cloud Run, Fly.io, or similar).

   ```typescript
   // infra/supabase/edge-functions/detokenize/index.ts
   import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

   Deno.serve(async (req) => {
     const { text, role, queryHash } = await req.json();
     const supabase = createClient(
       Deno.env.get("SUPABASE_URL")!,
       Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!
     );

     const tokens = [...text.matchAll(/[A-Z_]+_(?:[0-9a-f]{6,10}|BAND_\d)/g)]
       .map((m) => m[0]);

     let result = text;
     for (const token of new Set(tokens)) {
       const { data: entry } = await supabase
         .from("token_vault")
         .select("*")
         .eq("token", token)
         .single();
       if (!entry) continue;

       const authorized = entry.allowed_roles.includes(role);
       // decrypt() here mirrors crypto.py: HKDF-derived key, AES-256-GCM
       result = result.replace(token, authorized ? await decrypt(entry) : `[${entry.entity_type} — restricted]`);

       await supabase.from("audit_log").insert({
         user_role: role, token, authorized, query_hash: queryHash,
       });
     }
     return new Response(JSON.stringify({ result }));
   });
   ```

6. **Replace the role-dropdown simulation with real auth.** Set up
   Supabase Auth (email/password or magic link), and attach a `role`
   custom claim via a Postgres function triggered on user creation, or an
   Auth hook. Once that's in place, `auth.jwt() ->> 'role'` in the RLS
   policies above reflects a real, server-verified session instead of a
   value the frontend sent — this is the point at which the permission
   gate becomes tamper-proof end to end, not just in the demo.

---

## 17. Explicitly deferred

Stated plainly so nothing here is mistaken for "already handled":

- Live WhatsApp Business API and bank feed ingestion connectors
- OCR for scanned documents
- Multi-agent orchestration (n8n or otherwise) — the pipeline here runs as
  a single ordered sequence, not independent agents with a stop/review gate
- Formal PDPA certification / DPO workflow
- Automated key-rotation / breach protocol — for now this is a manual
  runbook step (rotate `TOKEN_ROOT_SECRET`, re-derive, re-encrypt affected
  vault rows), not an automated response
