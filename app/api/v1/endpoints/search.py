from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, case, func, cast, String, literal
from sqlalchemy.orm import selectinload
from typing import List, Optional, Literal
from uuid import UUID
from datetime import datetime, timezone, timedelta
import re

from pydantic import BaseModel, Field

from app.core.database import get_db
from app.models.contact import Contact
from app.models.entry import Entry
from app.models.entry_contact import EntryContact
from app.models.transaction import Transaction
from app.schemas.search import SearchRequest, SearchResponse, SearchSummary, CurrencyTotal
from app.schemas.entry import EntryResponse
from app.core.auth import get_current_user

router = APIRouter()

ALLOWED_TABLES = {"CONTACTS", "ENTRIES", "TRANSACTIONS"}
STOPWORDS = {
    "a", "an", "the", "is", "are", "am", "was", "were", "be", "been", "being",
    "i", "me", "my", "mine", "you", "your", "he", "she", "they", "them", "we", "our",
    "who", "what", "when", "where", "why", "how", "please", "show", "find", "search",
    "give", "get", "tell", "about", "for", "to", "in", "on", "of", "from", "with", "at",
    "and", "or", "that", "this", "those", "these", "all", "any", "some", "latest", "recent",
    "kal", "aaj", "parso", "mujhe", "mera", "meri", "mere", "kya", "ka", "ki", "ke",
    "me", "main", "hai", "tha", "thi", "the", "ko", "se", "aur", "ya", "yaa", "batao"
}

RECEIVABLE_HINTS = {"get", "receive", "receivable", "lena", "lene", "leni", "lenaa", "aana"}
PAYABLE_HINTS = {"give", "pay", "paid", "payable", "dena", "dene", "deni", "denaa"}
OUTSTANDING_HINTS = {"pending", "baki", "udhar", "due", "remaining", "rest"}
TOTAL_HINTS = {"how much", "total", "sum", "kitna", "kitne", "kitni"}


class TransactionFilters(BaseModel):
    status: Optional[Literal["PENDING", "COMPLETED", "CANCELLED"]] = Field(None, description="Transaction status")
    type: Optional[Literal["PAYABLE", "RECEIVABLE"]] = Field(None, description="Transaction type")
    overdue: Optional[bool] = Field(None, description="True if querying for overdue transactions")
    contact_name: Optional[str] = Field(None, description="Name of the person involved")
    amount_gt: Optional[float] = Field(None, description="Amount greater than this value")
    amount_lt: Optional[float] = Field(None, description="Amount less than this value")
    created_after: Optional[str] = Field(None, description="ISO datetime string for lower bound date")
    limit: Optional[int] = Field(10, ge=1, le=50, description="Number of results to return")


class ContactFilters(BaseModel):
    name: Optional[str] = Field(None, description="Name of the contact")
    org: Optional[str] = Field(None, description="Organization or company name")
    created_after: Optional[str] = Field(None, description="ISO datetime string for lower bound date")
    limit: Optional[int] = Field(10, ge=1, le=50, description="Number of results to return")


class EntryFilters(BaseModel):
    title: Optional[str] = Field(None, description="Keyword in the entry title")
    created_after: Optional[str] = Field(None, description="ISO datetime string for lower bound date")
    limit: Optional[int] = Field(10, ge=1, le=50, description="Number of results to return")


class NL2SQLIntent(BaseModel):
    use_vector_search: bool = Field(
        default=True,
        description="Set true for conceptual/semantic queries; false for strictly structured queries."
    )
    optimized_query: Optional[str] = Field(None, description="Cleaned search query for semantic search.")
    keywords: List[str] = Field(default_factory=list, description="Important tokens/entities from query.")
    target_tables: List[Literal["CONTACTS", "ENTRIES", "TRANSACTIONS"]] = Field(
        default_factory=lambda: ["CONTACTS", "ENTRIES", "TRANSACTIONS"],
        description="Tables required to answer the query."
    )
    transaction_filters: Optional[TransactionFilters] = None
    contact_filters: Optional[ContactFilters] = None
    entry_filters: Optional[EntryFilters] = None


