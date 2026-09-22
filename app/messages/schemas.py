from pydantic import BaseModel
from typing import Optional


class SendTextIn(BaseModel):
    restaurantId: str
    customerNumber: str
    phoneNumberId: str
    customerId: Optional[str] = None
    messageText: str


class SendTemplateIn(BaseModel):
    restaurantId: str
    customerNumber: str
    phoneNumberId: str
    templateName: str
    languageCode: str = "en_US"
    components: Optional[list] = None   # header/body variable substitutions