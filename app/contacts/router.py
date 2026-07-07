from fastapi import APIRouter, Depends, HTTPException, Query
from app.db import get_database
from app.contacts.schemas import (
    ContactIn, ContactBulkIn, ContactLabelsUpdate,
    ContactOut, ContactListResponse, ContactBulkResult,
)
from app.contacts import service

router = APIRouter(prefix="/api/{restaurant_id}/contacts", tags=["contacts"])


@router.get("", response_model=ContactListResponse)
async def get_contacts(
    restaurant_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db=Depends(get_database),
):
    return await service.list_contacts(db, restaurant_id, page, limit)


@router.post("", response_model=ContactOut)
async def add_contact(
    restaurant_id: str,
    contact: ContactIn,
    db=Depends(get_database),
):
    return await service.upsert_contact(db, restaurant_id, contact, source="manual")


@router.post("/bulk", response_model=ContactBulkResult)
async def bulk_import(
    restaurant_id: str,
    body: ContactBulkIn,
    db=Depends(get_database),
):
    return await service.bulk_import_contacts(db, restaurant_id, body)


@router.put("/{phone}/labels", response_model=ContactOut)
async def update_labels(
    restaurant_id: str,
    phone: str,
    body: ContactLabelsUpdate,
    db=Depends(get_database),
):
    result = await service.update_contact_labels(db, restaurant_id, phone, body)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="Contact not found")
    return result


@router.delete("/{phone}")
async def delete_contact(
    restaurant_id: str,
    phone: str,
    db=Depends(get_database),
):
    await service.delete_contact(db, restaurant_id, phone)
    return {"success": True}