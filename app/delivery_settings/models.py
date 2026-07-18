from pydantic import BaseModel


class DeliverySettingsUpdate(BaseModel):
    send_pickup_message: bool | None = None
    send_delivered_message: bool | None = None
    delivery_charge: float | None = None


class DeliverySettingsOut(BaseModel):
    restaurant_id: str
    send_pickup_message: bool = False
    send_delivered_message: bool = True
    delivery_charge: float = 0.0