SCHEMA_PROMPT = """
You are an NL2SQL planner for a personal digital diary + finance system.
The app supports English, Hindi, and Hinglish.

Current date & time (IST): {current_date}

Database schema (PostgreSQL):

Table CONTACTS:
- id (uuid)
- user_id (uuid)
- full_name (text)
- primary_title (text)
- primary_org (text)
- job_title_category (text)
- dynamic_details (jsonb)
- created_at (timestamptz)

Table ENTRIES:
- id (bigint)
- user_id (uuid)
- title (varchar)
- content (text)
- created_at (timestamptz)

Table TRANSACTIONS:
- id (uuid)
- user_id (uuid)
- contact_id (uuid, FK -> contacts.id)
- type (PAYABLE|RECEIVABLE)
- category (FINANCIAL|ITEM|TASK|OTHER)
- title (varchar)
- amount (float)
- currency (varchar)
- status (PENDING|COMPLETED|CANCELLED)
- due_date (timestamptz)
- description (text)
- created_at (timestamptz)

Rules:
1) Always scope results by user_id (handled by API layer).
2) If query is factual with names, status, amount, due date, or explicit numeric/date filters, include structured filters and set use_vector_search=false.
3) If query is conceptual/abstract (ideas, themes, thoughts), set use_vector_search=true.
4) If query is mixed (specific entity + semantic wording), keep useful structured filters and set use_vector_search=true.
5) Normalize synonyms:
   - pending, baki, udhar, dena hai, lena hai -> transaction status PENDING
   - received from, lena hai -> RECEIVABLE
   - paid to, dena hai -> PAYABLE
6) Relative dates (today, yesterday, last week, pichle hafte, kal) must be converted to ISO in created_after.
7) Keep keywords short and meaningful (entities, topics, places, organizations).
8) target_tables must be subset of [CONTACTS, ENTRIES, TRANSACTIONS].

Return ONLY valid JSON for this schema.
"""


def safe_parse_date(date_str: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(date_str)
    except Exception:
        return None


def extract_json_object(raw_text: str) -> Optional[str]:
    if not raw_text:
        return None
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start:end + 1]


def extract_keywords(query: str, max_terms: int = 8) -> List[str]:
    tokens = re.findall(r"[\w\u0900-\u097F]+", query.lower(), flags=re.UNICODE)
    cleaned = [t for t in tokens if len(t) > 1 and t not in STOPWORDS and not t.isdigit()]

    seen = set()
    result: List[str] = []
    for token in cleaned:
        if token not in seen:
            result.append(token)
            seen.add(token)
        if len(result) >= max_terms:
            break
    return result


def normalize_target_tables(tables: Optional[List[str]], query: str) -> List[str]:
    if tables:
        filtered = [t for t in tables if t in ALLOWED_TABLES]
        if filtered:
            return filtered

    q = query.lower()
    inferred = []
    if any(w in q for w in ["money", "amount", "rupee", "rs", "udhar", "pending", "pay", "paid", "due", "len den", "lenden"]):
        inferred.append("TRANSACTIONS")
    if any(w in q for w in ["note", "notes", "entry", "entries", "thought", "ideas", "journal"]):
        inferred.append("ENTRIES")
    if any(w in q for w in ["person", "people", "contact", "met", "called", "spoke", "who"]):
        inferred.append("CONTACTS")

    return inferred or ["CONTACTS", "ENTRIES", "TRANSACTIONS"]


def build_keyword_or(columns: List, keywords: List[str]):
    clauses = []
    for kw in keywords:
        term = f"%{kw}%"
        for col in columns:
            clauses.append(col.ilike(term))
    if not clauses:
        return None
    return or_(*clauses)


def get_ts_query(query_text: str):
    if not query_text or not query_text.strip():
        return None
    return func.websearch_to_tsquery('simple', query_text.strip())


def contains_phrase(query: str, phrases: set[str]) -> bool:
    q = query.lower()
    return any(p in q for p in phrases)


def maybe_extract_contact_phrase(query: str) -> Optional[str]:
    q = query.strip()
    patterns = [
        r"(?:from|to)\s+([a-zA-Z0-9 .'-]{2,60})",
        r"(?:with)\s+([a-zA-Z0-9 .'-]{2,60})",
    ]
    for pattern in patterns:
        match = re.search(pattern, q, flags=re.IGNORECASE)
        if not match:
            continue
        value = match.group(1).strip(" ?.,")
        value = re.sub(r"\s+(in|on|for)\s+.*$", "", value, flags=re.IGNORECASE).strip()
        if value:
            return value
    return None


