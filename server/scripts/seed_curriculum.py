import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.config import settings
from app.models.curriculum import Chapter, ChapterSection

async def seed():
    print(f"Connecting to {settings.async_database_url}")
    engine = create_async_engine(settings.async_database_url, connect_args={"ssl": "require"})
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    jsons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "docs", "jsons")
    print(f"Looking for JSON files in: {jsons_dir}")
    
    if not os.path.exists(jsons_dir):
        print(f"Directory not found: {jsons_dir}")
        return

    async with async_session() as db:
        for filename in os.listdir(jsons_dir):
            if not filename.endswith(".json"):
                continue
            
            filepath = os.path.join(jsons_dir, filename)
            print(f"Processing {filename}...")
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if not data or not isinstance(data, list):
                print(f"Invalid format in {filename}")
                continue
                
            chapter_data = data[0]
            section_data_list = data[1:]
            
            # Upsert Chapter
            stmt = insert(Chapter).values(
                chapter_id=chapter_data["chapter_id"],
                chapter_name=chapter_data["chapter_name"],
                grade=chapter_data.get("grade", 5),
                subject=chapter_data.get("subject", "Mathematics"),
                section_ids=chapter_data.get("section_ids", [])
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=['chapter_id'],
                set_={
                    "chapter_name": stmt.excluded.chapter_name,
                    "grade": stmt.excluded.grade,
                    "subject": stmt.excluded.subject,
                    "section_ids": stmt.excluded.section_ids
                }
            )
            await db.execute(stmt)
            
            # Upsert Sections
            for sec in section_data_list:
                sec_stmt = insert(ChapterSection).values(
                    section_id=sec["section_id"],
                    chapter_id=sec["chapter_id"],
                    order=sec["order"],
                    concept=sec["concept"],
                    title=sec["title"],
                    difficulty=sec.get("difficulty", "intro"),
                    prerequisite_concepts=sec.get("prerequisite_concepts", []),
                    explanation=sec.get("explanation", ""),
                    examples=sec.get("examples", []),
                    common_misconceptions=sec.get("common_misconceptions", []),
                    hint_progression=sec.get("hint_progression", []),
                    quiz_questions=sec.get("quiz_questions", [])
                )
                sec_stmt = sec_stmt.on_conflict_do_update(
                    index_elements=['section_id'],
                    set_={
                        "order": sec_stmt.excluded.order,
                        "concept": sec_stmt.excluded.concept,
                        "title": sec_stmt.excluded.title,
                        "difficulty": sec_stmt.excluded.difficulty,
                        "prerequisite_concepts": sec_stmt.excluded.prerequisite_concepts,
                        "explanation": sec_stmt.excluded.explanation,
                        "examples": sec_stmt.excluded.examples,
                        "common_misconceptions": sec_stmt.excluded.common_misconceptions,
                        "hint_progression": sec_stmt.excluded.hint_progression,
                        "quiz_questions": sec_stmt.excluded.quiz_questions
                    }
                )
                await db.execute(sec_stmt)
            
        await db.commit()
    await engine.dispose()
    print("Seeding complete!")

if __name__ == "__main__":
    asyncio.run(seed())
