from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime


class RestaurantIn(BaseModel):
    """What the Flutter app sends on POST /api/restaurants (register) and
    PUT /api/restaurants/{id} (update). Matches register_screen.dart's
    payload and settings_screen.dart's _saveSettingsToBackend fields
    exactly — field names are camelCase to match the Node backend's
    contract, no translation needed on the Flutter side.

    All fields optional here because PUT sends partial updates (e.g. just
    {"name": "...", "address": "..."} from the Profile tab) while POST
    sends the full payload. Validation of "required for creation" happens
    in service.py, not here.
    """
    name: Optional[str] = None
    wabaId: Optional[str] = None
    phoneNumberId: Optional[str] = None
    waToken: Optional[str] = None
    razorpayKeyId: Optional[str] = None
    razorpayKeySecret: Optional[str] = None
    razorpayWebhookSecret: Optional[str] = None
    address: Optional[str] = None
    longitude: Optional[float] = None
    latitude: Optional[float] = None
    gstRate: Optional[float] = None
    deliveryFee: Optional[float] = None
    deliveryRadius: Optional[float] = None
    paymentAvailability: Optional[str] = None
    serviceType: Optional[str] = None
    primaryFlowType: Optional[str] = None
    deliveryFlowType: Optional[str] = None
    catalogId: Optional[str] = None
    googleSheetUrl: Optional[str] = None
    googleSheetId: Optional[str] = None
    welcomeVideoUrl: Optional[str] = None
    welcomeVideoMediaId: Optional[str] = None

    model_config = ConfigDict(extra="ignore")  # tolerate stray fields (e.g. old "menu": [{}]) without erroring


class RestaurantOut(BaseModel):
    """What the API returns. `id` matches Flutter's `r['_id']` / `r['id']`
    dual-check in auth_api.dart and settings_api_service.dart — populated
    from Mongo's native _id (as a string), not a separate stored field.
    """
    id: str = Field(alias="_id")
    name: str = ""
    wabaId: str = ""
    phoneNumberId: str = ""
    waToken: str = ""
    razorpayKeyId: str = ""
    razorpayKeySecret: str = ""
    razorpayWebhookSecret: str = ""
    address: str = ""
    longitude: float = 0.0
    latitude: float = 0.0
    gstRate: float = 0.0
    deliveryFee: float = 0.0
    deliveryRadius: float = 5.0
    paymentAvailability: str = "BOTH"
    serviceType: str = "BOTH"
    primaryFlowType: str = "LOCATION_FIRST"
    deliveryFlowType: str = "LOCATION_FIRST"
    catalogId: str = ""
    googleSheetUrl: str = ""
    googleSheetId: str = ""
    welcomeVideoUrl: str = ""
    welcomeVideoMediaId: str = ""
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    model_config = ConfigDict(populate_by_name=True)


class RestaurantCreateResponse(BaseModel):
    """Matches Node's POST response envelope: { "restaurant": { "_id": ... } }
    — register_screen.dart reads responseData['restaurant']['_id']."""
    restaurant: RestaurantOut