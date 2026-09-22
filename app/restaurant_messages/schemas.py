from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


class MessageStoreIn(BaseModel):
    restaurantId: str
    customerNumber: str
    phoneNumberId: str
    customerId: Optional[str] = None
    direction: str                      # inbound | outbound
    messageType: str                    # text | image | audio | video | location | interactive
    messageContent: Any                 # string or object, matches Node's flexible shape


class MessageOut(BaseModel):
    restaurantId: str
    customerNumber: str
    phoneNumberId: str
    customerId: Optional[str] = None
    direction: str
    messageType: str
    messageContent: Any
    timestamp: datetime


class ThreadResponse(BaseModel):
    messages: list[MessageOut]
    totalMessages: int
    currentPage: int
    totalPages: int