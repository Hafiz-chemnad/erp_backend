from datetime import datetime, timedelta, timezone
from collections import defaultdict
from bson import ObjectId
import uuid

from app.insights.llm_client import ask_llm

# Orders that count as "real" completed business for revenue/analytics purposes.
# Rejected/cancelled orders are excluded everywhere in this module.
_COMPLETED_STATUSES = ("completed",)
_EXCLUDE_STATUSES = ("rejected",)


def _since(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


async def get_analytics_snapshot(db, restaurant_id: str, period_days: int = 30) -> dict:
    rid = ObjectId(restaurant_id)
    cutoff = _since(period_days)
    cursor = db.orders.find({
        "restaurantId": rid,
        "createdAt": {"$gte": cutoff},
        "paymentStatus": {"$nin": list(_EXCLUDE_STATUSES)},
    })
    orders = await cursor.to_list(length=None)

    total_revenue = 0.0
    item_stats: dict[str, dict] = defaultdict(lambda: {"qty": 0, "revenue": 0.0})
    revenue_by_mode: dict[str, float] = defaultdict(float)
    customer_order_count: dict[str, int] = defaultdict(int)

    for o in orders:
        amount = float(o.get("totalAmount") or 0)
        total_revenue += amount
        mode = o.get("orderMode") or ("whatsapp_delivery" if o.get("orderType") == "DELIVERY" else "whatsapp_takeaway")
        revenue_by_mode[mode] += amount

        customer = o.get("customerNumber")
        if customer:
            customer_order_count[customer] += 1

        for item in (o.get("items") or []):
            name = item.get("name", "Unknown")
            qty = int(item.get("qty") or 0)
            price = float(item.get("price") or 0)
            item_stats[name]["qty"] += qty
            item_stats[name]["revenue"] += qty * price

    total_orders = len(orders)
    avg_order_value = (total_revenue / total_orders) if total_orders else 0.0

    top_items = sorted(
        [{"name": n, "qty": s["qty"], "revenue": round(s["revenue"], 2)} for n, s in item_stats.items()],
        key=lambda x: x["revenue"],
        reverse=True,
    )[:10]

    # New vs repeat: based on whether this customer has any order *before* the window started.
    new_customers = 0
    repeat_customers = 0
    for customer in customer_order_count:
        earlier = await db.orders.count_documents({
            "restaurantId": rid,
            "customerNumber": customer,
            "createdAt": {"$lt": cutoff},
            "paymentStatus": {"$nin": list(_EXCLUDE_STATUSES)},
        })
        if earlier > 0:
            repeat_customers += 1
        else:
            new_customers += 1

    return {
        "periodDays": period_days,
        "totalRevenue": round(total_revenue, 2),
        "totalOrders": total_orders,
        "avgOrderValue": round(avg_order_value, 2),
        "topItems": top_items,
        "revenueByMode": {k: round(v, 2) for k, v in revenue_by_mode.items()},
        "newCustomers": new_customers,
        "repeatCustomers": repeat_customers,
    }


async def get_churn_candidates(db, restaurant_id: str, inactive_days: int = 14, lookback_days: int = 120) -> list[dict]:
    """Customers who ordered before but have gone quiet for `inactive_days`+."""
    rid = ObjectId(restaurant_id)
    lookback_cutoff = _since(lookback_days)
    inactivity_cutoff = _since(inactive_days)

    pipeline = [
        {"$match": {
            "restaurantId": rid,
            "customerNumber": {"$ne": None},
            "createdAt": {"$gte": lookback_cutoff},
            "paymentStatus": {"$nin": list(_EXCLUDE_STATUSES)},
        }},
        {"$sort": {"createdAt": -1}},
        {"$group": {
            "_id": "$customerNumber",
            "lastOrderAt": {"$first": "$createdAt"},
            "lastItems": {"$first": "$items"},
            "customerName": {"$first": "$customerName"},
            "totalOrdersPlaced": {"$sum": 1},
        }},
        {"$match": {"lastOrderAt": {"$lt": inactivity_cutoff}}},
        {"$sort": {"lastOrderAt": -1}},
        {"$limit": 50},
    ]
    results = await db.orders.aggregate(pipeline).to_list(length=None)

    now = datetime.now(timezone.utc)
    candidates = []
    for r in results:
        last_order_at = r["lastOrderAt"]
        if last_order_at.tzinfo is None:
            last_order_at = last_order_at.replace(tzinfo=timezone.utc)
        days_ago = (now - last_order_at).days
        last_item_name = None
        if r.get("lastItems"):
            last_item_name = r["lastItems"][0].get("name")
        candidates.append({
            "customerNumber": r["_id"],
            "customerName": r.get("customerName"),
            "lastOrderDaysAgo": days_ago,
            "totalOrdersPlaced": r["totalOrdersPlaced"],
            "lastOrderedItem": last_item_name,
        })
    return candidates


async def get_upsell_suggestions(db, restaurant_id: str) -> list[dict]:
    """Rule-based detection of actionable patterns, with LLM-written message copy
    when available (falls back to a plain template otherwise)."""
    suggestions = []

    # 1) Churn win-back suggestion
    churners = await get_churn_candidates(db, restaurant_id, inactive_days=14, lookback_days=120)
    if churners:
        numbers = [c["customerNumber"] for c in churners[:20]]
        restaurant = await db.restaurants.find_one({"_id": ObjectId(restaurant_id)})
        rname = (restaurant or {}).get("name", "us")
        used_llm = False
        message = f"Hi! We miss you at {rname} 🍽️ It's been a while since your last order — come back and enjoy 10% off your next order with code WELCOME10!"
        llm_text = await ask_llm(
            "You write short, warm WhatsApp win-back messages for a restaurant's quiet customers. "
            "Keep it under 300 characters, friendly, include a small incentive, no markdown.",
            f"Restaurant name: {rname}. Write one win-back WhatsApp message for customers who haven't ordered in 2+ weeks.",
        )
        if llm_text:
            message = llm_text
            used_llm = True
        suggestions.append({
            "suggestionId": str(uuid.uuid4()),
            "title": f"{len(churners)} customers have gone quiet",
            "description": f"{len(churners)} customers haven't ordered in 14+ days. Send a win-back message to bring them back.",
            "suggestedMessage": message,
            "customerNumbers": numbers,
            "customerCount": len(churners),
            "usedLlm": used_llm,
        })

    # 2) Top-seller cross-sell suggestion (based on last 30 days)
    snapshot = await get_analytics_snapshot(db, restaurant_id, period_days=30)
    if snapshot["topItems"]:
        top_item = snapshot["topItems"][0]
        # customers who ordered in the last 30 days but NOT this top item — good cross-sell target
        recent_customers_cursor = db.orders.find({
            "restaurantId": ObjectId(restaurant_id),
            "createdAt": {"$gte": _since(30)},
            "customerNumber": {"$ne": None},
            "paymentStatus": {"$nin": list(_EXCLUDE_STATUSES)},
        })
        recent_orders = await recent_customers_cursor.to_list(length=None)
        all_customers = set()
        bought_top_item = set()
        for o in recent_orders:
            cust = o.get("customerNumber")
            if not cust:
                continue
            all_customers.add(cust)
            if any(i.get("name") == top_item["name"] for i in (o.get("items") or [])):
                bought_top_item.add(cust)
        target_customers = list(all_customers - bought_top_item)

        if target_customers:
            used_llm = False
            message = f"Have you tried our {top_item['name']}? It's one of our most-loved dishes — give it a try on your next order!"
            llm_text = await ask_llm(
                "You write short, appetizing WhatsApp cross-sell messages for a restaurant. "
                "Keep it under 300 characters, friendly, no markdown.",
                f"Write one message suggesting customers try our best-selling item: {top_item['name']}.",
            )
            if llm_text:
                message = llm_text
                used_llm = True
            suggestions.append({
                "suggestionId": str(uuid.uuid4()),
                "title": f"Promote your bestseller: {top_item['name']}",
                "description": f"{len(target_customers)} recent customers haven't tried {top_item['name']} yet — your top seller this month.",
                "suggestedMessage": message,
                "customerNumbers": target_customers[:50],
                "customerCount": len(target_customers),
                "usedLlm": used_llm,
            })

    return suggestions


async def ask_question(db, restaurant_id: str, question: str) -> dict:
    """'Ask Your Data' — pulls a lightweight analytics context and asks the LLM
    to answer in plain English. Falls back to the raw snapshot if no LLM is configured."""
    snapshot = await get_analytics_snapshot(db, restaurant_id, period_days=30)
    churners = await get_churn_candidates(db, restaurant_id, inactive_days=14)

    context = (
        f"Last 30 days: revenue ₹{snapshot['totalRevenue']}, {snapshot['totalOrders']} orders, "
        f"avg order value ₹{snapshot['avgOrderValue']}. "
        f"Top items: {', '.join(i['name'] + ' (' + str(i['qty']) + ' sold)' for i in snapshot['topItems'][:5])}. "
        f"Revenue by order mode: {snapshot['revenueByMode']}. "
        f"New customers: {snapshot['newCustomers']}, repeat customers: {snapshot['repeatCustomers']}. "
        f"Customers gone quiet (14+ days inactive): {len(churners)}."
    )

    answer = await ask_llm(
        "You are a helpful restaurant business analyst. Answer the owner's question using ONLY the "
        "data context given. Be concise (2-4 sentences), use plain language, no markdown, include numbers "
        "where relevant. If the data doesn't answer the question, say so honestly.",
        f"Data context: {context}\n\nQuestion: {question}",
    )

    if answer:
        return {"answer": answer, "usedLlm": True}

    # Fallback: no LLM configured, just hand back the raw numbers.
    fallback = (
        f"Here's what I have for the last 30 days — Revenue: ₹{snapshot['totalRevenue']}, "
        f"Orders: {snapshot['totalOrders']}, Avg order value: ₹{snapshot['avgOrderValue']}, "
        f"Top item: {snapshot['topItems'][0]['name'] if snapshot['topItems'] else 'N/A'}, "
        f"Customers gone quiet: {len(churners)}. "
        f"(AI-written answers aren't available right now — add a free Groq or Gemini API key to enable them.)"
    )
    return {"answer": fallback, "usedLlm": False}
