"""Apply column additions directly via SQL."""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.config import settings

async def run():
    engine = create_async_engine(settings.async_database_url, connect_args={"ssl": "require"})
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE student_sessions ADD COLUMN IF NOT EXISTS all_messages JSONB NOT NULL DEFAULT '[]'"))
        await conn.execute(text("ALTER TABLE student_sessions ADD COLUMN IF NOT EXISTS ended_at TIMESTAMPTZ"))
        await conn.execute(text("ALTER TABLE student_sessions ADD COLUMN IF NOT EXISTS duration_seconds INTEGER"))
        await conn.execute(text("ALTER TABLE student_progress ADD COLUMN IF NOT EXISTS was_completed BOOLEAN NOT NULL DEFAULT false"))
        await conn.execute(text("ALTER TABLE students ADD COLUMN IF NOT EXISTS last_login_date TIMESTAMPTZ"))
    await engine.dispose()
    print("All columns added successfully!")

asyncio.run(run())
