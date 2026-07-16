from pydantic import BaseModel, Field


class DeliveryBoyRegister(BaseModel):
    name: str
    phone: str
    password: str = Field(min_length=4)


class DeliveryBoyLogin(BaseModel):
    phone: str
    password: str


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=4)


class TokenResponse(BaseModel):
    token: str
    delivery_boy_id: str
    name: str