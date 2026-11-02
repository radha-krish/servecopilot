import asyncpg


async def create_pool(database_url: str, init=None) -> asyncpg.Pool:
    return await asyncpg.create_pool(
        dsn=database_url,
        min_size=1,
        max_size=5,
        init=init,
    )
