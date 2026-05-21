from __future__ import annotations

import pytest

from app.domain.order_refs import extract_phone, extract_track, normalize_phone
from app.infrastructure.sahiy_api.customer import CustomerApi, _first_user_id


def test_normalize_uz_phone():
    assert normalize_phone("+998 90 123 45 67") == "998901234567"
    assert normalize_phone("901234567") == "998901234567"


def test_extract_track_and_phone():
    assert extract_track("Buyurtmam ABC12345678 qayerda") == "ABC12345678"
    assert extract_phone("tel: +998901112233") == "998901112233"
    assert extract_phone("773402939631585 bu zakazim qayerda") is None
    assert extract_track("773402939631585 bu zakazim qayerda") == "773402939631585"
    assert extract_track("track raqam Botir-test-101") == "Botir-test-101"
    assert extract_track("Botir-test-101 bu chi") == "Botir-test-101"


def test_first_user_id_from_search_list():
    body = {"data": [{"user_id": 77, "track_number": "X1"}]}
    assert _first_user_id(body) == 77


class _FakeClient:
    def __init__(self, by_path: dict):
        self._by_path = by_path

    async def get_json(self, path, *, params=None, params_list=None):
        if path in self._by_path:
            return self._by_path[path]
        return None


@pytest.mark.asyncio
async def test_build_snapshot_parallel():
    client = _FakeClient(
        {
            "/api/v2/admin/delivery/orders/user/5": {"data": [{"status": 4}]},
            "/api/client/dashboard/show/5": {"orders": []},
            "/api/custom/orders": {"data": []},
            "/api/v2/admin/delivery/orders/analytics/daigou": {
                "data": {"data": [{"order_sn": "DG1", "status": 2}], "total": 1}
            },
            "/api/v2/admin/delivery/orders/filter": {
                "items": [{"status": 4, "track_number": "T1"}]
            },
        }
    )
    api = CustomerApi(client)  # type: ignore[arg-type]
    snap = await api.build_snapshot(5)
    assert snap.user_id == 5
    assert len(snap.delivery_orders) == 1
    assert snap.unpicked_delivery[0]["status_label"]


@pytest.mark.asyncio
async def test_invalid_tracking_payload_does_not_return_full_list():
    track = "773402939631585"

    class _TrackingClient(_FakeClient):
        async def get_json(self, path, *, params=None, params_list=None):
            if path.startswith("/api/v2/admin/delivery/orders/tracking/"):
                return {"status": 4, "user_id": 5, "express_num": "OTHER"}
            if path == "/api/v2/admin/delivery/orders/search":
                return {"data": [{"user_id": 99, "track_number": track}]}
            return await super().get_json(path, params=params, params_list=params_list)

    client = _TrackingClient(
        {
            "/api/v2/admin/delivery/orders/user/5": {"data": [{"express_num": "OTHER", "status": 4}]},
            "/api/client/dashboard/show/5": {"orders": []},
            "/api/custom/orders": {"data": []},
            "/api/v2/admin/delivery/orders/analytics/daigou": {"data": {"data": [], "total": 0}},
            "/api/v2/admin/delivery/orders/filter": {"items": []},
        }
    )
    api = CustomerApi(client)  # type: ignore[arg-type]
    result = await api.lookup(verified_user_id=5, query=f"{track} bu qayerda")
    assert isinstance(result, dict)
    assert result.get("error") == "ownership_mismatch"


@pytest.mark.asyncio
async def test_track_belongs_to_other_user():
    track = "773402939631585"

    class _SearchClient(_FakeClient):
        async def get_json(self, path, *, params=None, params_list=None):
            if path.startswith("/api/v2/admin/delivery/orders/tracking/"):
                return None
            if path == "/api/v2/admin/delivery/orders/search":
                return {"data": [{"user_id": 99, "track_number": track}]}
            return await super().get_json(path, params=params, params_list=params_list)

    client = _SearchClient(
        {
            "/api/v2/admin/delivery/orders/user/5": {"data": [{"express_num": "OTHER", "status": 4}]},
            "/api/client/dashboard/show/5": {"orders": []},
            "/api/custom/orders": {"data": []},
            "/api/v2/admin/delivery/orders/analytics/daigou": {"data": {"data": [], "total": 0}},
            "/api/v2/admin/delivery/orders/filter": {"items": []},
        }
    )
    api = CustomerApi(client)  # type: ignore[arg-type]
    result = await api.lookup(verified_user_id=5, query=f"{track} bu qayerda")
    assert isinstance(result, dict)
    assert result.get("error") == "ownership_mismatch"
    assert "tegishli emas" in result.get("message", "")
    assert track in result.get("message", "")
