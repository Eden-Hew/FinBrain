from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class UserRole(StrEnum):
    GENERAL_EMPLOYEE = "general_employee"
    FINANCE_OPS = "finance_ops"
    OWNER_DIRECTOR = "owner_director"
    COMPLIANCE = "compliance"


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    role: UserRole


class QueryResponse(BaseModel):
    answer: str
    model_answer: str
    model_question: str
    sources_used: int
    mode: str


class AuditEntryResponse(BaseModel):
    id: int
    role: str
    token: str
    authorized: bool
    query_hash: str
    ts: datetime


class AuditResponse(BaseModel):
    entries: list[AuditEntryResponse]
    chain_valid: bool