def normalize_intent(intent: NL2SQLIntent, raw_query: str, request_limit: int) -> NL2SQLIntent:
    intent.target_tables = normalize_target_tables(intent.target_tables, raw_query)

    opt_query = (intent.optimized_query or raw_query).strip()
    intent.optimized_query = opt_query

    merged_keywords = []
    seen = set()
    for kw in intent.keywords + extract_keywords(raw_query) + extract_keywords(opt_query):
        token = kw.strip().lower()
        if not token or token in STOPWORDS:
            continue
        if token not in seen:
            merged_keywords.append(token)
            seen.add(token)
    intent.keywords = merged_keywords[:8]

    per_table_limit = max(1, min(request_limit, 50))
    if intent.transaction_filters and (intent.transaction_filters.limit is None):
        intent.transaction_filters.limit = per_table_limit
    if intent.contact_filters and (intent.contact_filters.limit is None):
        intent.contact_filters.limit = per_table_limit
    if intent.entry_filters and (intent.entry_filters.limit is None):
        intent.entry_filters.limit = per_table_limit

    return intent


def has_structured_filters(intent: NL2SQLIntent) -> bool:
    tf = intent.transaction_filters
    cf = intent.contact_filters
    ef = intent.entry_filters
    return any([
        bool(tf and (tf.status or tf.type or tf.overdue or tf.contact_name or tf.amount_gt is not None or tf.amount_lt is not None or tf.created_after)),
        bool(cf and (cf.name or cf.org or cf.created_after)),
        bool(ef and (ef.title or ef.created_after)),
    ])


async def parse_intent_with_ai(ai, prompt: str) -> Optional[NL2SQLIntent]:
    try:
        if ai.provider == "google":
            from google import genai

            client = genai.Client(api_key=ai.api_key_google)
            resp = await client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": NL2SQLIntent.model_json_schema(),
                    "temperature": 0.0,
                },
            )
            text_payload = getattr(resp, "text", "") or ""

        else:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=ai.api_key_openai)
            resp = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "intent_schema",
                        "schema": NL2SQLIntent.model_json_schema(),
                        "strict": True,
                    },
                },
                temperature=0,
            )
            text_payload = resp.choices[0].message.content or ""

        raw_json = extract_json_object(text_payload)
        if not raw_json:
            return None

        return NL2SQLIntent.model_validate_json(raw_json)

    except Exception as exc:
        print(f"AI Parsing Error: {exc}")
        return None


