"""Central configuration.

All tunables live here and are overridable via environment variables
(prefix ``BVB_``) or a local ``.env`` file. Nothing configurable should be
hard-coded elsewhere in the codebase.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


class Settings(BaseSettings):
    """Runtime configuration, sourced from env (``BVB_*``) or ``.env``."""

    model_config = SettingsConfigDict(env_prefix="BVB_", env_file=".env", extra="ignore")

    # ── Base + endpoint URLs (every working endpoint is preserved here) ──
    base_url: str = "https://www.bvb.ro"
    discovery_url: str = "https://www.bvb.ro/proxyshld.aspx/GetInstrumentsList"
    trading_url: str = "https://www.bvb.ro/TradingAndStatistics/Trading/CurrentTradingDay"
    detail_url_tmpl: str = (
        "https://www.bvb.ro/FinancialInstruments/Details/"
        "FinancialInstrumentsDetails.aspx?s={symbol}"
    )
    indices_url: str = "https://www.bvb.ro/FinancialInstruments/Indices/IndicesProfiles"
    current_reports_url: str = "https://www.bvb.ro/FinancialInstruments/SelectedData/CurrentReports"

    # ── HTTP behaviour ──
    user_agent: str = DEFAULT_USER_AGENT
    request_timeout: int = 20
    request_delay: float = 0.35
    max_workers: int = 6
    retry_total: int = 5
    retry_backoff: float = 0.5

    # ── ETF postback target (ASP.NET __EVENTTARGET) ──
    etf_event_target: str = "ctl00$ctl00$body$rightColumnPlaceHolder$" "TabsCtrlInstrumentsType$lb3"

    # ── Storage / persistence ──
    database_url: str = "sqlite:///bvb.sqlite3"
    # Read-only connection for the public API; falls back to database_url.
    api_database_url: str | None = None
    storage_dir: str = "storage"

    # ── Public API ──
    api_cache_seconds: int = 1800

    # ── Logging ──
    log_level: str = "INFO"

    @property
    def headers(self) -> dict[str, str]:
        """Default request headers mimicking a real browser."""
        return {
            "User-Agent": self.user_agent,
            "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
            "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": f"{self.base_url}/",
        }


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings singleton."""
    return Settings()


settings: Settings = get_settings()
