from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from app.core.database import get_db
from app.models.transaction import Transaction
from app.models.contact import Contact
from app.schemas.transaction import TransactionCreate, TransactionUpdate, TransactionResponse, LenDenSummary
from app.core.auth import get_current_user

router = APIRouter()

@router.post("/", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    transaction: TransactionCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    # 1. Resolve contact context for better semantic retrieval
    contact_result = await db.execute(
        select(Contact).where(Contact.id == transaction.contact_id, Contact.user_id == user_id)
    )
    contact = contact_result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    # 2. Generate Embedding
    components = [
        contact.full_name or "",
        contact.primary_org or "",
        transaction.title or "",
        transaction.category.value if getattr(transaction, 'category', None) else "",
        transaction.type,
        str(transaction.amount) if transaction.amount is not None else "",
        transaction.currency if transaction.currency is not None else "",
        transaction.description or ""
    ]
    text_to_embed = " ".join([c for c in components if c])
    embedding = await request.app.state.ai.get_embedding(text_to_embed)

    new_transaction = Transaction(
        user_id=user_id,
        contact_id=transaction.contact_id,
        title=transaction.title,
        type=transaction.type,
        category=transaction.category.value if hasattr(transaction.category, 'value') else transaction.category,
        amount=transaction.amount,
        currency=transaction.currency,
        due_date=transaction.due_date,
        reminder_at=transaction.reminder_at,
        description=transaction.description,
        related_entry_id=transaction.related_entry_id,
        status="PENDING",
        embedding=embedding if embedding else None
    )
    
    db.add(new_transaction)
    await db.commit()
    
    # Reload with relations
    stmt = select(Transaction).options(selectinload(Transaction.contact)).where(Transaction.id == new_transaction.id)
    result = await db.execute(stmt)
    return result.scalar_one()

@router.get("/", response_model=List[TransactionResponse])
async def list_transactions(
    type: Optional[str] = Query(None, description="Filter by PAYABLE or RECEIVABLE"),
    status: Optional[str] = Query(None, description="Filter by PENDING or COMPLETED"),
    contact_id: Optional[UUID] = Query(None, description="Filter by Contact"),
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    stmt = select(Transaction).options(selectinload(Transaction.contact)).where(Transaction.user_id == user_id)
    
    if type:
        stmt = stmt.where(Transaction.type == type)
    if status:
        stmt = stmt.where(Transaction.status == status)
    if contact_id:
        stmt = stmt.where(Transaction.contact_id == contact_id)
        
    # Sort by due_date ascending (soonest first)
    stmt = stmt.order_by(Transaction.due_date.asc()).offset(skip).limit(limit)
    
    result = await db.execute(stmt)
    return result.scalars().all()

@router.get("/summary", response_model=LenDenSummary)
async def get_transaction_summary(
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    # Calculate separate totals for PENDING transactions
    stmt_payable = select(func.sum(Transaction.amount)).where(
        Transaction.user_id == user_id,
        Transaction.type == 'PAYABLE',
        Transaction.status == 'PENDING',
        Transaction.category == 'FINANCIAL'
    )
    stmt_receivable = select(func.sum(Transaction.amount)).where(
        Transaction.user_id == user_id,
        Transaction.type == 'RECEIVABLE',
        Transaction.status == 'PENDING',
        Transaction.category == 'FINANCIAL'
    )
    
    payable_result = await db.execute(stmt_payable)
    receivable_result = await db.execute(stmt_receivable)
    
    total_payable = payable_result.scalar() or 0.0
    total_receivable = receivable_result.scalar() or 0.0
    
    return {
        "total_payable": total_payable,
        "total_receivable": total_receivable,
        "net_balance": total_receivable - total_payable
    }

@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    result = await db.execute(
        select(Transaction)
        .options(selectinload(Transaction.contact))
        .where(Transaction.id == transaction_id, Transaction.user_id == user_id)
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn

@router.patch("/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(
    transaction_id: UUID,
    txn_update: TransactionUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    result = await db.execute(
        select(Transaction)
        .options(selectinload(Transaction.contact))
        .where(Transaction.id == transaction_id, Transaction.user_id == user_id)
    )
    db_txn = result.scalar_one_or_none()
    if not db_txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    update_data = txn_update.model_dump(exclude_unset=True)
    
    # If status changes to COMPLETED, set completed_at
    if 'status' in update_data and update_data['status'] == 'COMPLETED' and db_txn.status != 'COMPLETED':
        db_txn.completed_at = datetime.now()
    elif 'status' in update_data and update_data['status'] != 'COMPLETED':
        db_txn.completed_at = None
        
    for key, value in update_data.items():
        if key == 'category' and hasattr(value, 'value'):
            setattr(db_txn, key, value.value)
        else:
            setattr(db_txn, key, value)
        
    # Refresh embedding if relevant fields changed
    if any(k in update_data for k in ['title', 'category', 'amount', 'currency', 'description', 'type', 'contact_id']):
        if update_data.get("contact_id"):
            contact_result = await db.execute(
                select(Contact).where(Contact.id == db_txn.contact_id, Contact.user_id == user_id)
            )
            db_txn.contact = contact_result.scalar_one_or_none()

        components = [
            db_txn.contact.full_name if db_txn.contact else "",
            db_txn.contact.primary_org if db_txn.contact else "",
            db_txn.title or "",
            db_txn.category or "",
            db_txn.type,
            str(db_txn.amount) if db_txn.amount is not None else "",
            db_txn.currency if db_txn.currency is not None else "",
            db_txn.description or ""
        ]
        text_to_embed = " ".join([c for c in components if c])
        embedding = await request.app.state.ai.get_embedding(text_to_embed)
        db_txn.embedding = embedding
        
    await db.commit()
    await db.refresh(db_txn)
    return db_txn

@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(
    transaction_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    result = await db.execute(select(Transaction).where(Transaction.id == transaction_id, Transaction.user_id == user_id))
    txn = result.scalar_one_or_none()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    await db.delete(txn)
    await db.commit()
