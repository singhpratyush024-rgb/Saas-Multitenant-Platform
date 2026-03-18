import asyncio
import asyncpg

async def test():
    conn = await asyncpg.connect(
        user="postgres",
        password="Pratyushcr7",
        database="saas_db",
        host="localhost"
    )
    print("Connected successfully!")
    await conn.close()

asyncio.run(test())