from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.MONGO_URI)
    return _client


def get_database():
    return get_client()[settings.DB_NAME]


async def ensure_indexes():
    """Call once on startup. Add one line per module as you build them."""
    db = get_database()
    await db.menu_items.create_index(
        [("restaurant_id", 1), ("retailer_id", 1)], unique=True
    )
    await db.delivery_boys.create_index(
        [("restaurant_id", 1), ("phone", 1)], unique=True
    )
    await db.labels.create_index(
        [("restaurant_id", 1), ("label_id", 1)], unique=True
    )
    await db.contacts.create_index(
        [("restaurant_id", 1), ("phone", 1)], unique=True
    )
     await db.campaigns.create_index(                     
        [("restaurant_id", 1), ("campaign_id", 1)], unique=True
    )