import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import TokenizedContent
from app.services.query_filters import QueryFilters


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
    filters: QueryFilters = QueryFilters()

    @property
    def source_systems(self) -> tuple[str, ...]:
        return self.filters.source_systems


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


def _date_range(
    lowered: str,
    *,
    now: datetime,
    timezone_name: str,
) -> tuple[datetime | None, datetime | None]:
    zone = ZoneInfo(timezone_name)
    local_now = now.astimezone(zone)
    today = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = end = None
    if re.search(r"\byesterday\b", lowered):
        start, end = today - timedelta(days=1), today
    elif re.search(r"\btoday\b", lowered):
        start, end = today, today + timedelta(days=1)
    elif re.search(r"\blast week\b", lowered):
        this_week = today - timedelta(days=today.weekday())
        start, end = this_week - timedelta(days=7), this_week
    elif re.search(r"\bthis week\b", lowered):
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=7)
    elif re.search(r"\bthis month\b", lowered):
        start = today.replace(day=1)
        end = (
            start.replace(year=start.year + 1, month=1)
            if start.month == 12
            else start.replace(month=start.month + 1)
        )
    elif match := re.search(r"\blast\s+([1-9]\d?)\s+days?\b", lowered):
        start = today - timedelta(days=int(match.group(1)) - 1)
        end = today + timedelta(days=1)
    return (
        start.astimezone(UTC) if start else None,
        end.astimezone(UTC) if end else None,
    )


def _record_types(lowered: str) -> tuple[str, ...]:
    values: list[str] = []
    rules = (
        (r"\b(?:spreadsheet rows?|invoice rows?|invoices?)\b", "invoice_row"),
        (r"\bmeeting (?:notes?|minutes)\b", "operations_minutes"),
        (r"\bsupport tickets?\b", "support_ticket"),
        (r"\bcustomer emails?\b", "customer_email"),
        (r"\btelegram messages?\b", "customer_message"),
    )
    for pattern, value in rules:
        if re.search(pattern, lowered):
            values.append(value)
    return tuple(dict.fromkeys(values))


def _categories(lowered: str) -> tuple[str, ...]:
    rules = {
        "payment_approval_delay": r"\bpayment approval delays?\b|\bapproval delays?\b",
        "customer_contact": r"\bcustomer contacts?\b",
        "approval_delay": r"\bworkflow approval delays?\b",
        "invoice": r"\binvoice categor(?:y|ies)\b",
        "uploaded_document": r"\buploaded documents?\b",
    }
    return tuple(value for value, pattern in rules.items() if re.search(pattern, lowered))


def _metadata_filters(lowered: str) -> tuple[tuple[tuple[str, str], ...], tuple[str, ...]]:
    equals: list[tuple[str, str]] = []
    for status in (
        "pending_approval",
        "overdue",
        "paid",
        "refund_requested",
        "cancelled",
        "unknown",
    ):
        readable = status.replace("_", " ")
        if re.search(rf"\b{re.escape(readable)}\b", lowered):
            equals.append(("status", status))
    if re.search(r"\b(?:without (?:an )?owner|unassigned)\b", lowered):
        equals.append(("has_assigned_owner", "false"))
    if match := re.search(r"\bamount band\s+([0-8])\b", lowered):
        equals.append(("amount_band", match.group(1)))
    return tuple(equals), ()


def plan_query(
    question: str,
    available_sources: list[str],
    *,
    now: datetime | None = None,
    timezone_name: str | None = None,
) -> QueryPlan:
    """Plan trusted metadata filters before PII tokenization changes the question text."""
    lowered = re.sub(r"\s+", " ", question.casefold()).strip()
    sources = _mentioned_sources(lowered, available_sources)
    occurred_from, occurred_to = _date_range(
        lowered,
        now=now or datetime.now(UTC),
        timezone_name=timezone_name or get_settings().application_timezone,
    )
    priorities = tuple(
        value
        for value in ("low", "medium", "high")
        if re.search(rf"\b{value}(?:-priority| priority)\b", lowered)
    )
    action_required = (
        False
        if re.search(r"\b(?:no action required|does not need action)\b", lowered)
        else True
        if re.search(r"\b(?:needs? action|action required|still needs? action)\b", lowered)
        else None
    )
    metadata_equals, metadata_missing = _metadata_filters(lowered)
    filters = QueryFilters(
        source_systems=sources,
        record_types=_record_types(lowered),
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        categories=_categories(lowered),
        priorities=priorities,
        action_required=action_required,
        metadata_equals=metadata_equals,
        metadata_missing=metadata_missing,
    )
    enumeration_verb = bool(re.search(r"\b(show|list|display|give|get|return|find)\b", lowered))
    enumeration_scope = bool(
        re.search(
            r"\b(all|content|records?|entries|messages?|emails?|sources?|"
            r"invoices?|tickets?|rows?)\b",
            lowered,
        )
    )
    explicit_column_filter = bool(
        re.search(r"\bsource[_ ]?system\b", lowered)
        or re.search(r"\bwhere\s+(?:the\s+)?source\b", lowered)
    )
    count_request = bool(
        re.search(r"\b(?:how many|count|number of|total(?: number of)?)\b", lowered)
    )
    record_count_scope = bool(
        re.search(
            r"\b(?:content|records?|entries|messages?|emails?|invoices?|tickets?|rows?)\b",
            lowered,
        )
    )

    if count_request and not sources and re.search(r"\b(?:source systems?|sources?)\b", lowered):
        return QueryPlan(QueryIntent.COUNT_SOURCES, filters)
    if count_request and (sources or record_count_scope):
        return QueryPlan(QueryIntent.COUNT_RECORDS, filters)
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
        return QueryPlan(QueryIntent.ANALYZE_ALL, filters)
    if sources and (explicit_column_filter or (enumeration_verb and enumeration_scope)):
        return QueryPlan(QueryIntent.LIST_RECORDS, filters)
    if not sources and (
        re.search(r"\b(list|show|display)\s+(?:me\s+)?(?:all\s+)?source systems?\b", lowered)
        or re.fullmatch(r"(?:list|show|display)(?: me)? all sources", lowered)
    ):
        return QueryPlan(QueryIntent.LIST_SOURCES, filters)
    return QueryPlan(QueryIntent.SEMANTIC, filters)
