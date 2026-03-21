import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def clean():
    engine = create_async_engine('postgresql+asyncpg://postgres:Pratyushcr7@localhost:5432/saas_db')
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM users WHERE email = 'new_reg@acme.com'"))
    await engine.dispose()
    print('cleaned')

asyncio.run(clean())
