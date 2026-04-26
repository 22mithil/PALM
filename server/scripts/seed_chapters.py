"""
Seed script — insert chapter/section data from JSON into NeonDB.

Usage:
    cd server
    python -m scripts.seed_chapters
"""

import asyncio
import json
import sys
from pathlib import Path

# Ensure the server package is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, text
from app.db.session import async_session_factory
from app.models.curriculum import Chapter, ChapterSection


async def seed(json_path: str) -> None:
    """Read JSON and upsert chapters + sections into the database."""
    path = Path(json_path)
    if not path.exists():
        print(f"ERROR: File not found: {path}")
        sys.exit(1)

    data = json.loads(path.read_text(encoding="utf-8"))
    print(f"Loaded {len(data)} records from {path.name}")

    async with async_session_factory() as db:
        chapters_inserted = 0
        sections_inserted = 0

        for record in data:
            if "chapter_name" in record:
                # This is a chapter record
                chapter_id = record["chapter_id"]

                # Check if exists
                existing = await db.execute(
                    select(Chapter).where(Chapter.chapter_id == chapter_id)
                )
                if existing.scalars().first():
                    print(f"  Chapter {chapter_id} already exists — skipping")
                    continue

                chapter = Chapter(
                    chapter_id=chapter_id,
                    chapter_name=record["chapter_name"],
                    grade=record["grade"],
                    subject=record.get("subject", "Mathematics"),
                    section_ids=record.get("section_ids", []),
                )
                db.add(chapter)
                chapters_inserted += 1
                print(f"  + Chapter {chapter_id}: {record['chapter_name']}")

            elif "section_id" in record:
                # This is a section record
                section_id = record["section_id"]

                existing = await db.execute(
                    select(ChapterSection).where(
                        ChapterSection.section_id == section_id
                    )
                )
                if existing.scalars().first():
                    print(f"  Section {section_id} already exists — skipping")
                    continue

                section = ChapterSection(
                    section_id=section_id,
                    chapter_id=record["chapter_id"],
                    order=record["order"],
                    concept=record["concept"],
                    title=record["title"],
                    difficulty=record.get("difficulty", "intro"),
                    prerequisite_concepts=record.get("prerequisite_concepts", []),
                    explanation=record["explanation"],
                    examples=record.get("examples", []),
                    common_misconceptions=record.get("common_misconceptions", []),
                    hint_progression=record.get("hint_progression", []),
                    quiz_questions=record.get("quiz_questions", []),
                )
                db.add(section)
                sections_inserted += 1
                print(f"  + Section {section_id}: {record['title']}")

        await db.commit()
        print(f"\nDone! Inserted {chapters_inserted} chapters, {sections_inserted} sections.")


def main():
    json_path = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).resolve().parents[2] / "docs" / "chapter2_fractions_seed (1).json"
    )
    asyncio.run(seed(json_path))


if __name__ == "__main__":
    main()
