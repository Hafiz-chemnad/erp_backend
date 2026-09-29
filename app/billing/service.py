import random
from datetime import datetime, timezone
from bson import ObjectId
from app.billing.schemas import POSOrderIn, BillLineOut
from app.core.phone import normalize_phone

ORDERS_COLLECTION = "orders"
PENDING_LOCATION_COLLECTION = "pending_location_requests"

# Statuses that mean "this bill is still running / not yet paid" — anything
# else (completed/rejected) is treated as closed, so a new order for the
# same table/counter-ticket starts fresh instead of merging into a settled bill.
_OPEN_STATUSES = {"pending", "preparing", "accepted", "ready", "awaiting_location"}


def _generate_order_id() -> str:
    return f"POS-{random.randint(100000, 999999)}-{random.randint(100, 999)}"


def _generate_display_id() -> str:
    return f"C{random.randint(1000, 9999)}"


def _serialize(doc: dict) -> dict:
    if "_id" in doc:
        doc["_id"] = str(doc["_id"])
    if "restaurantId" in doc and isinstance(doc["restaurantId"], ObjectId):
        doc["restaurantId"] = str(doc["restaurantId"])
    if isinstance(doc.get("createdAt"), datetime):
        doc["createdAt"] = doc["createdAt"].isoformat()
    if isinstance(doc.get("updatedAt"), datetime):
        doc["updatedAt"] = doc["updatedAt"].isoformat()
    return doc


async def _resolve_items(db, restaurant_id: str, items_in: list) -> list[BillLineOut]:
    """Never trust client-sent price/name — look every item up fresh from
    menu_items so a stale cart or tampered request can't under-charge."""
    resolved: list[BillLineOut] = []
    for line in items_in:
        doc = await db.menu_items.find_one({
            "restaurant_id": restaurant_id,
            "retailer_id": line.retailerId,
        })
        if not doc:
            continue
        qty = max(1, line.qty)
        price = float(doc["price"])
        resolved.append(BillLineOut(
            retailerId=line.retailerId,
            name=doc["name"],
            price=price,
            qty=qty,
            note=line.note,
            lineTotal=round(price * qty, 2),
        ))
    return resolved


def _merge_lines(existing: list[dict], new: list[BillLineOut]) -> list[dict]:
    by_id = {i["retailerId"]: dict(i) for i in existing}
    for line in new:
        if line.retailerId in by_id:
            by_id[line.retailerId]["qty"] += line.qty
            by_id[line.retailerId]["lineTotal"] = round(
                by_id[line.retailerId]["qty"] * by_id[line.retailerId]["price"], 2
            )
            if line.note:
                by_id[line.retailerId]["note"] = line.note
        else:
            by_id[line.retailerId] = line.model_dump()
    return list(by_id.values())


def _combine_raw_lines(a: list[dict], b: list[dict]) -> list[dict]:
    """Same merge as _merge_lines but for two already-saved item lists
    (used by table-merge, where both sides are plain dicts already)."""
    by_id = {i["retailerId"]: dict(i) for i in a}
    for line in b:
        if line["retailerId"] in by_id:
            by_id[line["retailerId"]]["qty"] += line["qty"]
            by_id[line["retailerId"]]["lineTotal"] = round(
                by_id[line["retailerId"]]["qty"] * by_id[line["retailerId"]]["price"], 2
            )
        else:
            by_id[line["retailerId"]] = dict(line)
    return list(by_id.values())


def _compute_totals(items: list[dict], discount_percent: float, discount_flat: float, tax_rate: float):
    subtotal = round(sum(i["lineTotal"] for i in items), 2)
    discount_amount = round(min(subtotal, (subtotal * discount_percent / 100) + discount_flat), 2)
    taxable = max(0.0, subtotal - discount_amount)
    tax_amount = round(taxable * tax_rate / 100, 2)
    total = round(taxable + tax_amount, 2)
    return subtotal, discount_amount, tax_amount, total


