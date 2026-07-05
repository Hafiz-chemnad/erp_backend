from fastapi import APIRouter, Depends, HTTPException, Query
from app.db import get_database
from app.menu.schemas import (
    MenuItemOut,
    MenuListResponse,
    MenuItemWrite,
    MenuItemUpdateFields,
    MetaCredentials,
    MetaSyncRequest,
    MetaSyncResponse,
)
from app.menu import service

router = APIRouter(prefix="/api/{restaurant_id}/menu", tags=["menu"])


@router.get("", response_model=MenuListResponse)
async def get_menu(
    restaurant_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db=Depends(get_database),
):
    return await service.list_menu_items(db, restaurant_id, page, limit)


@router.post("", response_model=MenuItemOut)
async def create_or_update_item(
    restaurant_id: str,
    item: MenuItemWrite,
    db=Depends(get_database),
):
    return await service.upsert_menu_item(db, restaurant_id, item)


@router.put("/{retailer_id}", response_model=MenuItemOut)
async def update_item(
    restaurant_id: str,
    retailer_id: str,
    body: MenuItemUpdateFields,
    db=Depends(get_database),
):
    updated = await service.update_menu_item(
        db, restaurant_id, retailer_id, body.fields,
        catalog_id=body.catalog_id, access_token=body.access_token,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Menu item not found")
    return updated


@router.delete("/{retailer_id}")
async def delete_item(
    restaurant_id: str,
    retailer_id: str,
    # Credentials in the request body (not query params) so the access
    # token never lands in server/proxy access logs.
    credentials: MetaCredentials = MetaCredentials(),
    db=Depends(get_database),
):
    deleted = await service.delete_menu_item(
        db, restaurant_id, retailer_id,
        catalog_id=credentials.catalog_id, access_token=credentials.access_token,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Menu item not found")
    return {"success": True}


@router.post("/sync-meta", response_model=MetaSyncResponse)
async def sync_from_meta(
    restaurant_id: str,
    payload: MetaSyncRequest,
    db=Depends(get_database),
):
    """The ONLY entry point for pulling Meta's catalog into Mongo.
    Flutter calls this on: first-time seed (empty catalog), and the
    manual 'Sync Catalog' button. Nothing else touches Meta for reads."""
    count = await service.sync_menu_from_meta(
        db, restaurant_id, payload.catalog_id, payload.access_token
    )
    return MetaSyncResponse(synced_count=count)