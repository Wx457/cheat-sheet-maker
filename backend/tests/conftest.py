import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from clerk_backend_api.security.types import (  # noqa: E402
    AuthErrorReason,
    AuthStatus,
    RequestState,
)

from app.core import auth as auth_module  # noqa: E402
from app.core.config import settings  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "real_auth: 不替换 Clerk 验签，测试 app.core.auth 的真实行为"
    )


def bearer(user_id: str) -> dict:
    """测试用请求头：fake_clerk 把 `Bearer test:<user_id>` 解析为已登录的 user_id。"""
    return {"Authorization": f"Bearer test:{user_id}"}


@pytest.fixture(autouse=True)
def fake_clerk(request, monkeypatch):
    """只替换 Clerk 的验签调用：get_current_user_id 依赖本身照常执行（含 401 分支）。"""
    if request.node.get_closest_marker("real_auth"):
        return

    async def fake_authenticate(req, options):
        token = req.headers.get("Authorization", "").removeprefix("Bearer ")
        if not token.startswith("test:"):
            return RequestState(
                status=AuthStatus.SIGNED_OUT, reason=AuthErrorReason.SESSION_TOKEN_MISSING
            )
        return RequestState(
            status=AuthStatus.SIGNED_IN, token=token, payload={"sub": token[len("test:") :]}
        )

    monkeypatch.setattr(settings, "CLERK_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setattr(auth_module, "authenticate_request_async", fake_authenticate)
