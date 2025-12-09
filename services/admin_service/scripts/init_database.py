"""Initialize database with initial data"""
import asyncio
import sys
sys.path.append('.')

from sqlalchemy import select
from app.database.connection import AdminAsyncSessionLocal
from app.models.studio import Studio

async def init_database():
    """Create initial studios and classrooms"""
    print("🔧 Initializing database...")
    
    async with AdminAsyncSessionLocal() as session:
        # Check if studios exist
        result = await session.execute(select(Studio))
        existing = result.scalars().first()
        
        if existing:
            print("⚠️  Database already initialized")
            return
        
        # Create demo studios
        studios_data = [
            {
                "name": "Главная студия",
                "description": "Основная студия вокальной школы",
                "address": "г. Москва, ул. Примерная, д. 1",
                "phone": "+7 (999) 123-45-67",
                "email": "main@vocal-school.ru"
            },
            {
                "name": "Филиал №2",
                "description": "Второй филиал на севере города",
                "address": "г. Москва, ул. Северная, д. 15",
                "phone": "+7 (999) 234-56-78",
                "email": "branch2@vocal-school.ru"
            }
        ]
        
        for data in studios_data:
            studio = Studio(**data)
            session.add(studio)
        
        await session.commit()
        print("✅ Database initialized successfully")
        print(f"   - Created {len(studios_data)} studios")

if __name__ == "__main__":
    asyncio.run(init_database())
