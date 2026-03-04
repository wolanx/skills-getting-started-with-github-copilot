import copy
import uuid
from urllib.parse import quote

import pytest
import httpx

from src import app as app_module
from src.app import app


@pytest.fixture(autouse=True)
def activities_snapshot():
    """Arrange: snapshot global `activities` before each test and restore after."""
    original = copy.deepcopy(app_module.activities)
    yield
    # Restore state to avoid cross-test pollution
    app_module.activities.clear()
    app_module.activities.update(original)


@pytest.fixture
async def async_client():
    """Provide an AsyncClient bound to the ASGI app."""
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_get_activities_returns_structure(async_client):
    # Arrange: client provided

    # Act
    resp = await async_client.get("/activities")

    # Assert
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    # pick any activity and assert expected keys
    if data:
        name, details = next(iter(data.items()))
        assert "description" in details
        assert "schedule" in details
        assert "max_participants" in details
        assert "participants" in details and isinstance(details["participants"], list)


@pytest.mark.asyncio
async def test_root_redirects_to_index(async_client):
    # Arrange

    # Act
    resp = await async_client.get("/", allow_redirects=False)

    # Assert
    assert resp.status_code in (301, 302, 307)
    loc = resp.headers.get("location", "")
    assert loc.endswith("/static/index.html")


@pytest.mark.asyncio
async def test_signup_success_adds_participant(async_client):
    # Arrange
    activity_name = next(iter(app_module.activities.keys()))
    email = f"pytest-{uuid.uuid4()}@example.com"

    # Act
    resp = await async_client.post(f"/activities/{quote(activity_name)}/signup?email={quote(email)}")

    # Assert
    assert resp.status_code == 200
    body = resp.json()
    assert "message" in body

    get_resp = await async_client.get("/activities")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert email in data[activity_name]["participants"]


@pytest.mark.asyncio
async def test_signup_duplicate_returns_400(async_client):
    # Arrange: sign up once, then attempt duplicate
    activity_name = next(iter(app_module.activities.keys()))
    email = f"pytest-{uuid.uuid4()}@example.com"

    first = await async_client.post(f"/activities/{quote(activity_name)}/signup?email={quote(email)}")
    assert first.status_code == 200

    # Act: duplicate signup
    dup = await async_client.post(f"/activities/{quote(activity_name)}/signup?email={quote(email)}")

    # Assert
    assert dup.status_code == 400
    body = dup.json()
    assert "detail" in body


@pytest.mark.asyncio
async def test_signup_activity_not_found_returns_404(async_client):
    # Arrange
    missing = "NoSuchActivity-Does-Not-Exist"
    email = f"pytest-{uuid.uuid4()}@example.com"

    # Act
    resp = await async_client.post(f"/activities/{quote(missing)}/signup?email={quote(email)}")

    # Assert
    assert resp.status_code == 404
    body = resp.json()
    assert body.get("detail") == "Activity not found"


@pytest.mark.asyncio
async def test_capacity_behavior_documented(async_client):
    # Arrange
    # Pick an activity and repeatedly sign up unique emails to exceed max_participants.
    activity_name, details = next(iter(app_module.activities.items()))
    max_p = details.get("max_participants", 0) or 0

    # Act
    successes = 0
    for i in range(max_p + 2):
        email = f"pytest-{uuid.uuid4()}@example.com"
        resp = await async_client.post(f"/activities/{quote(activity_name)}/signup?email={quote(email)}")
        if resp.status_code == 200:
            successes += 1

    # Assert
    # Current implementation does not enforce capacity; document expected behavior accordingly
    assert successes == max_p + 2
