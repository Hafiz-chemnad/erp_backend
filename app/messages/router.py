from fastapi import APIRouter, HTTPException
from app.messages import service
from app.messages.schemas import SendTextIn, SendTemplateIn

router = APIRouter(prefix="/api", tags=["Messages"])


@router.post("/sendTextMessage")
async def send_text_message(body: SendTextIn):
    try:
        return await service.send_text(
            body.restaurantId, body.phoneNumberId, body.customerNumber, body.messageText, body.customerId
        )
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/sendTemplateMessage")
async def send_template_message(body: SendTemplateIn):
    try:
        return await service.send_template(
            body.restaurantId, body.phoneNumberId, body.customerNumber,
            body.templateName, body.languageCode, body.components
        )
    except ValueError as e:
        raise HTTPException(404, str(e))