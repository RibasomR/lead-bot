"""Импорт поисковых фраз из data/search_phrases.txt в БД"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.database.engine import get_session, init_db
from shared.database.crud import import_search_phrases


async def main():
    await init_db()
    phrases_file = Path(__file__).parent.parent / "data" / "search_phrases.txt"

    async with get_session() as session:
        count = await import_search_phrases(session, str(phrases_file))
        await session.commit()
        print(f"✅ Импортировано {count} новых фраз")


if __name__ == "__main__":
    asyncio.run(main())
