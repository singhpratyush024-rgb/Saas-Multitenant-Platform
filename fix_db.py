import asyncio
import os
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://postgres:Pratyushcr7@localhost:5432/saas_db'
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def clean():
    engine = create_async_engine(os.environ['DATABASE_URL'])
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM tenants WHERE slug = 'beta-iso-test'"))
    await engine.dispose()
    print('cleaned')

asyncio.run(clean())
