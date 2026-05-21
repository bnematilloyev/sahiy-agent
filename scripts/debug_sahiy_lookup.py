#!/usr/bin/env python3
"""Debug Sahiy API: phone -> user_id and order endpoints (raw JSON).

Usage:
  python scripts/debug_sahiy_lookup.py 998933741511
  python scripts/debug_sahiy_lookup.py +998933741511
  python scripts/debug_sahiy_lookup.py DG60353352
  python scripts/debug_sahiy_lookup.py Botir-test-101
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.infrastructure.sahiy_api.auth import ServiceUserAuth
from app.infrastructure.sahiy_api.client import SahiyApiClient
from app.domain.order_refs import extract_track, normalize_phone
from app.infrastructure.sahiy_api.customer import CustomerApi


def _short(data: object, limit: int = 1200) -> str:
    text = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    if len(text) > limit:
        return text[:limit] + "\n... (truncated)"
    return text


async def main() -> None:
    if len(sys.argv) < 2:
        print("Telefon yoki track: python scripts/debug_sahiy_lookup.py 998901234567")
        sys.exit(1)

    raw = sys.argv[1].strip()
    track = extract_track(raw)
    phone = normalize_phone(raw) if not track else None
    settings = get_settings()

    if not settings.has_service_user:
        print("Xato: .env da SAHIY_API_BASE_URL, SERVICE_USER_PHONE, SERVICE_USER_PASSWORD to'ldiring.")
        sys.exit(1)

    print(f"Base URL: {settings.sahiy_api_base_url.rstrip('/')}")
    print(f"Input:    {raw}")
    print(f"Track:    {track}")
    print(f"Phone:    {phone}\n")

    auth = ServiceUserAuth(settings)
    client = SahiyApiClient(auth)
    api = CustomerApi(client)

    print("==> 1) Login")
    token = await auth.get_access_token()
    print(f"    Token: {token[:20]}...\n")

    user_id: int | None = None
    if track:
        print(f"==> 2) GET /api/v2/admin/delivery/orders/tracking/{track}")
        tracking = await api.get_tracking(track)
        print(f"    Response:\n{_short(tracking)}\n")
        user_id = await api.resolve_user_id_for_track(track, tracking)
        print(f"    Resolved user_id: {user_id}\n")
    elif phone:
        search_path = "/api/v2/admin/delivery/orders/search"
        search_params = {"search_by": "phone", "query": phone}
        print(f"==> 2) GET {search_path}")
        print(f"    params: {search_params}")
        search_body = await client.get_json(search_path, params=search_params)
        user_id = await api.find_user_id_by_phone(phone)
        print(f"    Parsed user_id: {user_id}")
        print(f"    Response:\n{_short(search_body)}\n")
    else:
        print("Track yoki telefon aniqlanmadi.")
        sys.exit(1)

    if user_id is None:
        print("user_id topilmadi — qolgan endpointlar o'tkazib yuborildi.")
        return

    endpoints = [
        (f"/api/v2/admin/delivery/orders/user/{user_id}", {}),
        (f"/api/client/dashboard/show/{user_id}", {}),
        ("/api/custom/orders", {"user": user_id}),
        (
            "/api/v2/admin/delivery/orders/analytics/daigou",
            {"user_id": user_id, "page": 1, "size": 5},
        ),
        (
            "/api/v2/admin/delivery/orders/filter",
            None,
        ),
    ]

    idx = 3
    for path, params in endpoints:
        print(f"==> {idx}) GET {path}")
        if params is not None:
            print(f"    params: {params}")
            body = await client.get_json(path, params=params)
        else:
            body = await client.get_json(
                path,
                params_list=[
                    ("user_id", user_id),
                    ("delivered", "false"),
                    ("with[]", "user"),
                    ("with[]", "location.branch"),
                ],
            )
        if isinstance(body, dict):
            keys = list(body.keys())
            print(f"    top-level keys: {keys}")
        print(f"    Response:\n{_short(body)}\n")
        idx += 1

    print("==> Snapshot (agent logic)")
    snap = await api.build_snapshot(user_id, phone=phone)
    print(
        json.dumps(
            {
                "user_id": snap.user_id,
                "delivery": len(snap.delivery_orders),
                "dashboard": len(snap.dashboard_orders),
                "jiyun": len(snap.jiyun_orders),
                "daigou": len(snap.daigou_orders),
                "unpicked": len(snap.unpicked_delivery),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
