from fastapi import APIRouter, HTTPException
from bson import ObjectId
from app.db import get_database
from app.delivery_auth.models import DeliveryBoyLogin, TokenResponse
from app.delivery_auth.service import verify_password, create_token

login_router = APIRouter(prefix="/api/delivery-boys", tags=["delivery-auth"])


@login_router.post("/login")
async def login(body: DeliveryBoyLogin):
    db = get_database()

    auth_doc = await db.delivery_boy_auth.find_one({"phone": body.phone})
    if not auth_doc or not verify_password(body.password, auth_doc["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid phone or password")

    restaurant_id = auth_doc["restaurant_id"]
    delivery_boy = await db.delivery_boys.find_one({"_id": ObjectId(auth_doc["delivery_boy_id"])})
    name = delivery_boy["name"] if delivery_boy else ""

    token = create_token(restaurant_id, auth_doc["delivery_boy_id"], body.phone)
    return {
        "token": token,
        "delivery_boy_id": auth_doc["delivery_boy_id"],
        "name": name,
        "restaurant_id": restaurant_id,
    }