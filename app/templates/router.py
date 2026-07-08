from fastapi import APIRouter, Depends, HTTPException
from app.db import get_database
from app.templates.schemas import TemplateCreateIn, RefreshStatusIn, TemplateOut, TemplateListResponse
from app.templates import service

router = APIRouter(prefix="/api/{restaurant_id}/templates", tags=["templates"])

@router.get("", response_model=TemplateListResponse)
async def get_templates(
    restaurant_id: str,
    db=Depends(get_database),
):
    return await service.list_templates(db, restaurant_id)

@router.post("", response_model=TemplateOut)
async def create_template(
    restaurant_id: str,
    body: TemplateCreateIn,
    db=Depends(get_database),
):
    result = await service.create_template(db, restaurant_id, body)
    if result == "meta_error":
        raise HTTPException(status_code=400, detail="Failed to create template in Meta. Check formatting.")
    return result

@router.post("/refresh-status", response_model=TemplateListResponse)
async def refresh_status(
    restaurant_id: str,
    body: RefreshStatusIn,
    db=Depends(get_database),
):
    # Post is used because credentials are in the body
    return await service.refresh_template_statuses(db, restaurant_id, body.waba_id, body.access_token)

@router.delete("/{name}")
async def delete_template(
    restaurant_id: str,
    name: str,
    body: RefreshStatusIn,  # Passed in body to avoid token in URL
    db=Depends(get_database),
):
    result = await service.delete_template(db, restaurant_id, name, body.waba_id, body.access_token)
    if result == "error":
        raise HTTPException(status_code=400, detail="Failed to delete from Meta.")
    return {"success": True}