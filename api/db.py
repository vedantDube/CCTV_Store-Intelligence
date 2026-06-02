# api/db.py
import os
import csv
from datetime import datetime
from typing import AsyncGenerator
from sqlmodel import Field, SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
import json

DATABASE_URL = os.getenv("DATABASE_URL")
SQLITE_URL = "sqlite+aiosqlite:///store_intelligence.db"

# Prefer PostgreSQL when DATABASE_URL is provided, otherwise use SQLite.
if DATABASE_URL:
    engine = create_async_engine(DATABASE_URL, echo=False, future=True)
else:
    engine = create_async_engine(SQLITE_URL, connect_args={"check_same_thread": False}, echo=False, future=True)

active_engine = engine

async def check_db_connection():
    global active_engine
    # If DATABASE_URL is not set, active_engine already points to SQLite.
    if not DATABASE_URL:
        print(f"[DB] DATABASE_URL not set. Using fallback SQLite: {SQLITE_URL}")
        return

    try:
        # Try a quick test connection to PostgreSQL
        async with engine.connect() as conn:
            from sqlmodel import select
            await conn.execute(select(1))
        print("[DB] Connected to PostgreSQL successfully.")
    except Exception as e:
        print(f"[DB] PostgreSQL connection failed: {e}. Falling back to SQLite: {SQLITE_URL}")
        active_engine = create_async_engine(SQLITE_URL, connect_args={"check_same_thread": False}, echo=False, future=True)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(active_engine) as session:
        yield session

# --------------------
# SQLModel Definitions
# --------------------

class DBEvent(SQLModel, table=True):
    __tablename__ = "events"
    
    event_id: str = Field(primary_key=True)
    store_id: str = Field(index=True)
    camera_id: str
    visitor_id: str = Field(index=True)
    event_type: str = Field(index=True)
    timestamp: datetime = Field(index=True)
    zone_id: str | None = Field(default=None, index=True)
    dwell_ms: int = Field(default=0)
    is_staff: bool = Field(default=False)
    confidence: float
    
    # Store metadata fields as columns
    queue_depth: int | None = Field(default=None)
    sku_zone: str | None = Field(default=None)
    session_seq: int | None = Field(default=None)

class DBTransaction(SQLModel, table=True):
    __tablename__ = "pos_transactions"
    
    transaction_id: str = Field(primary_key=True)
    store_id: str = Field(index=True)
    timestamp: datetime = Field(index=True)
    basket_value_inr: float

# Helper to load transactions from local CSV into database
async def load_pos_transactions():
    csv_path = "Brigade_Bangalore_10_April_26 (1)bc6219c.csv"
    if not os.path.exists(csv_path):
        print(f"[DB INIT] Warning: {csv_path} not found. Skipping POS transaction import.")
        return

    print(f"[DB INIT] Loading transactions from {csv_path}...")
    
    # Read transactions in a sync block and insert them
    transactions_to_insert = []
    seen_ids = set()
    
    with open(csv_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            txn_id = row.get("order_id")
            if not txn_id or txn_id in seen_ids:
                continue
                
            try:
                date_str = row.get("order_date")
                time_str = row.get("order_time")
                dt = datetime.strptime(f"{date_str} {time_str}", "%d-%m-%Y %H:%M:%S")
                
                basket_val = float(row.get("total_amount", 0))
                store_id = row.get("store_id", "ST1008")
                
                seen_ids.add(txn_id)
                transactions_to_insert.append(DBTransaction(
                    transaction_id=txn_id,
                    store_id=store_id,
                    timestamp=dt,
                    basket_value_inr=basket_val
                ))
            except Exception as e:
                # Log parsing errors
                pass

    if transactions_to_insert:
        async with AsyncSession(active_engine) as session:
            try:
                # Insert transactions using upsert logic
                for txn in transactions_to_insert:
                    await session.merge(txn)
                await session.commit()
                print(f"[DB INIT] Successfully loaded {len(transactions_to_insert)} POS transactions.")
            except Exception as e:
                print(f"[DB INIT] Error saving transactions to DB: {e}")
                await session.rollback()

async def init_db():
    await check_db_connection()
    async with active_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    await load_pos_transactions()
