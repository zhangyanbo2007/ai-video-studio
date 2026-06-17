"""
API 测试 — 启动服务后运行
"""

import sys
import json
import httpx

BASE = "http://localhost:8879"


def test_health():
    r = httpx.get(f"{BASE}/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    print("✅ /api/health")


def test_web_ui():
    r = httpx.get(f"{BASE}/")
    assert r.status_code == 200
    assert "AI" in r.text
    print("✅ / (Web UI)")


def test_register():
    r = httpx.post(f"{BASE}/api/user/register", json={"uid": ""})
    assert r.status_code == 200
    data = r.json()
    assert "uid" in data
    assert data["credits"] == 3
    assert data["is_new"] == True
    uid = data["uid"]

    # 第二次用同一 uid 应该返回 is_new=False
    r2 = httpx.post(f"{BASE}/api/user/register", json={"uid": uid})
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["is_new"] == False
    print(f"✅ /api/user/register (uid={uid[:12]}...)")


def test_plans():
    r = httpx.get(f"{BASE}/api/pay/plans")
    assert r.status_code == 200
    plans = r.json()["plans"]
    assert len(plans) >= 4
    print(f"✅ /api/pay/plans ({len(plans)} plans)")


def test_pay_status():
    r = httpx.get(f"{BASE}/api/pay/status", headers={"X-User-Id": ""})
    assert r.status_code == 200
    assert r.json()["credits"] == 0
    print("✅ /api/pay/status")


def test_redeem_invalid_code():
    r = httpx.post(f"{BASE}/api/pay/redeem", json={"uid": "test", "code": "INVALID"})
    # 应该返回 400（用户不存在）或 404
    assert r.status_code in (400, 404)
    print("✅ /api/pay/redeem (invalid code rejected)")


def test_upload():
    import io
    # 创建一个测试图片
    from PIL import Image
    img = Image.new("RGB", (100, 100), color="red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)

    r = httpx.post(
        f"{BASE}/api/upload",
        files={"file": ("test.jpg", buf, "image/jpeg")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "image"
    assert data["url"].startswith("/uploads/")
    print(f"✅ /api/upload → {data['url']}")


def test_models():
    # 需要 API Key（内部接口不需要）
    r = httpx.get(f"{BASE}/api/v1/models", headers={"X-API-Key": "invalid"})
    assert r.status_code == 401
    print("✅ /api/v1/models (auth required)")


if __name__ == "__main__":
    print(f"Testing API at {BASE}...")
    print()

    tests = [
        test_health,
        test_web_ui,
        test_register,
        test_plans,
        test_pay_status,
        test_redeem_invalid_code,
        test_upload,
        test_models,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"❌ {t.__name__}: {e}")
            failed += 1

    print()
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
