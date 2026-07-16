from fastapi import APIRouter
from app.db import get_database
from app.order_assignments.models import AssignOrderRequest, AssignmentOut
from app.order_assignments import service

router = APIRouter(prefix="/api/{restaurant_id}", tags=["order-assignments"])


@router.post("/orders/{order_id}/assign", response_model=AssignmentOut)
async def assign_order(restaurant_id: str, order_id: str, body: AssignOrderRequest):
    db = get_database()
    return await service.create_assignment(db, restaurant_id, order_id, body)


@router.get("/assignments", response_model=list[AssignmentOut])
async def get_assignments(restaurant_id: str):
    db = get_database()
    return await service.list_assignments_for_restaurant(db, restaurant_id)


@router.get("/delivery-boys/{phone}/orders", response_model=list[AssignmentOut])
async def get_orders_for_delivery_boy(restaurant_id: str, phone: str):
    db = get_database()
    return await service.list_assignments_for_delivery_boy(db, restaurant_id, phone)