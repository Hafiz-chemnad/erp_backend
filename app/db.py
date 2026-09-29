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

    # ── Existing modules ──────────────────────────────────────────────────
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
    await db.templates.create_index(
        [("restaurant_id", 1), ("name", 1)], unique=True
    )
    await db.message_events.create_index([("wamid", 1)], unique=True)
    await db.restaurants.create_index([("name", 1)])
    await db.delivery_boy_auth.create_index(
        [("restaurant_id", 1), ("phone", 1)], unique=True
    )
    await db.order_assignments.create_index(
        [("restaurant_id", 1), ("order_id", 1)], unique=True
    )
    await db.order_assignments.create_index(
        [("restaurant_id", 1), ("delivery_boy_phone", 1), ("delivery_status", 1)]
    )

    # ── Orders (matches tymdb.orders) ────────────────────────────────────
    await db.orders.create_index([("orderId", 1)], unique=True)
    await db.orders.create_index([("restaurantId", 1), ("createdAt", -1)])
    await db.orders.create_index([("restaurantId", 1), ("updatedAt", -1)])
    await db.orders.create_index([("restaurantId", 1), ("paymentStatus", 1)])
    await db.orders.create_index([("customerNumber", 1)])
    # Billing: fast lookup of a table's/counter-ticket's currently open bill
    await db.orders.create_index([("restaurantId", 1), ("orderMode", 1), ("tableNumber", 1), ("paymentStatus", 1)])
    await db.orders.create_index([("restaurantId", 1), ("orderId", 1)])
    await db.pending_location_requests.create_index(
        [("restaurantId", 1), ("customerNumber", 1)], unique=True
    )

    # ── Order logs — bot's draft order before confirmation ───────────────
    await db.orderlogs.create_index([("orderId", 1)])
    await db.orderlogs.create_index([("customerNumber", 1), ("phoneNumberId", 1)])

    # ── User message logs — full chat thread (inbound + outbound) ────────
    # matches tymdb.usermessagelogs
    await db.usermessagelogs.create_index(
        [("restaurantId", 1), ("timestamp", -1)]
    )
    await db.usermessagelogs.create_index(
        [("restaurantId", 1), ("customerNumber", 1), ("timestamp", -1)]
    )
    await db.usermessagelogs.create_index([("phoneNumberId", 1)])

    # ── Message logs — raw inbound messages from customers to bot ─────────
    # matches tymdb.messagelogs
    await db.messagelogs.create_index(
        [("customerId", 1), ("createdAt", -1)]
    )
    await db.messagelogs.create_index([("phoneNumberId", 1)])

    # ── Customers ─────────────────────────────────────────────────────────
    # matches tymdb.customers
    await db.customers.create_index(
        [("restaurantId", 1), ("customerNumber", 1)], unique=True
    )

    # ── Customer sessions — bot flow state (backup to Redis) ─────────────
    # matches tymdb.customersessions
    await db.customersessions.create_index(
        [("customerNumber", 1), ("phoneNumberId", 1)], unique=True
    )
    await db.customersessions.create_index([("lastMessageAt", -1)])