async def _find_open_table_order(db, restaurant_id: str, table_number: str) -> dict | None:
    return await db[ORDERS_COLLECTION].find_one({
        "restaurantId": ObjectId(restaurant_id),
        "source": "pos",
        "orderMode": "dine_in",
        "tableNumber": table_number,
        "paymentStatus": {"$in": list(_OPEN_STATUSES)},
    })


async def _find_open_order_by_id(db, restaurant_id: str, order_id: str) -> dict | None:
    """Generic open-order lookup by id — used for takeaway counter tickets
    and phone orders (pickup/delivery), which have no table number to key
    off, unlike dine-in."""
    return await db[ORDERS_COLLECTION].find_one({
        "restaurantId": ObjectId(restaurant_id),
        "source": "pos",
        "orderId": order_id,
        "paymentStatus": {"$in": list(_OPEN_STATUSES)},
    })


def _initial_status(order_mode: str) -> str:
    """Every mode starts unpaid — payment only happens at the explicit
    settle-payment step, never at creation."""
    if order_mode == "phone_delivery":
        return "awaiting_location"  # gated until the customer's WhatsApp pin arrives
    return "preparing" if order_mode in ("dine_in", "takeaway_counter") else "pending"


async def send_to_kitchen(db, restaurant_id: str, body: POSOrderIn) -> dict:
    """Persists the order and marks it in-progress. No payment is
    collected here for any mode — that only happens in settle_payment()."""
    restaurant = await db.restaurants.find_one({"_id": ObjectId(restaurant_id)})
    tax_rate = float(restaurant.get("gstRate", 0.0)) if restaurant else 0.0
    restaurant_name = restaurant.get("name", "") if restaurant else ""

    resolved_items = await _resolve_items(db, restaurant_id, body.items)
    now = datetime.now(timezone.utc)

    # Staff type numbers in every format ("98765 43210", "+91-98765..."). Store
    # the WhatsApp form (country code + digits, no "+") so that (a) order
    # notifications can actually be delivered and (b) the customer's location
    # pin — which Meta reports as msg["from"] — matches this order.
    customer_number = normalize_phone(body.customerNumber) or None

    # Dine-in bills with a table number accumulate onto one running order
    # until the table is closed — lets staff add a second round without
    # creating a duplicate bill. Takeaway counter tickets and phone orders
    # have no table number, so they're keyed off an explicit existingOrderId
    # (the chip the cashier selected) instead.
    existing = None
    if body.orderMode == "dine_in" and body.tableNumber:
        existing = await _find_open_table_order(db, restaurant_id, body.tableNumber)
    elif body.orderMode in ("takeaway_counter", "phone_pickup", "phone_delivery") and body.existingOrderId:
        existing = await _find_open_order_by_id(db, restaurant_id, body.existingOrderId)

    if existing:
        merged_items = _merge_lines(existing.get("items", []), resolved_items)
        subtotal, discount_amount, tax_amount, total = _compute_totals(
            merged_items, body.discountPercent, body.discountFlat, tax_rate
        )
        update_fields = {
            "items": merged_items,
            "subtotal": subtotal,
            "discountAmount": discount_amount,
            "taxRate": tax_rate,
            "taxAmount": tax_amount,
            "totalAmount": total,
            "updatedAt": now,
        }
        if body.additionalNotes:
            update_fields["additionalNotes"] = body.additionalNotes
        await db[ORDERS_COLLECTION].update_one({"_id": existing["_id"]}, {"$set": update_fields})
        saved = await db[ORDERS_COLLECTION].find_one({"_id": existing["_id"]})
        return _serialize(saved)

    subtotal, discount_amount, tax_amount, total = _compute_totals(
        [i.model_dump() for i in resolved_items], body.discountPercent, body.discountFlat, tax_rate
    )
    status = _initial_status(body.orderMode)
    order_doc = {
        "orderId": _generate_order_id(),
        "displayId": _generate_display_id(),
        "source": "pos",
        "orderMode": body.orderMode,
        "orderType": "DELIVERY" if body.orderMode == "phone_delivery" else "TAKEAWAY",
        "tableNumber": body.tableNumber,
        "customerName": body.customerName,
        "customerNumber": customer_number,
        "items": [i.model_dump() for i in resolved_items],
        "subtotal": subtotal,
        "discountAmount": discount_amount,
        "taxRate": tax_rate,
        "taxAmount": tax_amount,
        "totalAmount": total,
        "paymentStatus": status,
        "paymentMethod": None,
        "billedBy": body.billedBy,
        "additionalNotes": body.additionalNotes,
        "restaurantId": ObjectId(restaurant_id),
        "restaurantName": restaurant_name,
        "createdAt": now,
        "updatedAt": now,
    }
    result = await db[ORDERS_COLLECTION].insert_one(order_doc)
    order_doc["_id"] = result.inserted_id

    if body.orderMode == "phone_delivery" and customer_number:
        await db[PENDING_LOCATION_COLLECTION].update_one(
            {"restaurantId": ObjectId(restaurant_id), "customerNumber": customer_number},
            {"$set": {
                "restaurantId": ObjectId(restaurant_id),
                "customerNumber": customer_number,
                "orderId": order_doc["orderId"],
                "requestedAt": now,
            }},
            upsert=True,
        )

    return _serialize(order_doc)


