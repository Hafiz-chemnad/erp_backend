from fastapi import APIRouter, Depends
from app.db import get_database
from app.delivery_settings.models import DeliverySettingsOut, DeliverySettingsUpdate
from app.delivery_settings import service

router = APIRouter(prefix="/api/{restaurant_id}/delivery-settings", tags=["delivery-settings"])


@router.get("", response_model=DeliverySettingsOut)
async def get_delivery_settings(restaurant_id: str, db=Depends(get_database)):
    return await service.get_settings(db, restaurant_id)


@router.put("", response_model=DeliverySettingsOut)
async def update_delivery_settings(
    restaurant_id: str,
    body: DeliverySettingsUpdate,
    db=Depends(get_database),
):
    return await service.update_settings(db, restaurant_id, body)