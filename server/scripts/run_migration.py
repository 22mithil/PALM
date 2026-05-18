"""Run DB migration directly."""
import asyncio
from app.db.session import async_session_factory
from sqlalchemy import text


SQL_STATEMENTS = [
    "DROP TABLE IF EXISTS session_events CASCADE",
    "DROP TABLE IF EXISTS mastery_scores CASCADE",
    "DROP TABLE IF EXISTS sessions CASCADE",
    "DROP TABLE IF EXISTS curriculum_topics CASCADE",
    "DROP TABLE IF EXISTS student_progress CASCADE",
    "DROP TABLE IF EXISTS student_sessions CASCADE",
    "DROP TABLE IF EXISTS chapter_sections CASCADE",
    "DROP TABLE IF EXISTS chapters CASCADE",
    "DROP TABLE IF EXISTS students CASCADE",
    """CREATE TABLE IF NOT EXISTS students (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name VARCHAR(100) NOT NULL,
        email VARCHAR(255) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        grade SMALLINT NOT NULL CHECK (grade BETWEEN 1 AND 5),
        age SMALLINT,
        streak SMALLINT DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT now(),
        updated_at TIMESTAMPTZ DEFAULT now(),
        last_login_date TIMESTAMPTZ
    )""",
    """CREATE TABLE IF NOT EXISTS chapters (
        chapter_id INTEGER PRIMARY KEY,
        chapter_name VARCHAR(200) NOT NULL,
        grade SMALLINT NOT NULL CHECK (grade BETWEEN 1 AND 5),
        subject VARCHAR(100) NOT NULL DEFAULT 'Mathematics',
        section_ids TEXT[] NOT NULL DEFAULT '{}'
    )""",
    """CREATE TABLE IF NOT EXISTS chapter_sections (
        section_id VARCHAR(50) PRIMARY KEY,
        chapter_id INTEGER NOT NULL REFERENCES chapters(chapter_id) ON DELETE CASCADE,
        "order" SMALLINT NOT NULL,
        concept VARCHAR(100) NOT NULL,
        title VARCHAR(200) NOT NULL,
        difficulty VARCHAR(20) NOT NULL DEFAULT 'intro',
        prerequisite_concepts TEXT[] NOT NULL DEFAULT '{}'::TEXT[],
        explanation TEXT NOT NULL,
        examples TEXT[] NOT NULL DEFAULT '{}'::TEXT[],
        common_misconceptions TEXT[] NOT NULL DEFAULT '{}'::TEXT[],
        hint_progression TEXT[] NOT NULL DEFAULT '{}'::TEXT[],
        quiz_questions JSONB NOT NULL DEFAULT '[]'::JSONB
    )""",
    """CREATE TABLE IF NOT EXISTS student_sessions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        student_id UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
        chapter_id INTEGER REFERENCES chapters(chapter_id) ON DELETE SET NULL,
        grade SMALLINT NOT NULL DEFAULT 5,
        started_at TIMESTAMPTZ DEFAULT now(),
        turn_count INTEGER DEFAULT 0,
        session_summary TEXT,
        last_10_messages JSONB NOT NULL DEFAULT '[]'::JSONB,
        all_messages JSONB NOT NULL DEFAULT '[]'::JSONB,
        asked_questions JSONB NOT NULL DEFAULT '[]'::JSONB,
        ended_at TIMESTAMPTZ,
        duration_seconds INTEGER
    )""",
    """CREATE TABLE IF NOT EXISTS student_progress (
        student_id UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
        chapter_id INTEGER NOT NULL REFERENCES chapters(chapter_id) ON DELETE CASCADE,
        current_section_id VARCHAR(50) NOT NULL,
        section_statuses JSONB NOT NULL DEFAULT '{}'::JSONB,
        completion_percent FLOAT DEFAULT 0.0,
        last_updated TIMESTAMPTZ DEFAULT now(),
        was_completed BOOLEAN DEFAULT false,
        PRIMARY KEY (student_id, chapter_id)
    )""",
]


async def run():
    async with async_session_factory() as db:
        for stmt in SQL_STATEMENTS:
            print(f"  Executing: {stmt[:60]}...")
            await db.execute(text(stmt))
        await db.commit()
        print("Migration complete!")


if __name__ == "__main__":
    asyncio.run(run())
