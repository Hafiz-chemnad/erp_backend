from fastapi import APIRouter
from app.restaurant_messages import service
from app.restaurant_messages.schemas import MessageStoreIn

router = APIRouter(prefix="/api/restaurant-messages", tags=["Restaurant Messages"])


@router.post("/store")
async def store(body: MessageStoreIn):
    return await service.store_message(body.model_dump())


@router.get("/thread")
async def thread(restaurantId: str, customerNumber: str, page: int = 1, limit: int = 50):
    return await service.get_thread(restaurantId, customerNumber, page, limit)


@router.get("/restaurant/{restaurant_id}")
async def restaurant_messages(restaurant_id: str, direction: str | None = None, page: int = 1, limit: int = 50):
    return await service.get_restaurant_messages(restaurant_id, direction, page, limit)