async def settle_payment_by_table(db, restaurant_id: str, table_number: str, payment_method: str) -> dict | None:
    """Convenience wrapper for the dine-in 'close table' endpoint, which
    identifies the bill by table rather than orderId."""
    existing = await _find_open_table_order(db, restaurant_id, table_number)
    if not existing:
        return None
    return await settle_payment(db, restaurant_id, existing["orderId"], payment_method)


async def edit_sent_items(db, restaurant_id: str, order_id: str, items_in: list, discount_percent: float, discount_flat: float) -> dict | None:
    """Replaces the full item list on an already-sent (unsettled) order —
    covers removing an item, changing a quantity, or re-adding something
    that was dropped. Only allowed while the order is still open; settled
    orders are financial records and shouldn't be edited after the fact."""
    existing = await db[ORDERS_COLLECTION].find_one({
        "restaurantId": ObjectId(restaurant_id),
        "orderId": order_id,
    })
    if not existing:
        return None
    if existing.get("paymentStatus") not in _OPEN_STATUSES:
        return None  # already settled/rejected — edits aren't allowed past this point

    restaurant = await db.restaurants.find_one({"_id": ObjectId(restaurant_id)})
    tax_rate = float(restaurant.get("gstRate", 0.0)) if restaurant else 0.0

    resolved_items = await _resolve_items(db, restaurant_id, [i for i in items_in if i.qty > 0])
    new_lines = [i.model_dump() for i in resolved_items]
    subtotal, discount_amount, tax_amount, total = _compute_totals(new_lines, discount_percent, discount_flat, tax_rate)

    await db[ORDERS_COLLECTION].update_one(
        {"_id": existing["_id"]},
        {"$set": {
            "items": new_lines,
            "subtotal": subtotal,
            "discountAmount": discount_amount,
            "taxAmount": tax_amount,
            "totalAmount": total,
            "updatedAt": datetime.now(timezone.utc),
        }},
    )
    saved = await db[ORDERS_COLLECTION].find_one({"_id": existing["_id"]})
    return _serialize(saved)


async def settle_payment(db, restaurant_id: str, order_id: str, payment_method: str) -> dict | None:
    """Closes out an already-sent order once the customer actually pays —
    the only place paymentStatus ever becomes 'completed'."""
    existing = await db[ORDERS_COLLECTION].find_one({
        "restaurantId": ObjectId(restaurant_id),
        "orderId": order_id,
    })
    if not existing:
        return None
    await db[ORDERS_COLLECTION].update_one(
        {"_id": existing["_id"]},
        {"$set": {
            "paymentStatus": "completed",
            "paymentMethod": payment_method,
            "updatedAt": datetime.now(timezone.utc),
        }},
    )
    saved = await db[ORDERS_COLLECTION].find_one({"_id": existing["_id"]})
    return _serialize(saved)


