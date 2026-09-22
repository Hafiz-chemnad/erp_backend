from fastapi import APIRouter, HTTPException, Query
from app.orders import service
from app.orders.schemas import OrderStatusUpdate

router = APIRouter(prefix="/api/orders", tags=["Orders"])


@router.get("/restaurant/{restaurant_id}")
async def get_orders(restaurant_id: str, status: str | None = None, page: int = 1, limit: int = 50):
    return await service.list_orders(restaurant_id, status, page, limit)


@router.get("/restaurant/{restaurant_id}/stats")
async def get_stats(restaurant_id: str):
    return await service.get_order_stats(restaurant_id)


@router.get("/{order_id}")
async def get_order(order_id: str):
    order = await service.get_order(order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    return order


@router.put("/{order_id}/status")
async def update_status(order_id: str, body: OrderStatusUpdate):
    updated = await service.update_order_status(order_id, body.paymentStatus, body.additionalNotes)
    if not updated:
        raise HTTPException(404, "Order not found")
    return updated