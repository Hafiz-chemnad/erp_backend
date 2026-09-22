"""
Google Sheet sync — restaurant owners maintain menu in a spreadsheet,
we pull it in and push to Meta catalog. Uses a service account
(GOOGLE_SERVICE_ACCOUNT_JSON in config) so no per-restaurant OAuth needed,
as long as the restaurant shares their sheet with the service account email.
"""

import json
import gspread
from google.oauth2.service_account import Credentials
from app.core.config import settings

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def _get_client():
    creds_dict = json.loads(settings.GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)


def fetch_sheet_items(sheet_id: str) -> list[dict]:
    """
    Expects columns: retailer_id | name | price | availability | image_url
    Returns list of dicts matching CatalogItem shape.
    """
    client = _get_client()
    sheet = client.open_by_key(sheet_id).sheet1
    rows = sheet.get_all_records()

    items = []
    for row in rows:
        items.append({
            "retailer_id": str(row.get("retailer_id", "")),
            "name": row.get("name", ""),
            "price": float(row.get("price", 0)),
            "availability": row.get("availability", "in stock"),
            "image_url": row.get("image_url", ""),
        })
    return items