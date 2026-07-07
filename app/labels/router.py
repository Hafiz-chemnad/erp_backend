from fastapi import APIRouter, Depends, HTTPException, Query
from app.db import get_database
from app.labels.schemas import LabelIn, LabelUpdate, LabelOut, LabelListResponse
from app.labels import service

router = APIRouter(prefix="/api/{restaurant_id}/labels", tags=["labels"])


@router.get("", response_model=LabelListResponse)
async def get_labels(
    restaurant_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db=Depends(get_database),
):
    # Keep counts fresh on every read — cheap since it's just count queries,
    # and matches the current app's "recalc on every load" behaviour.
    await service.recalculate_label_counts(db, restaurant_id)
    return await service.list_labels(db, restaurant_id, page, limit)


@router.post("", response_model=LabelOut)
async def create_label(
    restaurant_id: str,
    label: LabelIn,
    db=Depends(get_database),
):
    return await service.create_label(db, restaurant_id, label)


@router.put("/{label_id}", response_model=LabelOut)
async def update_label(
    restaurant_id: str,
    label_id: str,
    body: LabelUpdate,
    db=Depends(get_database),
):
    result = await service.update_label(db, restaurant_id, label_id, body)
    if result == "forbidden":
        raise HTTPException(status_code=403, detail="Automated Smart Labels cannot be edited manually")
    return result


@router.delete("/{label_id}")
async def delete_label(
    restaurant_id: str,
    label_id: str,
    db=Depends(get_database),
):
    result = await service.delete_label(db, restaurant_id, label_id)
    if result == "forbidden":
        raise HTTPException(status_code=403, detail="Automated Smart Labels cannot be deleted manually")
    return {"success": True}