async def run_structured_search(
    intent: NL2SQLIntent,
    user_id: UUID,
    db: AsyncSession,
    limit: int,
) -> SearchResponse:
    res = SearchResponse()
    query_text = intent.optimized_query or ""
    keywords = intent.keywords
    ts_query = get_ts_query(query_text)

    if "TRANSACTIONS" in intent.target_tables:
        f = intent.transaction_filters
        stmt = select(Transaction).outerjoin(Contact, Transaction.contact_id == Contact.id).where(Transaction.user_id == user_id)

        if f:
            if f.status:
                stmt = stmt.where(Transaction.status == f.status)
            if f.type:
                stmt = stmt.where(Transaction.type == f.type)
            if f.overdue:
                stmt = stmt.where(Transaction.status == "PENDING", Transaction.due_date < func.now())
            if f.contact_name:
                stmt = stmt.where(Contact.full_name.ilike(f"%{f.contact_name}%"))
            if f.amount_gt is not None:
                stmt = stmt.where(Transaction.amount > f.amount_gt)
            if f.amount_lt is not None:
                stmt = stmt.where(Transaction.amount < f.amount_lt)
            if f.created_after:
                dt = safe_parse_date(f.created_after)
                if dt:
                    stmt = stmt.where(Transaction.created_at >= dt)

        lexical = []
        if query_text:
            term = f"%{query_text}%"
            lexical.extend([
                Transaction.title.ilike(term),
                Transaction.description.ilike(term),
                Contact.full_name.ilike(term),
            ])
            if ts_query is not None:
                lexical.append(Transaction.search_text.op("@@")(ts_query))

        kw_clause = build_keyword_or(
            [Transaction.title, Transaction.description, Contact.full_name],
            keywords,
        )
        if kw_clause is not None:
            lexical.append(kw_clause)

        # Only force lexical searches in structured mode if we haven't already explicitly satisfied the search via direct amount/numeric intent filters to prevent '1050' AND 'title contains 1050' collapsing query results to zero.
        if lexical and not (f and (f.amount_gt is not None or f.amount_lt is not None or f.created_after)):
            stmt = stmt.where(or_(*lexical))

        capped_limit = f.limit if (f and f.limit) else limit
        rank_order = func.ts_rank_cd(Transaction.search_text, ts_query) if ts_query is not None else literal(0.0)
        stmt = stmt.options(selectinload(Transaction.contact)).order_by(rank_order.desc(), Transaction.created_at.desc()).limit(capped_limit)
        res.transactions = (await db.execute(stmt)).scalars().all()

    if "CONTACTS" in intent.target_tables:
        f = intent.contact_filters
        stmt = select(Contact).where(Contact.user_id == user_id)

        if f:
            if f.name:
                stmt = stmt.where(Contact.full_name.ilike(f"%{f.name}%"))
            if f.org:
                stmt = stmt.where(Contact.primary_org.ilike(f"%{f.org}%"))
            if f.created_after:
                dt = safe_parse_date(f.created_after)
                if dt:
                    stmt = stmt.where(Contact.created_at >= dt)

        lexical = []
        if query_text:
            term = f"%{query_text}%"
            lexical.extend([
                Contact.full_name.ilike(term),
                Contact.primary_org.ilike(term),
                Contact.primary_title.ilike(term),
                Contact.job_title_category.ilike(term),
                cast(Contact.dynamic_details, String).ilike(term),
            ])
            if ts_query is not None:
                lexical.append(Contact.search_text.op("@@")(ts_query))

        kw_clause = build_keyword_or(
            [Contact.full_name, Contact.primary_org, Contact.primary_title, Contact.job_title_category, cast(Contact.dynamic_details, String)],
            keywords,
        )
        if kw_clause is not None:
            lexical.append(kw_clause)

        # Only force lexical searches in structured mode if we haven't already explicitly satisfied the search via direct amount/numeric intent filters to prevent '1050' AND 'title contains 1050' collapsing query results to zero.
        if lexical and not (f and f.created_after):
            stmt = stmt.where(or_(*lexical))

        capped_limit = f.limit if (f and f.limit) else limit
        rank_order = func.ts_rank_cd(Contact.search_text, ts_query) if ts_query is not None else literal(0.0)
        stmt = stmt.order_by(rank_order.desc(), Contact.created_at.desc()).limit(capped_limit)
        res.contacts = (await db.execute(stmt)).scalars().all()

    if "ENTRIES" in intent.target_tables:
        f = intent.entry_filters
        stmt = select(Entry).where(Entry.user_id == user_id)

        if f:
            if f.title:
                stmt = stmt.where(Entry.title.ilike(f"%{f.title}%"))
            if f.created_after:
                dt = safe_parse_date(f.created_after)
                if dt:
                    stmt = stmt.where(Entry.created_at >= dt)

        lexical = []
        if query_text:
            term = f"%{query_text}%"
            lexical.extend([Entry.title.ilike(term), Entry.content.ilike(term)])

        kw_clause = build_keyword_or([Entry.title, Entry.content], keywords)
        if kw_clause is not None:
            lexical.append(kw_clause)

        # Only force lexical searches in structured mode if we haven't already explicitly satisfied the search via direct amount/numeric intent filters to prevent '1050' AND 'title contains 1050' collapsing query results to zero.
        if lexical and not (f and f.created_after):
            stmt = stmt.where(or_(*lexical))

        capped_limit = f.limit if (f and f.limit) else limit
        stmt = stmt.options(selectinload(Entry.contacts)).order_by(Entry.created_at.desc()).limit(capped_limit)
        rows = (await db.execute(stmt)).scalars().all()
        res.entries = [EntryResponse.model_validate(e) for e in rows]

    return res


