from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
from bson import ObjectId
from app.db import get_database
from app.delivery_auth.models import DeliveryBoyRegister, DeliveryBoyLogin, PasswordReset, TokenResponse
from app.delivery_auth.service import hash_password, verify_password, create_token

router = APIRouter(prefix="/api/{restaurant_id}/delivery-boys", tags=["delivery-auth"])


from pymongo.errors import DuplicateKeyError

@router.post("/register", response_model=TokenResponse)
async def register(restaurant_id: str, body: DeliveryBoyRegister):
    db = get_database()

    existing_auth = await db.delivery_boy_auth.find_one(
        {"restaurant_id": restaurant_id, "phone": body.phone}
    )
    if existing_auth:
        raise HTTPException(status_code=409, detail="Phone already registered for this restaurant")

    try:
        result = await db.delivery_boys.insert_one({
            "restaurant_id": restaurant_id,
            "name": body.name,
            "phone": body.phone,
            "created_at": datetime.now(timezone.utc),
        })
    except DuplicateKeyError:
        raise HTTPException(
            status_code=409,
            detail="This phone number already exists as a delivery boy for this restaurant. Ask an admin to reset their password instead of registering again."
        )

    delivery_boy_id = str(result.inserted_id)

    await db.delivery_boy_auth.insert_one({
        "restaurant_id": restaurant_id,
        "delivery_boy_id": delivery_boy_id,
        "phone": body.phone,
        "password_hash": hash_password(body.password),
        "created_at": datetime.now(timezone.utc),
    })

    token = create_token(restaurant_id, delivery_boy_id, body.phone)
    return TokenResponse(token=token, delivery_boy_id=delivery_boy_id, name=body.name)

@router.post("/login", response_model=TokenResponse)
async def login(restaurant_id: str, body: DeliveryBoyLogin):
    db = get_database()

    auth_doc = await db.delivery_boy_auth.find_one(
        {"restaurant_id": restaurant_id, "phone": body.phone}
    )
    if not auth_doc or not verify_password(body.password, auth_doc["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid phone or password")

    delivery_boy = await db.delivery_boys.find_one({"_id": ObjectId(auth_doc["delivery_boy_id"])})
    name = delivery_boy["name"] if delivery_boy else ""

    token = create_token(restaurant_id, auth_doc["delivery_boy_id"], body.phone)
    return TokenResponse(token=token, delivery_boy_id=auth_doc["delivery_boy_id"], name=name)


@router.put("/{phone}/password")
async def reset_password(restaurant_id: str, phone: str, body: PasswordReset):
    db = get_database()

    result = await db.delivery_boy_auth.update_one(
        {"restaurant_id": restaurant_id, "phone": phone},
        {"$set": {"password_hash": hash_password(body.new_password)}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Delivery boy not found")

    return {"message": "Password updated successfully"}