from fastapi import APIRouter, HTTPException
from app.db import get_database
from app.billing.schemas import (
    POSOrderIn, POSOrderOut, OpenTableOut, OpenCounterTicketOut,
    CloseTableIn, SettlePaymentIn, MergeTablesIn, MoveTableIn, OpenPhoneOrderOut, EditItemsIn,
)
from app.billing import service

router = APIRouter(prefix="/api/{restaurant_id}/pos", tags=["Billing"])


@router.post("/send-to-kitchen", response_model=POSOrderOut)
async def send_to_kitchen(restaurant_id: str, body: POSOrderIn):
    db = get_database()
    if not body.items:
        raise HTTPException(400, "Bill must have at least one item")
    if body.orderMode in ("phone_pickup", "phone_delivery") and not body.customerNumber:
        raise HTTPException(400, "Customer phone number is required for phone orders")
    order = await service.send_to_kitchen(db, restaurant_id, body)
    return order


@router.put("/{order_id}/edit-items", response_model=POSOrderOut)
async def edit_items(restaurant_id: str, order_id: str, body: EditItemsIn):
    db = get_database()
    updated = await service.edit_sent_items(db, restaurant_id, order_id, body.items, body.discountPercent, body.discountFlat)
    if not updated:
        raise HTTPException(404, "Order not found, or it's already been settled and can no longer be edited")
    return updated


@router.post("/settle-payment", response_model=POSOrderOut)
async def settle_payment(restaurant_id: str, body: SettlePaymentIn):
    db = get_database()
    updated = await service.settle_payment(db, restaurant_id, body.orderId, body.paymentMethod)
    if not updated:
        raise HTTPException(404, "Order not found or already settled")
    return updated


@router.get("/open-tables", response_model=list[OpenTableOut])
async def open_tables(restaurant_id: str):
    db = get_database()
    return await service.get_open_tables(db, restaurant_id)


@router.get("/open-counter-tickets", response_model=list[OpenCounterTicketOut])
async def open_counter_tickets(restaurant_id: str):
    db = get_database()
    return await service.get_open_counter_tickets(db, restaurant_id)


@router.get("/open-phone-orders", response_model=list[OpenPhoneOrderOut])
async def open_phone_orders(restaurant_id: str):
    db = get_database()
    return await service.get_open_phone_orders(db, restaurant_id)


@router.put("/tables/{table_number}/close", response_model=POSOrderOut)
async def close_table(restaurant_id: str, table_number: str, body: CloseTableIn):
    db = get_database()
    updated = await service.settle_payment_by_table(db, restaurant_id, table_number, body.paymentMethod)
    if not updated:
        raise HTTPException(404, "No open bill found for that table")
    return updated


@router.post("/tables/merge", response_model=POSOrderOut)
async def merge_tables(restaurant_id: str, body: MergeTablesIn):
    db = get_database()
    if body.sourceTable == body.targetTable:
        raise HTTPException(400, "Source and target tables must be different")
    updated = await service.merge_tables(db, restaurant_id, body.sourceTable, body.targetTable)
    if not updated:
        raise HTTPException(404, "Both tables must have an open bill to merge")
    return updated


@router.put("/tables/{table_number}/move", response_model=POSOrderOut)
async def move_table(restaurant_id: str, table_number: str, body: MoveTableIn):
    db = get_database()
    updated = await service.move_table(db, restaurant_id, table_number, body.newTable)
    if not updated:
        raise HTTPException(400, "No open bill on source table, or destination table already occupied")
    return updated
