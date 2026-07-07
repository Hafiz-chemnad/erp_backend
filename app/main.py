from fastapi import FastAPI
from app.db import ensure_indexes
from app.menu.router import router as menu_router
from app.delivery_boys.router import router as delivery_boys_router
from app.labels.router import router as labels_router

app = FastAPI(title="WhatsApp ERP - CRM Backend")


@app.on_event("startup")
async def on_startup():
    await ensure_indexes()


@app.get("/health")
async def health():
    return {"status": "ok"}


# 🚀 Add one line per module as you build them:
app.include_router(menu_router)
app.include_router(delivery_boys_router)
app.include_router(labels_router)
# app.include_router(contacts_router)
# app.include_router(campaigns_router)