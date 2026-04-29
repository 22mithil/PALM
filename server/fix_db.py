import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import os
from dotenv import load_dotenv

load_dotenv("../.env")

async def fix():
    url = os.getenv("DATABASE_URL")
    if "?" in url:
        url = url.split("?")[0]
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(url)
    async with engine.begin() as conn:
        print("Dropping tables")
        tables = [
            "session_events", "sessions", "mastery_scores", "students", 
            "curriculum_topics", "alembic_version", "student_progress", 
            "student_sessions", "chapter_sections", "chapters"
        ]
        for table in tables:
            await conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
    await engine.dispose()
    print("Done")

asyncio.run(fix())
