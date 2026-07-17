from pydantic import BaseModel


class DeliverySettingsUpdate(BaseModel):
    """Body for PUT — both toggles are optional so the restaurant app can
    update just one switch at a time without needing to know the other's
    current value."""
    send_pickup_message: bool | None = None
    send_delivered_message: bool | None = None


class DeliverySettingsOut(BaseModel):
    restaurant_id: str
    # Defaults chosen to match your original plan: pickup message optional
    # (default off, since it's the "extra" one), delivered/feedback message
    # on by default since that's the core "thank you" touchpoint.
    send_pickup_message: bool = False
    send_delivered_message: bool = True