async def run_hybrid_search(
    intent: NL2SQLIntent,
    query_embedding: List[float],
    optimized_query: str,
    user_id: UUID,
    db: AsyncSession,
    limit: int = 5,
    threshold: float = 0.40,
) -> SearchResponse:
    res = SearchResponse()
    keywords = intent.keywords
    term = f"%{optimized_query}%" if optimized_query else None
    ts_query = get_ts_query(optimized_query)

    if "CONTACTS" in intent.target_tables:
        lexical = []
        stmt = select(Contact).where(
            Contact.user_id == user_id,
            and_(Contact.embedding.is_not(None), Contact.embedding.cosine_distance(query_embedding) < threshold)
        ).order_by(
            case((Contact.full_name.ilike(term), 0), else_=1) if term else literal(1),
            func.ts_rank_cd(Contact.search_text, ts_query).desc() if ts_query is not None else literal(0.0),
            case((Contact.embedding.is_not(None), Contact.embedding.cosine_distance(query_embedding)), else_=1.0),
            Contact.created_at.desc(),
        ).limit(limit)
        res.contacts = (await db.execute(stmt)).scalars().all()

    if "ENTRIES" in intent.target_tables:
        lexical = []
        stmt = select(Entry).where(
            Entry.user_id == user_id,
            and_(Entry.embedding.is_not(None), Entry.embedding.cosine_distance(query_embedding) < threshold),
        ).options(selectinload(Entry.contacts)).order_by(
            case((Entry.title.ilike(term), 0), else_=1) if term else literal(1),
            case((Entry.embedding.is_not(None), Entry.embedding.cosine_distance(query_embedding)), else_=1.0),
            Entry.created_at.desc(),
        ).limit(limit)
        rows = (await db.execute(stmt)).scalars().all()
        res.entries = [EntryResponse.model_validate(e) for e in rows]

    if "TRANSACTIONS" in intent.target_tables:
        lexical = []
        stmt = select(Transaction).outerjoin(Contact, Transaction.contact_id == Contact.id).where(
            Transaction.user_id == user_id,
            and_(Transaction.embedding.is_not(None), Transaction.embedding.cosine_distance(query_embedding) < threshold)
        ).options(selectinload(Transaction.contact)).order_by(
            case((Transaction.title.ilike(term), 0), else_=1) if term else literal(1),
            func.ts_rank_cd(Transaction.search_text, ts_query).desc() if ts_query is not None else literal(0.0),
            case((Transaction.embedding.is_not(None), Transaction.embedding.cosine_distance(query_embedding)), else_=1.0),
            Transaction.created_at.desc(),
        ).limit(limit)
        res.transactions = (await db.execute(stmt)).scalars().all()

    return res


def merge_unique(primary: SearchResponse, secondary: SearchResponse, limit: int) -> SearchResponse:
    merged = SearchResponse(
        contacts=list(primary.contacts),
        entries=list(primary.entries),
        transactions=list(primary.transactions),
    )

    def merge_list(existing, incoming):
        seen = {str(getattr(item, "id", "")) for item in existing}
        for item in incoming:
            key = str(getattr(item, "id", ""))
            if key and key not in seen:
                existing.append(item)
                seen.add(key)
            if len(existing) >= limit:
                break
        return existing

    merged.contacts = merge_list(merged.contacts, secondary.contacts)
    merged.entries = merge_list(merged.entries, secondary.entries)
    merged.transactions = merge_list(merged.transactions, secondary.transactions)
    return merged


async def resolve_candidate_contacts(
    *,
    user_id: UUID,
    db: AsyncSession,
    contact_phrase: Optional[str],
    keywords: List[str],
    limit: int,
) -> List[Contact]:
    query_terms = []
    if contact_phrase:
        query_terms.append(contact_phrase)
    query_terms.extend([k for k in keywords if len(k) > 2])
    if not query_terms:
        return []

    clauses = []
    for term in query_terms[:8]:
        token = f"%{term}%"
        clauses.extend([
            Contact.full_name.ilike(token),
            Contact.primary_org.ilike(token),
            Contact.primary_title.ilike(token),
            cast(Contact.dynamic_details, String).ilike(token),
        ])

    phrase_for_ts = contact_phrase or " ".join(query_terms[:3])
    ts_query = get_ts_query(phrase_for_ts)

    stmt = (
        select(Contact)
        .where(
            Contact.user_id == user_id,
            or_(
                *clauses,
                Contact.search_text.op("@@")(ts_query) if ts_query is not None else literal(False),
            ),
        )
        .order_by(
            case((Contact.full_name.ilike(f"%{contact_phrase}%"), 0), else_=1) if contact_phrase else literal(1),
            func.ts_rank_cd(Contact.search_text, ts_query).desc() if ts_query is not None else literal(0.0),
            Contact.created_at.desc(),
        )
        .limit(limit)
    )
    return (await db.execute(stmt)).scalars().all()


