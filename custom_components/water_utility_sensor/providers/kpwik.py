"""KPWIK (Kobierzyckie Przedsiębiorstwo Wodociągów i Kanalizacji) water utility provider."""
import json
import logging
import re
from datetime import datetime
from typing import Optional, List

import httpx

from . import WaterProvider, WaterReading, AccountBalance, ProviderInfo, ProviderRegistry

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://ebok.kpwik.com:7443"
APEX_BASE = f"{BASE_URL}/apex"


@ProviderRegistry.register
class KpwikProvider(WaterProvider):
    """Provider for KPWIK (ebok.kpwik.com) — Oracle APEX 22.2 portal."""

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(
            id="kpwik",
            name="KPWIK Kobierzyce",
            description="Kobierzyckie Przedsiębiorstwo Wodociągów i Kanalizacji",
        )

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self._session: Optional[httpx.Client] = None
        self._p_instance: Optional[str] = None  # APEX session ID

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_client(self) -> httpx.Client:
        return httpx.Client(
            base_url=BASE_URL,
            follow_redirects=True,
            timeout=30,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/148.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/",
            },
        )

    @staticmethod
    def _scrape_login_page(html: str) -> dict:
        """Extract all APEX hidden fields and checksums from the login page HTML."""

        def _find(pattern, text, group=1, default=""):
            m = re.search(pattern, text)
            return m.group(group) if m else default

        # APEX session instance embedded in the page JS
        p_instance = _find(r'"pInstance"\s*:\s*"(\d+)"', html)
        if not p_instance:
            # Fallback: URL pattern in form action
            p_instance = _find(r'logowanie/(\d+)', html)

        # One-time submission nonce (same as salt in p_json)
        salt = _find(r'"salt"\s*:\s*"(\d+)"', html)

        # The "protected" HMAC covering read-only field names
        protected = _find(r'"protected"\s*:\s*"([^"]+)"', html)

        # Checksums for server-set read-only items (P102_NAZWA, P102_WLASCICIEL)
        # These are per-session HMACs the server embeds next to each read-only item
        ck_nazwa = _find(r'"n"\s*:\s*"P102_NAZWA"[^}]*"ck"\s*:\s*"([^"]+)"', html)
        ck_wlasciciel = _find(r'"n"\s*:\s*"P102_WLASCICIEL"[^}]*"ck"\s*:\s*"([^"]+)"', html)

        # Server-populated read-only values
        v_nazwa = _find(r'"n"\s*:\s*"P102_NAZWA"[^}]*"v"\s*:\s*"([^"]*)"', html)
        v_wlasciciel = _find(r'"n"\s*:\s*"P102_WLASCICIEL"[^}]*"v"\s*:\s*"([^"]*)"', html)

        # HTTP protocol and client IP injected by APEX
        v_http = _find(r'"n"\s*:\s*"P102_HTTP"[^}]*"v"\s*:\s*"([^"]*)"', html) or "https:"
        v_ip = _find(r'"n"\s*:\s*"P102_IP"[^}]*"v"\s*:\s*"([^"]*)"', html)

        return {
            "p_instance": p_instance,
            "salt": salt,
            "protected": protected,
            "ck_nazwa": ck_nazwa,
            "ck_wlasciciel": ck_wlasciciel,
            "v_nazwa": v_nazwa,
            "v_wlasciciel": v_wlasciciel,
            "v_http": v_http,
            "v_ip": v_ip,
        }

    @staticmethod
    def _scrape_meters_page(html: str) -> dict:
        """Extract the APEX region ajaxIdentifier and page-item checksums
        needed to fetch the meter list from the wodomierze (meters) page."""

        def _find(pattern, text, group=1, default=""):
            m = re.search(pattern, text)
            return m.group(group) if m else default

        # Region ID for the active meters card view
        region_id = _find(r'"id"\s*:\s*"(9754\d+)"', html)

        # ajaxIdentifier is a server-signed token for the region fetch
        ajax_id = _find(
            r'"id"\s*:\s*"9754[^"]*"[^}]*"ajaxIdentifier"\s*:\s*"([^"]+)"',
            html,
        )
        if not ajax_id:
            # Broader fallback: first ajaxIdentifier that looks like a region token
            ajax_id = _find(r'"ajaxIdentifier"\s*:\s*"(UkVHSU9O[^"]+)"', html)

        # Checksum for P20_INFSIECINSTAL_ID (the only checksummed item on this page)
        ck_instal = _find(
            r'"n"\s*:\s*"P20_INFSIECINSTAL_ID"[^}]*"ck"\s*:\s*"([^"]+)"', html
        )

        # Protected HMAC for the page's form region
        protected = _find(r'"protected"\s*:\s*"([^"]+)"', html)

        # Salt / submission nonce
        salt = _find(r'"salt"\s*:\s*"(\d+)"', html)

        return {
            "region_id": region_id,
            "ajax_id": ajax_id,
            "ck_instal": ck_instal,
            "protected": protected,
            "salt": salt,
        }

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def login(self) -> bool:
        """
        Two-step APEX login:
          1. GET the login page to obtain the session instance, nonce, and HMACs.
          2. POST credentials to wwv_flow.accept.
        """
        client = self._make_client()

        try:
            # Step 1 — obtain a fresh APEX session and all hidden field values
            _LOGGER.debug("KPWIK: fetching login page")
            resp = client.get(f"{APEX_BASE}/r/ebok/e/logowanie")
            resp.raise_for_status()

            fields = self._scrape_login_page(resp.text)
            p_instance = fields["p_instance"]

            if not p_instance:
                _LOGGER.error("KPWIK: could not extract p_instance from login page")
                return False

            _LOGGER.debug("KPWIK: p_instance=%s", p_instance)

            # Step 2 — submit credentials
            # Build the p_json payload exactly as the browser does
            items_to_submit = [
                {"n": "P102_HTTP", "v": fields["v_http"]},
                {"n": "P102_IP",   "v": fields["v_ip"]},
                {"n": "P102_POMOC", "v": ""},
            ]
            if fields["ck_nazwa"]:
                items_to_submit.append(
                    {"n": "P102_NAZWA", "v": fields["v_nazwa"], "ck": fields["ck_nazwa"]}
                )
            if fields["ck_wlasciciel"]:
                items_to_submit.append(
                    {"n": "P102_WLASCICIEL", "v": fields["v_wlasciciel"],
                     "ck": fields["ck_wlasciciel"]}
                )
            items_to_submit += [
                {"n": "P102_USERNAME", "v": self.username},
                {"n": "P102_PASSWORD", "v": self.password},
            ]

            p_json = {
                "pageItems": {
                    "itemsToSubmit": items_to_submit,
                    "protected": fields["protected"],
                    "rowVersion": "",
                    "formRegionChecksums": [],
                },
                "salt": fields["salt"],
            }

            post_data = {
                "p_flow_id":            "110",
                "p_flow_step_id":       "102",
                "p_instance":           p_instance,
                "p_debug":              "",
                "p_request":            "P102_ZALOGUJ",
                "p_reload_on_submit":   "S",
                "p_page_submission_id": fields["salt"],
                "p_json":               json.dumps(p_json, separators=(",", ":")),
            }

            _LOGGER.debug("KPWIK: posting login credentials")
            resp = client.post(
                f"{APEX_BASE}/wwv_flow.accept?p_context=e/logowanie/{p_instance}",
                data=post_data,
                headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
            )
            resp.raise_for_status()

            # Verify we are authenticated: the session cookie must be present
            # and the response must not redirect back to the login page
            session_cookie = client.cookies.get("ORA_WWV_APP_110")
            if not session_cookie:
                _LOGGER.error("KPWIK: login failed — no session cookie received")
                return False

            # Quick sanity-check: fetch the dashboard page
            dash = client.get(
                f"{APEX_BASE}/r/ebok/e/podsumowanie",
                params={"session": p_instance},
            )
            if "logowanie" in dash.url.path:
                _LOGGER.error("KPWIK: login failed — redirected back to login page")
                return False

            self._session = client
            self._p_instance = p_instance
            _LOGGER.info("KPWIK: login successful, p_instance=%s", p_instance)
            return True

        except Exception:
            _LOGGER.exception("KPWIK: login error")
            client.close()
            return False

    def _ensure_session(self) -> bool:
        """Return True if a valid session exists, otherwise attempt login."""
        if self._session and self._p_instance:
            return True
        return self.login()

    def _fetch_meter_list(self) -> list:
        """
        POST to the wodomierze (meters) APEX page to retrieve the list of
        active meters with their latest readings.

        Returns a list of raw column-value arrays from the APEX JSON response.
        """
        if not self._ensure_session():
            return []

        try:
            # Load the meters page to pick up a fresh ajaxIdentifier + checksums
            resp = self._session.get(
                f"{APEX_BASE}/r/ebok/e/wodomierze",
                params={"clear": "RP,20", "session": self._p_instance},
            )
            resp.raise_for_status()
            page_fields = self._scrape_meters_page(resp.text)

            if not page_fields["ajax_id"]:
                _LOGGER.error("KPWIK: could not find ajaxIdentifier on meters page")
                return []

            # Build the region-fetch AJAX request
            p_json = {
                "regions": [
                    {
                        "id": page_fields["region_id"],
                        "ajaxIdentifier": page_fields["ajax_id"],
                        "fetchData": {
                            "version": 1,
                            "firstRow": 1,
                            "maxRows": 100,
                        },
                    }
                ],
                "pageItems": {
                    "itemsToSubmit": [
                        {
                            "n": "P20_INFSIECINSTAL_ID",
                            "v": "",
                            **({"ck": page_fields["ck_instal"]}
                               if page_fields["ck_instal"] else {}),
                        },
                        {"n": "P20_PUNKTY",     "v": ""},
                        {"n": "P20_WODOMIERZ",  "v": ""},
                    ],
                    "protected": page_fields["protected"],
                    "rowVersion": "",
                    "formRegionChecksums": [],
                },
                "salt": page_fields["salt"],
            }

            ajax_resp = self._session.post(
                f"{APEX_BASE}/wwv_flow.ajax"
                f"?p_context=e/wodomierze/{self._p_instance}",
                data={
                    "p_flow_id":      "110",
                    "p_flow_step_id": "20",
                    "p_instance":     self._p_instance,
                    "p_debug":        "",
                    "p_json":         json.dumps(p_json, separators=(",", ":")),
                },
                headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
            )
            ajax_resp.raise_for_status()
            data = ajax_resp.json()
            return data["regions"][0]["fetchedData"]["values"]

        except Exception:
            _LOGGER.exception("KPWIK: error fetching meter list")
            return []

    @staticmethod
    def _parse_meter_row(row: list) -> Optional[WaterReading]:
        """
        Parse one row from the meter-list APEX response.

        Column layout (0-based, from HAR analysis):
          0  — installation ID (int as string)
          1  — JS dialog opener (ignored)
          2  — meter serial number  e.g. "C23FA094856"
          3  — address string
          4  — last reading date  "YYYY-MM-DD"
          5  — current meter reading (m³, string with whitespace + comma decimal)
          6  — last consumption (m³, string with whitespace + comma decimal)
          14 — meter type  "Zwykły"
        """
        try:
            def _float(val) -> float:
                if val is None:
                    return 0.0
                return float(str(val).strip().replace(",", ".").replace(" ", ""))

            meter_number = str(row[2]).strip()
            date_str     = str(row[4]).strip()          # "2026-04-13"
            current      = _float(row[5])               # 23.00
            consumption  = _float(row[6])               # 4.00
            previous     = current - consumption        # derived

            timestamp = datetime.strptime(date_str, "%Y-%m-%d") if date_str else datetime.now()

            return WaterReading(
                timestamp=timestamp,
                current_reading=current,
                previous_reading=previous,
                consumption=consumption,
                meter_number=meter_number,
            )
        except Exception:
            _LOGGER.exception("KPWIK: failed to parse meter row: %s", row)
            return None

    def get_current_reading(self) -> Optional[WaterReading]:
        """Return the reading for the first (usually only) meter."""
        rows = self._fetch_meter_list()
        if not rows:
            return None
        return self._parse_meter_row(rows[0])

    def get_all_readings(self) -> List[WaterReading]:
        """Return readings for all meters on the account."""
        readings = []
        for row in self._fetch_meter_list():
            reading = self._parse_meter_row(row)
            if reading:
                readings.append(reading)
        return readings

    def get_account_balance(self) -> Optional[AccountBalance]:
        """
        KPWIK eBOK does not expose a balance/payments page in the observed
        HAR traffic. Return None until such an endpoint is identified.
        """
        return None
