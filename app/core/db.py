from contextlib import asynccontextmanager
from prisma import Prisma

db = Prisma()

@asynccontextmanager
async def lifespan(app):
    await db.connect()
    try:
        yield
    finally:
        await db.disconnect()
