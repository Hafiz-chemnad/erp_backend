from fastapi import FastAPI
from app.db import ensure_indexes
from app.menu.router import router as menu_router
from app.labels.router import router as labels_router
from app.contacts.router import router as contacts_router
from app.campaigns.router import router as campaigns_router 
from app.templates.router import router as templates_router
from app.webhooks.router import router as webhooks_router
from app.restaurants.router import router as restaurants_router
from app.delivery_auth.router import router as delivery_auth_router
from app.order_assignments.router import router as order_assignments_router
from app.delivery_boys.router import router as delivery_boys_router
from app.delivery_auth.login_router import login_router

app = FastAPI(title="WhatsApp ERP - CRM Backend")


@app.on_event("startup")
async def on_startup():
    await ensure_indexes()


@app.get("/health")
async def health():
    return {"status": "ok"}


# 🚀 Add one line per module as you build them:
app.include_router(menu_router)
app.include_router(labels_router)
app.include_router(contacts_router)
app.include_router(campaigns_router)                                  
app.include_router(templates_router)
app.include_router(webhooks_router)
app.include_router(restaurants_router)
app.include_router(delivery_auth_router)
app.include_router(order_assignments_router)
app.include_router(delivery_boys_router)
app.include_router(login_router)