from fastapi import APIRouter, Depends, HTTPException, Query
from app.db import get_database
from app.campaigns.schemas import (
    CampaignStartIn, CampaignProgressIn, CampaignOut, CampaignListResponse,
)
from app.campaigns import service

router = APIRouter(prefix="/api/{restaurant_id}/campaigns", tags=["campaigns"])


@router.get("", response_model=CampaignListResponse)
async def get_campaigns(
    restaurant_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db=Depends(get_database),
):
    return await service.list_campaigns(db, restaurant_id, page, limit)


@router.get("/{campaign_id}", response_model=CampaignOut)
async def get_campaign_detail(
    restaurant_id: str,
    campaign_id: str,
    db=Depends(get_database),
):
    result = await service.get_campaign(db, restaurant_id, campaign_id)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="Campaign not found")
    return result


@router.post("", response_model=CampaignOut)
async def start_campaign(
    restaurant_id: str,
    body: CampaignStartIn,
    db=Depends(get_database),
):
    """Called ONCE, the instant 'Launch Campaign' is pressed — before any
    message has gone out. Returns campaign_id, which the client then uses
    for every subsequent /progress call in its send loop."""
    return await service.start_campaign(db, restaurant_id, body)


@router.patch("/{campaign_id}/progress", response_model=CampaignOut)
async def report_progress(
    restaurant_id: str,
    campaign_id: str,
    body: CampaignProgressIn,
    db=Depends(get_database),
):
    """Called once per recipient, immediately after that individual send
    attempt finishes (success or fail). This is what makes counts live."""
    result = await service.report_progress(db, restaurant_id, campaign_id, body)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="Campaign not found")
    if result == "cancelled":
        raise HTTPException(status_code=409, detail="Campaign was cancelled — progress not recorded")
    return result


@router.patch("/{campaign_id}/cancel", response_model=CampaignOut)
async def cancel_campaign(
    restaurant_id: str,
    campaign_id: str,
    db=Depends(get_database),
):
    result = await service.cancel_campaign(db, restaurant_id, campaign_id)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="Campaign not found")
    if result == "not_active":
        raise HTTPException(status_code=409, detail="Campaign is not currently sending")
    return result


@router.delete("/{campaign_id}")
async def delete_campaign(
    restaurant_id: str,
    campaign_id: str,
    db=Depends(get_database),
):
    result = await service.delete_campaign(db, restaurant_id, campaign_id)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="Campaign not found")
    if result == "forbidden":
        raise HTTPException(status_code=403, detail="Cannot delete a campaign that is still sending — cancel it first")
    return {"success": True}

@router.patch("/{campaign_id}/resume", response_model=CampaignOut)
async def resume_campaign(
    restaurant_id: str,
    campaign_id: str,
    db=Depends(get_database),
):
    from app.campaigns import service
    result = await service.resume_campaign(db, restaurant_id, campaign_id)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="Campaign not found")
    if result == "invalid_state":
        raise HTTPException(status_code=400, detail="Can only resume paused/cancelled campaigns")
    return result    