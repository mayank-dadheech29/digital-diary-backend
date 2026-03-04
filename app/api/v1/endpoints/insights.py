from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, text
from sqlalchemy.orm import selectinload
from uuid import UUID
from datetime import datetime, timezone, timedelta
import math
from typing import List, Optional
from pydantic import BaseModel

from app.core.database import get_db
from app.models.transaction import Transaction
from app.models.entry import Entry
from app.models.contact import Contact
from app.models.entry_contact import EntryContact
from app.core.auth import get_current_user

router = APIRouter()


class InsightItem(BaseModel):
    icon: str
    icon_color: str  # e.g., "orange", "purple", "blue", "green", "red"
    title: str
    subtitle: str
    destination: str  # "len_den", "search:<query>", "contacts", or "none"


class InsightsResponse(BaseModel):
    insights: List[InsightItem]
    has_data: bool


@router.get("/", response_model=InsightsResponse)
async def get_insights(
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    insights: List[InsightItem] = []

    # ── 1. Pending commitments ──────────────────────────────────────────────
    pending_result = await db.execute(
        select(func.count(Transaction.id)).where(
            and_(Transaction.user_id == user_id, Transaction.status == "PENDING")
        )
    )
    pending_count = pending_result.scalar_one_or_none() or 0

    overdue_result = await db.execute(
        select(func.count(Transaction.id)).where(
            and_(
                Transaction.user_id == user_id,
                Transaction.status == "PENDING",
                Transaction.due_date < now,
            )
        )
    )
    overdue_count = overdue_result.scalar_one_or_none() or 0

    if pending_count > 0:
        overdue_suffix = f" • {overdue_count} overdue" if overdue_count > 0 else ""
        insights.append(InsightItem(
            icon="chart.line.uptrend.xyaxis",
            icon_color="orange",
            title=f"{pending_count} commitment{'s' if pending_count != 1 else ''} pending",
            subtitle=f"Review your promises{overdue_suffix}",
            destination="len_den"
        ))

    # ── 2. Notes this week ─────────────────────────────────────────────────
    notes_result = await db.execute(
        select(func.count(Entry.id)).where(
            and_(
                Entry.user_id == user_id,
                Entry.created_at >= week_ago,
            )
        )
    )
    notes_count = notes_result.scalar_one_or_none() or 0
    total_notes_result = await db.execute(
        select(func.count(Entry.id)).where(Entry.user_id == user_id)
    )
    total_notes = total_notes_result.scalar_one_or_none() or 0

    if total_notes > 0:
        insights.append(InsightItem(
            icon="note.text",
            icon_color="purple",
            title=f"{notes_count if notes_count > 0 else 'No'} note{'s' if notes_count != 1 else ''} this week",
            subtitle=f"{total_notes} total interactions logged",
            destination="search:recent notes"
        ))

    # ── 3. Soonest upcoming due transaction ───────────────────────────────
    soonest_result = await db.execute(
        select(Transaction)
        .options(selectinload(Transaction.contact))
        .where(
            and_(
                Transaction.user_id == user_id,
                Transaction.status == "PENDING",
                Transaction.due_date >= now,
            )
        )
        .order_by(Transaction.due_date.asc())
        .limit(1)
    )
    soonest = soonest_result.scalar_one_or_none()

    if soonest is not None:
        due = soonest.due_date
        # Ensure due_date is timezone-aware before comparing
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        else:
            due = due.astimezone(timezone.utc)

        delta = due - now
        # Use ceiling so "23:59 remaining" shows as 1 day, not 0
        days_left = math.ceil(delta.total_seconds() / 86400)
        amount_str = (
            f"₹{int(soonest.amount)}" if soonest.amount else soonest.category
        )
        contact_name = soonest.contact.full_name if soonest.contact else "someone"
        days_str = "today" if days_left <= 0 else f"in {days_left} day{'s' if days_left != 1 else ''}"
        insights.append(InsightItem(
            icon="calendar.badge.clock",
            icon_color="blue",
            title=f"{amount_str} due {days_str}",
            subtitle=f"From {contact_name}",
            destination="len_den"
        ))

    # ── 4. Most neglected contact (no interaction in the longest time) ────
    # Find the contact whose most recent entry is the oldest
    contacts_result = await db.execute(
        select(Contact).where(Contact.user_id == user_id).limit(50)
    )
    all_contacts = contacts_result.scalars().all()

    if all_contacts:
        oldest_contact = None
        oldest_date = None

        for contact in all_contacts:
            # Find the most recent entry linked to this contact
            entry_result = await db.execute(
                select(func.max(Entry.created_at))
                .join(EntryContact, EntryContact.entry_id == Entry.id)
                .where(EntryContact.contact_id == contact.id)
            )
            last_interaction = entry_result.scalar_one_or_none()

            if last_interaction is None:
                # Never logged — most neglected
                oldest_date = None
                oldest_contact = contact
                break
            else:
                if oldest_date is None or last_interaction < oldest_date:
                    oldest_date = last_interaction
                    oldest_contact = contact

        if oldest_contact is not None:
            if oldest_date is None:
                subtitle = "No interactions logged yet"
                days_ago_str = "never"
            else:
                aware_date = oldest_date if oldest_date.tzinfo else oldest_date.replace(tzinfo=timezone.utc)
                days_ago = (now - aware_date).days
                days_ago_str = f"{days_ago} day{'s' if days_ago != 1 else ''} ago"
                subtitle = f"Last interaction {days_ago_str}"

            insights.append(InsightItem(
                icon="person.crop.circle.badge.clock",
                icon_color="red",
                title=f"Catch up with {oldest_contact.full_name}",
                subtitle=subtitle,
                destination=f"contact:{oldest_contact.id}"
            ))

    # ── 5. Follow-up intent from notes ───────────────────────────────────
    # Scan the 20 most recent notes for follow-up intent keywords.
    # Emit an insight for the most recent note that has a linked contact.
    FOLLOWUP_KEYWORDS = [
        "call", "meet", "follow up", "follow-up", "followup",
        "reach out", "remind", "schedule", "connect", "discuss",
        "catch up", "check in", "ring", "ping", "touch base",
        "get back", "get together", "visit", "drop by",
    ]

    recent_entries_result = await db.execute(
        select(Entry)
        .options(selectinload(Entry.contacts))  # type: ignore[attr-defined]
        .where(Entry.user_id == user_id)
        .order_by(Entry.created_at.desc())
        .limit(20)
    )
    recent_entries = recent_entries_result.scalars().all()

    followup_entry = None
    followup_contact = None
    for entry in recent_entries:
        content_lower = (entry.content or "").lower()
        has_keyword = any(kw in content_lower for kw in FOLLOWUP_KEYWORDS)
        if has_keyword:
            # Find the first linked contact for this entry
            contacts_for_entry = getattr(entry, "contacts", None) or []
            if contacts_for_entry:
                followup_entry = entry
                followup_contact = contacts_for_entry[0]
                break

    if followup_entry and followup_contact:
        # Truncate the note content for the subtitle (max 60 chars)
        snippet = followup_entry.content.strip().replace("\n", " ")
        if len(snippet) > 60:
            snippet = snippet[:57] + "..."
        insights.append(InsightItem(
            icon="phone.arrow.up.right",
            icon_color="green",
            title=f"Follow up with {followup_contact.full_name}",
            subtitle=f"Note: \"{snippet}\"",
            destination=f"contact:{followup_contact.id}"
        ))

    # ── 6. Contacts count (always useful for new users) ───────────────────
    contacts_count = len(all_contacts) if all_contacts else 0

    has_data = total_notes > 0 or pending_count > 0 or contacts_count > 0


    # Pad with a "Get started" card if user is brand new
    if not has_data:
        insights.append(InsightItem(
            icon="wand.and.stars",
            icon_color="cyan",
            title="Welcome! Let's get started",
            subtitle="Add your first contact to begin",
            destination="contacts"
        ))
    elif len(insights) == 0:
        insights.append(InsightItem(
            icon="checkmark.seal",
            icon_color="green",
            title="All caught up!",
            subtitle="No pending items right now",
            destination="none"
        ))

    return InsightsResponse(insights=insights, has_data=has_data)