async def fetch_entries_for_contacts(
    *,
    user_id: UUID,
    db: AsyncSession,
    contact_ids: List[UUID],
    limit: int,
) -> List[EntryResponse]:
    if not contact_ids:
        return []

    stmt = (
        select(Entry)
        .join(EntryContact, EntryContact.entry_id == Entry.id)
        .where(Entry.user_id == user_id, EntryContact.contact_id.in_(contact_ids))
        .options(selectinload(Entry.contacts))
        .order_by(Entry.created_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().unique().all()
    return [EntryResponse.model_validate(e) for e in rows]


async def build_financial_summary_if_applicable(
    *,
    raw_query: str,
    intent: NL2SQLIntent,
    user_id: UUID,
    db: AsyncSession,
    limit: int,
) -> tuple[Optional[SearchSummary], List[Contact], List[EntryResponse], List[Transaction]]:
    lower_query = raw_query.lower()

    asks_total = contains_phrase(lower_query, TOTAL_HINTS)
    mentions_finance = any(
        token in lower_query
        for token in ["amount", "money", "rupee", "rs", "pay", "paid", "get", "give", "lena", "dena", "udhar", "due"]
    )

    if not (asks_total and mentions_finance):
        return None, [], [], []

    direction = None
    if contains_phrase(lower_query, RECEIVABLE_HINTS):
        direction = "RECEIVABLE"
    elif contains_phrase(lower_query, PAYABLE_HINTS):
        direction = "PAYABLE"

    pending_only = contains_phrase(lower_query, OUTSTANDING_HINTS) or direction is not None

    contact_phrase = None
    if intent.transaction_filters and intent.transaction_filters.contact_name:
        contact_phrase = intent.transaction_filters.contact_name
    if not contact_phrase and intent.contact_filters and intent.contact_filters.name:
        contact_phrase = intent.contact_filters.name
    if not contact_phrase:
        contact_phrase = maybe_extract_contact_phrase(raw_query)

    contacts = await resolve_candidate_contacts(
        user_id=user_id,
        db=db,
        contact_phrase=contact_phrase,
        keywords=intent.keywords,
        limit=max(3, min(limit, 10)),
    )
    contact_ids = [c.id for c in contacts]

    tx_stmt = select(Transaction).where(Transaction.user_id == user_id, Transaction.amount.is_not(None))
    if contact_ids:
        tx_stmt = tx_stmt.where(Transaction.contact_id.in_(contact_ids))
    if direction:
        tx_stmt = tx_stmt.where(Transaction.type == direction)
    if pending_only:
        tx_stmt = tx_stmt.where(Transaction.status == "PENDING")

    tx_stmt = tx_stmt.options(selectinload(Transaction.contact)).order_by(Transaction.created_at.desc()).limit(limit)
    tx_rows = (await db.execute(tx_stmt)).scalars().all()

    if not tx_rows and not contacts:
        return None, [], [], []

    agg_stmt = select(
        Transaction.currency,
        func.coalesce(func.sum(Transaction.amount), 0.0),
        func.count(Transaction.id),
    ).where(Transaction.user_id == user_id, Transaction.amount.is_not(None))
    if contact_ids:
        agg_stmt = agg_stmt.where(Transaction.contact_id.in_(contact_ids))
    if direction:
        agg_stmt = agg_stmt.where(Transaction.type == direction)
    if pending_only:
        agg_stmt = agg_stmt.where(Transaction.status == "PENDING")
    agg_stmt = agg_stmt.group_by(Transaction.currency)

    totals = []
    total_count = 0
    for currency, amount, count in (await db.execute(agg_stmt)).all():
        totals.append(CurrencyTotal(currency=currency or "INR", amount=float(amount or 0.0)))
        total_count += int(count or 0)

    linked_entries = await fetch_entries_for_contacts(
        user_id=user_id,
        db=db,
        contact_ids=contact_ids,
        limit=limit,
    )

    metric_label = "transaction_total"
    if direction == "RECEIVABLE":
        metric_label = "receivable_total"
    elif direction == "PAYABLE":
        metric_label = "payable_total"

    explanation = "Total amount"
    if direction == "RECEIVABLE":
        explanation = "Total amount to receive"
    elif direction == "PAYABLE":
        explanation = "Total amount to pay"
    if pending_only:
        explanation += " (pending)"
    if contact_phrase:
        explanation += f" for {contact_phrase}"

    summary = SearchSummary(
        metric=metric_label,
        explanation=explanation,
        contact_ids=contact_ids,
        transaction_count=total_count,
        currency_totals=totals,
    )
    return summary, contacts, linked_entries, tx_rows


@router.post("/", response_model=SearchResponse)
async def semantic_search(
    search_request: SearchRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
):
    ai = request.app.state.ai
    raw_query = (search_request.query or "").strip()
    if not raw_query:
        return SearchResponse()

    request_limit = max(1, min(search_request.limit or 5, 50))
    threshold = min(max(search_request.threshold or 0.40, 0.10), 0.90)

    ist = timezone(timedelta(hours=5, minutes=30))
    now_str = datetime.now(ist).strftime("%Y-%m-%dT%H:%M:%S")
    prompt = f"{SCHEMA_PROMPT.format(current_date=now_str)}\n\nUser Query: '{raw_query}'"

    intent = await parse_intent_with_ai(ai, prompt)
    print("intent before if NL2SQLIntent ", intent)
    if intent is None:
        intent = NL2SQLIntent(
            use_vector_search=True,
            optimized_query=raw_query,
            keywords=extract_keywords(raw_query),
            target_tables=["CONTACTS", "ENTRIES", "TRANSACTIONS"],
        )
    print("intent after if NL2SQLIntent ", intent)

    intent = normalize_intent(intent, raw_query, request_limit)
    print("intent after normalize_intent ", intent)

    structured_result = await run_structured_search(intent, user_id, db, request_limit)
    print("structured_result ", structured_result)

    financial_summary, financial_contacts, financial_entries, financial_transactions = await build_financial_summary_if_applicable(
        raw_query=raw_query,
        intent=intent,
        user_id=user_id,
        db=db,
        limit=request_limit,
    )
    print("financial_summary ", financial_summary)
    print("financial_contacts ", financial_contacts)
    print("financial_entries ", financial_entries)
    print("financial_transactions ", financial_transactions)

    if financial_contacts:
        existing = {str(c.id) for c in structured_result.contacts}
        for contact in financial_contacts:
            if str(contact.id) not in existing:
                structured_result.contacts.append(contact)
                existing.add(str(contact.id))
            if len(structured_result.contacts) >= request_limit:
                break

    if financial_entries:
        existing = {str(e.id) for e in structured_result.entries}
        for entry in financial_entries:
            if str(entry.id) not in existing:
                structured_result.entries.append(entry)
                existing.add(str(entry.id))
            if len(structured_result.entries) >= request_limit:
                break

    if financial_transactions:
        existing = {str(t.id) for t in structured_result.transactions}
        for txn in financial_transactions:
            if str(txn.id) not in existing:
                structured_result.transactions.append(txn)
                existing.add(str(txn.id))
            if len(structured_result.transactions) >= request_limit:
                break

    should_run_vector = intent.use_vector_search or not has_structured_filters(intent)
    if not should_run_vector:
        if financial_summary:
            structured_result.summary = financial_summary
        return structured_result

    optimized_query = intent.optimized_query or raw_query
    query_embedding = await ai.get_embedding(optimized_query)
    if not query_embedding:
        return structured_result

    vector_result = await run_hybrid_search(
        intent=intent,
        query_embedding=query_embedding,
        optimized_query=optimized_query,
        user_id=user_id,
        db=db,
        limit=request_limit,
        threshold=threshold,
    )

    final_result = merge_unique(structured_result, vector_result, request_limit)
    if financial_summary:
        final_result.summary = financial_summary
    return final_result
