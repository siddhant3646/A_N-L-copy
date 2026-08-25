import pytest
import time
from unittest.mock import AsyncMock, MagicMock
from src.sentinel.session_manager import SessionManager


@pytest.mark.asyncio
async def test_session_manager_init_and_record():
    sm = SessionManager(max_inactive_seconds=300.0)
    assert sm.max_inactive == 300.0
    assert sm.last_url is None
    assert sm.crashes == 0

    sm.record_activity(url="https://www.naukri.com/jobs", title="Naukri Jobs")
    assert sm.last_url == "https://www.naukri.com/jobs"
    assert sm.last_title == "Naukri Jobs"


@pytest.mark.asyncio
async def test_session_manager_reset():
    sm = SessionManager(max_inactive_seconds=300.0)
    sm.record_activity(url="https://www.instahyre.com/opportunities", title="Instahyre")
    sm.crashes = 2
    sm.last_activity = time.monotonic() - 500

    sm.reset()
    assert sm.last_url is None
    assert sm.last_title is None
    assert sm.crashes == 0
    assert (time.monotonic() - sm.last_activity) < 5.0


@pytest.mark.asyncio
async def test_session_manager_health_inactivity():
    sm = SessionManager(max_inactive_seconds=10.0)
    sm.last_activity = time.monotonic() - 20.0

    mock_page = MagicMock()
    mock_page.is_closed.return_value = False
    mock_page.url = "https://www.naukri.com/jobs"

    async def mock_title():
        return "Jobs"
    mock_page.title = mock_title

    health = await sm.check_health(mock_page)
    assert health["healthy"] is False
    assert "Inactive for" in health["reason"]


@pytest.mark.asyncio
async def test_session_manager_recover_prioritizes_expected_url():
    sm = SessionManager()
    sm.last_url = "https://www.instahyre.com/opportunities"

    mock_page = MagicMock()
    mock_page.is_closed.return_value = False
    mock_page.url = "https://www.naukri.com/recommendedjobs"
    mock_page.reload = AsyncMock()
    mock_page.goto = AsyncMock()

    # When expected_url is provided, it must use expected_url
    success = await sm.recover(mock_page, expected_url="https://www.naukri.com/recommendedjobs")
    assert success is True
    mock_page.reload.assert_awaited_once()
    # url matches expected_url, so goto is not even needed after reload
    mock_page.goto.assert_not_awaited()


@pytest.mark.asyncio
async def test_session_manager_recover_does_not_redirect_to_stale_url():
    sm = SessionManager()
    # Stale URL from previous task
    sm.last_url = "https://www.instahyre.com/opportunities"

    mock_page = MagicMock()
    mock_page.is_closed.return_value = False
    # Current page is on Naukri
    mock_page.url = "https://www.naukri.com/recommendedjobs"
    mock_page.reload = AsyncMock()
    mock_page.goto = AsyncMock()

    # If expected_url is None, it should prioritize current page.url over stale self.last_url
    success = await sm.recover(mock_page)
    assert success is True
    mock_page.reload.assert_awaited_once()
    # It must NOT navigate to Instahyre!
    mock_page.goto.assert_not_awaited()
