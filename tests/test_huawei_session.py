"""Session-handling tests for FusionSolar, at the aiohttp boundary.

The rest of the suite mocks `_request` away, which is exactly where the session
lives, so these drive the real thing against a fake session.
"""

import asyncio
import json
from typing import Any, Self

import aiohttp
import pytest

from custom_components.sunweg.huawei.api import (
    _KEEP_ALIVE_EVERY,
    FusionSolarClient,
)

KEEP_ALIVE = "/rest/dpcloud/auth/v1/keep-alive"
VALIDATE = "/rest/dp/uidm/unisso/v1/validate-user"
DETAIL = "/rest/pvms/web/station/v1/overview/station-detail"

LOGIN_OK = json.dumps(
    {"code": 0, "payload": {"redirectURL": "/rest/dp/uidm/auth/v1/on-sso"}}
)
TOKEN_OK = json.dumps({"code": 0, "payload": "c-token"})

# What the portal answers with once the session has lapsed: the login page,
# with HTTP 200 and not a scrap of JSON in it.
LOGIN_PAGE = "<!DOCTYPE html><html><body>login</body></html>"


class _FakeResponse:
    """Just enough of aiohttp's response to satisfy the client."""

    def __init__(self, body: str, status: int = 200) -> None:
        self.status = status
        self._body = body

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise aiohttp.ClientResponseError(None, (), status=self.status)

    async def json(self, content_type: str | None = None) -> Any:
        return json.loads(self._body)

    async def read(self) -> bytes:
        return self._body.encode()


class _FakeSession:
    """Records every call and answers from a handler keyed on the path."""

    def __init__(self, handler) -> None:
        self._handler = handler
        self.paths: list[str] = []

    def _call(self, method: str, url: str, **kwargs: Any) -> _FakeResponse:
        path = url.split("huawei.com", 1)[-1]
        self.paths.append(path)
        return self._handler(method, path, kwargs)

    def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        return self._call("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        return self._call("POST", url, **kwargs)

    def request(self, method: str, url: str, **kwargs: Any) -> _FakeResponse:
        return self._call(method, url, **kwargs)


def _default(method: str, path: str, kwargs: Any) -> _FakeResponse:
    if VALIDATE in path:
        return _FakeResponse(LOGIN_OK)
    if KEEP_ALIVE in path:
        return _FakeResponse(TOKEN_OK)
    return _FakeResponse(json.dumps({"data": {"dn": "NE=1", "name": "Plant"}}))


@pytest.fixture
def client_factory():
    """Build a client over a fake session, returning both."""

    def _build(handler=_default):
        session = _FakeSession(handler)
        return FusionSolarClient(session, "https://x.huawei.com", "u", "p"), session

    return _build


async def test_heartbeat_holds_the_session_open(client_factory) -> None:
    """Reading data does not renew the session; only the heartbeat does.

    Without it the session lapses after about half an hour and the fast poll
    dies mid-morning, which is exactly what this is here to prevent.
    """
    client, session = client_factory()
    await client.async_get_plant("NE=1")
    assert session.paths.count(KEEP_ALIVE) == 1  # the one login makes

    # A burst of polling inside the window must not add heartbeats...
    for _ in range(5):
        await client.async_get_plant("NE=1")
    assert session.paths.count(KEEP_ALIVE) == 1

    # ...but once the window has passed, the next poll carries one.
    client._last_keep_alive -= _KEEP_ALIVE_EVERY + 1
    await client.async_get_plant("NE=1")
    assert session.paths.count(KEEP_ALIVE) == 2


async def test_parallel_polls_fire_one_heartbeat(client_factory) -> None:
    """Plants are fetched together, so the stamp is taken before the call."""
    client, session = client_factory()
    await client.async_get_plant("NE=1")
    client._last_keep_alive -= _KEEP_ALIVE_EVERY + 1

    await asyncio.gather(*(client.async_get_plant(f"NE={i}") for i in range(4)))
    assert session.paths.count(KEEP_ALIVE) == 2


async def test_lapsed_session_logs_back_in(client_factory) -> None:
    """The login page comes back as HTTP 200 with no JSON; that means dead."""
    state = {"dead": False, "logins": 0}

    def handler(method: str, path: str, kwargs: Any) -> _FakeResponse:
        if VALIDATE in path:
            state["logins"] += 1
            state["dead"] = False
            return _FakeResponse(LOGIN_OK)
        if KEEP_ALIVE in path:
            return _FakeResponse(TOKEN_OK)
        if state["dead"]:
            return _FakeResponse(LOGIN_PAGE)
        return _FakeResponse(json.dumps({"data": {"dn": "NE=1", "name": "Plant"}}))

    client, _ = client_factory(handler)
    await client.async_get_plant("NE=1")
    assert state["logins"] == 1

    # The session dies between polls; the next one recovers on its own.
    state["dead"] = True
    plant = await client.async_get_plant("NE=1")
    assert state["logins"] == 2
    assert plant.name == "Plant"


async def test_rotated_token_is_picked_up(client_factory) -> None:
    """The heartbeat hands back the CSRF token, and it can change."""
    tokens = iter(["c-first", "c-second"])

    def handler(method: str, path: str, kwargs: Any) -> _FakeResponse:
        if KEEP_ALIVE in path:
            return _FakeResponse(json.dumps({"code": 0, "payload": next(tokens)}))
        return _default(method, path, kwargs)

    client, _ = client_factory(handler)
    await client.async_get_plant("NE=1")
    assert client._headers()["roarand"] == "c-first"

    client._last_keep_alive -= _KEEP_ALIVE_EVERY + 1
    await client.async_get_plant("NE=1")
    assert client._headers()["roarand"] == "c-second"