async def get_open_tables(db, restaurant_id: str) -> list[dict]:
    cursor = db[ORDERS_COLLECTION].find({
        "restaurantId": ObjectId(restaurant_id),
        "source": "pos",
        "orderMode": "dine_in",
        "tableNumber": {"$ne": None},
        "paymentStatus": {"$in": list(_OPEN_STATUSES)},
    })
    out = []
    async for doc in cursor:
        out.append({
            "tableNumber": doc["tableNumber"],
            "orderId": doc["orderId"],
            "displayId": doc.get("displayId", doc["orderId"]),
            "totalAmount": doc.get("totalAmount", 0.0),
            "itemCount": sum(i.get("qty", 1) for i in doc.get("items", [])),
            "createdAt": doc["createdAt"].isoformat() if isinstance(doc["createdAt"], datetime) else doc["createdAt"],
        })
    return out


async def get_open_orders_by_mode(db, restaurant_id: str, order_mode: str) -> list[dict]:
    """Open (unsettled) orders for a given mode — used for the counter-ticket
    picker (takeaway_counter) and the phone-order picker (phone_pickup /
    phone_delivery), so staff can reopen an order they created earlier in
    the shift instead of losing track of it once they navigate away."""
    cursor = db[ORDERS_COLLECTION].find({
        "restaurantId": ObjectId(restaurant_id),
        "source": "pos",
        "orderMode": order_mode,
        "paymentStatus": {"$in": list(_OPEN_STATUSES)},
    })
    out = []
    async for doc in cursor:
        out.append({
            "orderId": doc["orderId"],
            "displayId": doc.get("displayId", doc["orderId"]),
            "customerName": doc.get("customerName"),
            "customerNumber": doc.get("customerNumber"),
            "paymentStatus": doc.get("paymentStatus"),
            "totalAmount": doc.get("totalAmount", 0.0),
            "itemCount": sum(i.get("qty", 1) for i in doc.get("items", [])),
            "createdAt": doc["createdAt"].isoformat() if isinstance(doc["createdAt"], datetime) else doc["createdAt"],
        })
    return out


async def get_open_phone_orders(db, restaurant_id: str) -> list[dict]:
    cursor = db[ORDERS_COLLECTION].find({
        "restaurantId": ObjectId(restaurant_id),
        "source": "pos",
        "orderMode": {"$in": ["phone_pickup", "phone_delivery"]},
        "paymentStatus": {"$in": list(_OPEN_STATUSES)},
    }).sort("createdAt", -1)
    out = []
    async for doc in cursor:
        out.append({
            "orderId": doc["orderId"],
            "displayId": doc.get("displayId", doc["orderId"]),
            "orderMode": doc["orderMode"],
            "customerName": doc.get("customerName"),
            "customerNumber": doc.get("customerNumber"),
            "paymentStatus": doc.get("paymentStatus"),
            "totalAmount": doc.get("totalAmount", 0.0),
            "itemCount": sum(i.get("qty", 1) for i in doc.get("items", [])),
            "createdAt": doc["createdAt"].isoformat() if isinstance(doc["createdAt"], datetime) else doc["createdAt"],
        })
    return out


async def get_open_phone_orders(db, restaurant_id: str) -> list[dict]:
    """Both phone_pickup and phone_delivery in one list — staff think in
    terms of 'which phone order is this?', not which sub-type, so the UI
    shows them together and distinguishes them by orderMode/status."""
    cursor = db[ORDERS_COLLECTION].find({
        "restaurantId": ObjectId(restaurant_id),
        "source": "pos",
        "orderMode": {"$in": ["phone_pickup", "phone_delivery"]},
        "paymentStatus": {"$in": list(_OPEN_STATUSES)},
    })
    out = []
    async for doc in cursor:
        out.append({
            "orderId": doc["orderId"],
            "displayId": doc.get("displayId", doc["orderId"]),
            "orderMode": doc.get("orderMode"),
            "paymentStatus": doc.get("paymentStatus"),
            "customerName": doc.get("customerName"),
            "customerNumber": doc.get("customerNumber"),
            "totalAmount": doc.get("totalAmount", 0.0),
            "itemCount": sum(i.get("qty", 1) for i in doc.get("items", [])),
            "hasLocation": doc.get("location") is not None,
            "createdAt": doc["createdAt"].isoformat() if isinstance(doc["createdAt"], datetime) else doc["createdAt"],
        })
    return out


