from fastapi import APIRouter, Depends, HTTPException
from app.db import get_database
from app.restaurants.schemas import RestaurantIn, RestaurantOut, RestaurantCreateResponse
from app.restaurants import service

# No {restaurant_id} prefix here (unlike menu's /api/{restaurant_id}/menu) —
# the restaurant IS the resource, matching the old Node backend's exact
# paths: /api/restaurants, /api/restaurants/{id}. This keeps auth_api.dart,
# settings_api_service.dart, and register_screen.dart working with zero
# changes on the Flutter side.
router = APIRouter(prefix="/api/restaurants", tags=["restaurants"])


@router.post("", response_model=RestaurantCreateResponse, status_code=201)
async def register_restaurant(
    payload: RestaurantIn,
    db=Depends(get_database),
):
    """Matches Node's POST /api/restaurants. register_screen.dart reads
    responseData['restaurant']['_id'] from this response."""
    restaurant = await service.create_restaurant(db, payload)
    return RestaurantCreateResponse(restaurant=restaurant)


@router.get("", response_model=list[RestaurantOut])
async def list_restaurants(db=Depends(get_database)):
    """Matches Node's GET /api/restaurants — returns the full list.
    auth_api.dart's verifyRestaurantId and settings_api_service.dart's
    fetchRestaurantProfile both fetch this and filter client-side by id.
    Kept as-is for zero-change compatibility; see GET /{id} below for
    the more efficient path going forward."""
    return await service.list_restaurants(db)


@router.get("/{restaurant_id}", response_model=RestaurantOut)
async def get_restaurant(restaurant_id: str, db=Depends(get_database)):
    """NEW — not present in the old Node backend. Additive only; doesn't
    replace GET /api/restaurants, so nothing breaks. Lets a future
    Flutter update fetch a single restaurant directly instead of pulling
    the entire list to find one match."""
    restaurant = await service.get_restaurant(db, restaurant_id)
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    return restaurant


@router.put("/{restaurant_id}", response_model=RestaurantOut)
async def update_restaurant(
    restaurant_id: str,
    payload: RestaurantIn,
    db=Depends(get_database),
):
    """Matches Node's PUT /api/restaurants/{id}. settings_api_service.dart's
    updateRestaurantSettings sends partial field updates here — 200 on
    success, 404 if the restaurant doesn't exist."""
    updated = await service.update_restaurant(db, restaurant_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    return updated