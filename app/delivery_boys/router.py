from fastapi import APIRouter, Depends, HTTPException, Query
from app.db import get_database
from app.delivery_boys import service
from app.delivery_boys.schemas import DeliveryBoyIn, DeliveryBoyOut, DeliveryBoyListResponse, DeliveryBoyUpdate

router = APIRouter(prefix="/api/{restaurant_id}/delivery-boys", tags=["delivery_boys"])


@router.get("", response_model=DeliveryBoyListResponse)
async def list_delivery_boys(
    restaurant_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db=Depends(get_database),
):
    return await service.list_delivery_boys(db, restaurant_id, page, limit)


@router.post("", response_model=DeliveryBoyOut)
async def add_delivery_boy(
    restaurant_id: str,
    boy: DeliveryBoyIn,
    db=Depends(get_database),
):
    return await service.add_delivery_boy(db, restaurant_id, boy)


@router.put("/{phone}", response_model=DeliveryBoyOut)
async def update_delivery_boy(
    restaurant_id: str,
    phone: str,
    body: DeliveryBoyUpdate,
    db=Depends(get_database),
):
    updated = await service.update_delivery_boy(db, restaurant_id, phone, body.name)
    if not updated:
        raise HTTPException(status_code=404, detail="Delivery boy not found")
    return updated


@router.delete("/{phone}")
async def delete_delivery_boy(
    restaurant_id: str,
    phone: str,
    db=Depends(get_database),
):
    deleted = await service.delete_delivery_boy(db, restaurant_id, phone)
    if not deleted:
        raise HTTPException(status_code=404, detail="Delivery boy not found")
    return {"success": True}