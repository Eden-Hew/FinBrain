import re
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import TokenizedContent


class QueryIntent(StrEnum):
    SEMANTIC = "semantic"
    ANALYZE_ALL = "analyze_all"
    LIST_RECORDS = "list_records"
    LIST_SOURCES = "list_sources"
    COUNT_RECORDS = "count_records"
    COUNT_SOURCES = "count_sources"


@dataclass(frozen=True, slots=True)
class QueryPlan:
    intent: QueryIntent
    source_systems: tuple[str, ...] = ()


def source_inventory(db: Session) -> list[tuple[str, int]]:
    return list(
        db.execute(
            select(TokenizedContent.source_system, func.count(TokenizedContent.id))
            .where(TokenizedContent.processing_status == "ready")
            .group_by(TokenizedContent.source_system)
            .order_by(TokenizedContent.source_system)
        ).all()
    )


def _source_aliases(source_system: str) -> set[str]:
    readable = re.sub(r"[_.-]+", " ", source_system.casefold()).strip()
    aliases = {source_system.casefold(), readable}
    if readable == "email":
        aliases.update({"emails", "mail", "mails"})
    elif readable == "telegram":
        aliases.add("telegram messages")
    elif readable == "meeting notes":
        aliases.update({"meeting", "meetings"})
    elif readable == "support ticket":
        aliases.update({"support", "support tickets"})
    elif readable == "bank csv":
        aliases.update({"bank", "bank records", "bank transactions"})
    return {alias for alias in aliases if alias}


def _mentioned_sources(question: str, available_sources: list[str]) -> tuple[str, ...]:
    lowered = question.casefold()
    matches: list[str] = []
    for source in available_sources:
        if any(
            re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", lowered)
            for alias in _source_aliases(source)
        ):
            matches.append(source)
    return tuple(matches)


def plan_query(question: str, available_sources: list[str]) -> QueryPlan:
    """Plan trusted metadata filters before PII tokenization changes the question text."""
    lowered = re.sub(r"\s+", " ", question.casefold()).strip()
    sources = _mentioned_sources(lowered, available_sources)
    enumeration_verb = bool(re.search(r"\b(show|list|display|give|get|return|find)\b", lowered))
    enumeration_scope = bool(
        re.search(r"\b(all|content|records?|entries|messages?|emails?|sources?)\b", lowered)
    )
    explicit_column_filter = bool(
        re.search(r"\bsource[_ ]?system\b", lowered)
        or re.search(r"\bwhere\s+(?:the\s+)?source\b", lowered)
    )
    count_request = bool(
        re.search(r"\b(?:how many|count|number of|total(?: number of)?)\b", lowered)
    )
    record_count_scope = bool(
        re.search(r"\b(?:content|records?|entries|messages?|emails?)\b", lowered)
    )

    if count_request and not sources and re.search(
        r"\b(?:source systems?|sources?)\b", lowered
    ):
        return QueryPlan(QueryIntent.COUNT_SOURCES)
    if count_request and (sources or record_count_scope):
        return QueryPlan(QueryIntent.COUNT_RECORDS, sources)
    exhaustive_scope = bool(
        re.search(r"\b(?:all|each|every|entire|complete)\b", lowered)
        or re.search(r"\bacross\s+(?:all|every)\b", lowered)
    )
    analytical_request = bool(
        re.search(
            r"\b(?:analy[sz]e|summari[sz]e|synthesi[sz]e|review|compare|"
            r"patterns?|themes?|trends?|issues?|problems?|complaints?|insights?)\b",
            lowered,
        )
    )
    if exhaustive_scope and analytical_request:
        return QueryPlan(QueryIntent.ANALYZE_ALL, sources)
    if sources and (explicit_column_filter or (enumeration_verb and enumeration_scope)):
        return QueryPlan(QueryIntent.LIST_RECORDS, sources)
    if not sources and (
        re.search(r"\b(list|show|display)\s+(?:me\s+)?(?:all\s+)?source systems?\b", lowered)
        or re.fullmatch(r"(?:list|show|display)(?: me)? all sources", lowered)
    ):
        return QueryPlan(QueryIntent.LIST_SOURCES)
    return QueryPlan(QueryIntent.SEMANTIC, sources)
