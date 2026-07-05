"""
Meta Graph API client for the menu module.

Kept separate from service.py (Mongo CRUD) on purpose — same separation
of concerns as the Flutter side's catalog_sync.dart vs menu_api.dart/menu_db.dart.
Nothing in here touches Mongo directly; it only talks to Meta.
"""
import httpx

GRAPH_BASE = "https://graph.facebook.com/v19.0"


async def push_item_to_meta(
    retailer_id: str,
    name: str,
    price: float,
    catalog_id: str,
    access_token: str,
    image_url: str = "",
    description: str = "",
    product_link: str = "",
    is_available: bool = True,
) -> bool:
    """Create-or-update a single item in Meta's catalog (matches Flutter's
    addItemToMeta / updateItemDetailsInMeta — Meta's items_batch endpoint
    handles both as an UPDATE when the retailer_id already exists, so we
    just always send UPDATE with full fields; Meta upserts internally)."""
    if not catalog_id or not access_token:
        return False

    url = f"{GRAPH_BASE}/{catalog_id}/items_batch"
    payload = {
        "item_type": "PRODUCT_ITEM",
        "requests": [
            {
                "method": "UPDATE",
                "id": retailer_id,
                "retailer_id": retailer_id,
                "data": {
                    "id": retailer_id,
                    "title": name,
                    "description": description or "Menu Item",
                    "availability": "in stock" if is_available else "out of stock",
                    "condition": "new",
                    "price": f"{price:.2f} INR",
                    "image_link": image_url or "https://placehold.co/600x600/096A56/FFFFFF.png",
                    "link": product_link or "https://wa.me",
                    "brand": "TYM",
                },
            }
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}",
                },
                json=payload,
            )
            return response.status_code == 200
    except Exception:
        return False


async def delete_item_from_meta(retailer_id: str, catalog_id: str, access_token: str) -> bool:
    if not catalog_id or not access_token or not retailer_id:
        return False

    url = f"{GRAPH_BASE}/{catalog_id}/items_batch"
    payload = {
        "item_type": "PRODUCT_ITEM",
        "requests": [
            {
                "method": "DELETE",
                "id": retailer_id,
                "retailer_id": retailer_id,
                "data": {"id": retailer_id},
            }
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}",
                },
                json=payload,
            )
            return response.status_code == 200
    except Exception:
        return False


async def fetch_catalog_from_meta(catalog_id: str, access_token: str) -> list[dict]:
    """Pulls the entire Meta catalog, following pagination — ported from
    Flutter's CatalogSyncService.fetchCatalogFromMeta."""
    if not catalog_id or not access_token:
        return []

    all_items: list[dict] = []
    next_url = (
        f"{GRAPH_BASE}/{catalog_id}/products"
        "?fields=id,retailer_id,name,description,price,image_url,availability&limit=1000"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            while next_url:
                response = await client.get(
                    next_url, headers={"Authorization": f"Bearer {access_token}"}
                )
                if response.status_code != 200:
                    break

                decoded = response.json()
                items = decoded.get("data") or []
                all_items.extend(items)

                paging = decoded.get("paging") or {}
                cursors = paging.get("cursors") or {}
                next_url = paging.get("next") if cursors.get("after") else None
    except Exception:
        pass

    return all_items