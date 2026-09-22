from fastapi import APIRouter, HTTPException
from app.catalog import service
from app.catalog.schemas import CatalogLinkIn, SendProductIn, SendMenuIn

router = APIRouter(prefix="/api/catalog", tags=["Catalog"])


@router.post("/link")
async def link(body: CatalogLinkIn):
    return await service.link_catalog(body.restaurantId, body.catalogId)


@router.get("/{restaurant_id}/items")
async def items(restaurant_id: str):
    return await service.get_catalog_items(restaurant_id)


@router.post("/sync-sheet")
async def sync_sheet(restaurantId: str):
    try:
        return await service.sync_from_sheet(restaurantId)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/sync")
async def sync(restaurantId: str):
    try:
        return await service.sync_catalog(restaurantId)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/send-product")
async def send_product(body: SendProductIn):
    return await service.send_product(body.restaurantId, body.customerNumber, body.phoneNumberId, body.retailerId)


@router.post("/send-menu")
async def send_menu(body: SendMenuIn):
    return await service.send_menu(body.restaurantId, body.customerNumber, body.phoneNumberId)