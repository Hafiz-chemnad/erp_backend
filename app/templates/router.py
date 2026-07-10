from fastapi import APIRouter, Depends, HTTPException
from app.db import get_database
from app.templates.schemas import TemplateCreateIn, RefreshStatusIn, TemplateOut, TemplateListResponse, SendMessageRequest
from app.templates import service
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
import mimetypes # 🚀 ADD THIS
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



@router.post("/upload-media")
async def upload_media(
    restaurant_id: str,
    phone_number_id: str = Form(...),
    access_token: str = Form(...),
    file: UploadFile = File(...)
):
    from app.templates import meta_client
    
    file_bytes = await file.read()
    
    # 🚀 THE FIX: Automatically detect the correct MIME type (video/mp4, image/png, etc.) 
    # from the filename extension, overriding Flutter's default 'octet-stream'.
    guessed_mime, _ = mimetypes.guess_type(file.filename)
    final_mime = guessed_mime or file.content_type or "application/octet-stream"
    
    media_id = await meta_client.upload_media_to_meta(
        phone_number_id=phone_number_id,
        access_token=access_token,
        file_bytes=file_bytes,
        file_name=file.filename,
        mime_type=final_mime  # 🚀 Pass the corrected MIME type here!
    )
    
    if not media_id:
        raise HTTPException(status_code=400, detail="Failed to upload file to Meta.")
        
    return {"success": True, "media_id": media_id}


@router.post("/send-message")
async def send_direct_message(
    restaurant_id: str,
    body: SendMessageRequest,
):
    from app.templates import meta_client 
    
    # 🚀 This now returns the WAMID string (or False if it failed)
    wamid_result = await meta_client.send_template_message(
        phone_number_id=body.phone_number_id,
        access_token=body.access_token,
        to_phone=body.to_phone,
        template_name=body.template_name,
        language_code=body.language_code,
        body_params=body.body_params,
        header_type=body.header_type,
        media_url=body.media_url,
        media_id=body.media_id,
        button_url_param=body.button_url_param
    )
    
    # 🚀 Return the WAMID explicitly so Flutter can read it!
    if wamid_result:
        return {"wamid": wamid_result}
    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Failed to send message")