async def get_open_counter_tickets(db, restaurant_id: str) -> list[dict]:
    return await get_open_orders_by_mode(db, restaurant_id, "takeaway_counter")


async def merge_tables(db, restaurant_id: str, source_table: str, target_table: str) -> dict | None:
    source = await _find_open_table_order(db, restaurant_id, source_table)
    target = await _find_open_table_order(db, restaurant_id, target_table)
    if not source or not target:
        return None

    restaurant = await db.restaurants.find_one({"_id": ObjectId(restaurant_id)})
    tax_rate = float(restaurant.get("gstRate", 0.0)) if restaurant else 0.0

    combined_items = _combine_raw_lines(target.get("items", []), source.get("items", []))
    subtotal, discount_amount, tax_amount, total = _compute_totals(combined_items, 0.0, 0.0, tax_rate)

    now = datetime.now(timezone.utc)
    await db[ORDERS_COLLECTION].update_one(
        {"_id": target["_id"]},
        {"$set": {
            "items": combined_items,
            "subtotal": subtotal,
            "discountAmount": discount_amount,
            "taxAmount": tax_amount,
            "totalAmount": total,
            "updatedAt": now,
        }},
    )
    # Source table's bill is now folded in — close it out (not "completed",
    # just closed/merged) so it stops showing up as its own open table.
    await db[ORDERS_COLLECTION].update_one(
        {"_id": source["_id"]},
        {"$set": {"paymentStatus": "merged", "mergedInto": target_table, "updatedAt": now}},
    )
    saved = await db[ORDERS_COLLECTION].find_one({"_id": target["_id"]})
    return _serialize(saved)


async def move_table(db, restaurant_id: str, table_number: str, new_table: str) -> dict | None:
    existing = await _find_open_table_order(db, restaurant_id, table_number)
    if not existing:
        return None
    # Guard: don't silently clobber a bill that's already running on the
    # destination table — merge should be used instead in that case.
    already_open = await _find_open_table_order(db, restaurant_id, new_table)
    if already_open:
        return None
    await db[ORDERS_COLLECTION].update_one(
        {"_id": existing["_id"]},
        {"$set": {"tableNumber": new_table, "updatedAt": datetime.now(timezone.utc)}},
    )
    saved = await db[ORDERS_COLLECTION].find_one({"_id": existing["_id"]})
    return _serialize(saved)


async def attach_location_and_confirm(db, restaurant_id: str, order_id: str, latitude: float, longitude: float, address: str | None = None) -> dict | None:
    """Called from the webhook once the customer's WhatsApp location pin
    arrives — flips awaiting_location -> pending and the order becomes
    identical to a normal WhatsApp delivery order from here on."""
    existing = await db[ORDERS_COLLECTION].find_one({
        "restaurantId": ObjectId(restaurant_id),
        "orderId": order_id,
    })
    if not existing:
        return None
    await db[ORDERS_COLLECTION].update_one(
        {"_id": existing["_id"]},
        {"$set": {
            "paymentStatus": "pending",
            # lat/lng — the same keys the bot flow saves and the Flutter app
            # reads. (This used to be latitude/longitude, so the app never saw
            # the pin and the Map / Assign buttons stayed disabled.)
            "location": {"lat": latitude, "lng": longitude, "address": address},
            "updatedAt": datetime.now(timezone.utc),
        }},
    )
    saved = await db[ORDERS_COLLECTION].find_one({"_id": existing["_id"]})
    return _serialize(saved)


async def find_pending_location_request(db, restaurant_id: str, customer_number: str) -> dict | None:
    return await db[PENDING_LOCATION_COLLECTION].find_one({
        "restaurantId": ObjectId(restaurant_id),
        "customerNumber": customer_number,
    })


async def clear_pending_location_request(db, restaurant_id: str, customer_number: str) -> None:
    await db[PENDING_LOCATION_COLLECTION].delete_one({
        "restaurantId": ObjectId(restaurant_id),
        "customerNumber": customer_number,
    })
