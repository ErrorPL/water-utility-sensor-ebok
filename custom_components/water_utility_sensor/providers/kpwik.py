"""KPWIK (Kobierzyckie Przedsiębiorstwo Wodociągów i Kanalizacji) water utility provider."""
import json
import logging
import random
import re
import ssl
from datetime import datetime
from typing import Optional, List

import certifi
import httpx

from . import WaterProvider, WaterReading, AccountBalance, ProviderInfo, ProviderRegistry

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://ebok.kpwik.com:7443"
APEX_BASE = f"{BASE_URL}/apex"

# ebok.kpwik.com's TLS handshake only sends its leaf certificate and omits the
# intermediate CA. Browsers paper over this by fetching the missing
# intermediate via the certificate's Authority Information Access (AIA)
# extension, but httpx/OpenSSL do not do AIA chasing, so the connection fails
# with "unable to get local issuer certificate". Confirmed via a direct TLS
# handshake against the host: the leaf's issuer is exactly this intermediate
# (Sectigo Public Server Authentication CA DV R36, valid until 2036-03-21),
# fetched from Sectigo's public repository (crt.sectigo.com) and pinned here
# so certificate validation stays intact instead of disabling verification.
_SECTIGO_SERVER_AUTH_CA_DV_R36 = """-----BEGIN CERTIFICATE-----
MIIGTDCCBDSgAwIBAgIQOXpmzCdWNi4NqofKbqvjsTANBgkqhkiG9w0BAQwFADBf
MQswCQYDVQQGEwJHQjEYMBYGA1UEChMPU2VjdGlnbyBMaW1pdGVkMTYwNAYDVQQD
Ey1TZWN0aWdvIFB1YmxpYyBTZXJ2ZXIgQXV0aGVudGljYXRpb24gUm9vdCBSNDYw
HhcNMjEwMzIyMDAwMDAwWhcNMzYwMzIxMjM1OTU5WjBgMQswCQYDVQQGEwJHQjEY
MBYGA1UEChMPU2VjdGlnbyBMaW1pdGVkMTcwNQYDVQQDEy5TZWN0aWdvIFB1Ymxp
YyBTZXJ2ZXIgQXV0aGVudGljYXRpb24gQ0EgRFYgUjM2MIIBojANBgkqhkiG9w0B
AQEFAAOCAY8AMIIBigKCAYEAljZf2HIz7+SPUPQCQObZYcrxLTHYdf1ZtMRe7Yeq
RPSwygz16qJ9cAWtWNTcuICc++p8Dct7zNGxCpqmEtqifO7NvuB5dEVexXn9RFFH
12Hm+NtPRQgXIFjx6MSJcNWuVO3XGE57L1mHlcQYj+g4hny90aFh2SCZCDEVkAja
EMMfYPKuCjHuuF+bzHFb/9gV8P9+ekcHENF2nR1efGWSKwnfG5RawlkaQDpRtZTm
M64TIsv/r7cyFO4nSjs1jLdXYdz5q3a4L0NoabZfbdxVb+CUEHfB0bpulZQtH1Rv
38e/lIdP7OTTIlZh6OYL6NhxP8So0/sht/4J9mqIGxRFc0/pC8suja+wcIUna0HB
pXKfXTKpzgis+zmXDL06ASJf5E4A2/m+Hp6b84sfPAwQ766rI65mh50S0Di9E3Pn
2WcaJc+PILsBmYpgtmgWTR9eV9otfKRUBfzHUHcVgarub/XluEpRlTtZudU5xbFN
xx/DgMrXLUAPaI60fZ6wA+PTAgMBAAGjggGBMIIBfTAfBgNVHSMEGDAWgBRWc1hk
lfmSGrASKgRieaFAFYghSTAdBgNVHQ4EFgQUaMASFhgOr872h6YyV6NGUV3LBycw
DgYDVR0PAQH/BAQDAgGGMBIGA1UdEwEB/wQIMAYBAf8CAQAwHQYDVR0lBBYwFAYI
KwYBBQUHAwEGCCsGAQUFBwMCMBsGA1UdIAQUMBIwBgYEVR0gADAIBgZngQwBAgEw
VAYDVR0fBE0wSzBJoEegRYZDaHR0cDovL2NybC5zZWN0aWdvLmNvbS9TZWN0aWdv
UHVibGljU2VydmVyQXV0aGVudGljYXRpb25Sb290UjQ2LmNybDCBhAYIKwYBBQUH
AQEEeDB2ME8GCCsGAQUFBzAChkNodHRwOi8vY3J0LnNlY3RpZ28uY29tL1NlY3Rp
Z29QdWJsaWNTZXJ2ZXJBdXRoZW50aWNhdGlvblJvb3RSNDYucDdjMCMGCCsGAQUF
BzABhhdodHRwOi8vb2NzcC5zZWN0aWdvLmNvbTANBgkqhkiG9w0BAQwFAAOCAgEA
YtOC9Fy+TqECFw40IospI92kLGgoSZGPOSQXMBqmsGWZUQ7rux7cj1du6d9rD6C8
ze1B2eQjkrGkIL/OF1s7vSmgYVafsRoZd/IHUrkoQvX8FZwUsmPu7amgBfaY3g+d
q1x0jNGKb6I6Bzdl6LgMD9qxp+3i7GQOnd9J8LFSietY6Z4jUBzVoOoz8iAU84OF
h2HhAuiPw1ai0VnY38RTI+8kepGWVfGxfBWzwH9uIjeooIeaosVFvE8cmYUB4TSH
5dUyD0jHct2+8ceKEtIoFU/FfHq/mDaVnvcDCZXtIgitdMFQdMZaVehmObyhRdDD
4NQCs0gaI9AAgFj4L9QtkARzhQLNyRf87Kln+YU0lgCGr9HLg3rGO8q+Y4ppLsOd
unQZ6ZxPNGIfOApbPVf5hCe58EZwiWdHIMn9lPP6+F404y8NNugbQixBber+x536
WrZhFZLjEkhp7fFXf9r32rNPfb74X/U90Bdy4lzp3+X1ukh1BuMxA/EEhDoTOS3l
7ABvc7BYSQubQ2490OcdkIzUh3ZwDrakMVrbaTxUM2p24N6dB+ns2zptWCva6jzW
r8IWKIMxzxLPv5Kt3ePKcUdvkBU/smqujSczTzzSjIoR5QqQA6lN1ZRSnuHIWCvh
JEltkYnTAH41QJ6SAWO66GrrUESwN/cgZzL4JLEqz1Y=
-----END CERTIFICATE-----
"""


def _build_ssl_context() -> ssl.SSLContext:
    """Default certifi trust store plus the intermediate KPWIK's server omits."""
    ctx = ssl.create_default_context(cafile=certifi.where())
    ctx.load_verify_locations(cadata=_SECTIGO_SERVER_AUTH_CA_DV_R36)
    return ctx


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
            verify=_build_ssl_context(),
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
    def _find_input_value(html: str, attr_name: str, attr_value: str) -> Optional[str]:
        """Return the `value="..."` of a hidden <input> tag identified by another
        attribute (id, name, or data-for). APEX renders these as plain HTML hidden
        inputs — NOT as inline JSON — and the attribute order on the tag varies
        (sometimes `value` comes before the identifying attribute, sometimes after),
        so both orders are tried. Confirmed via live inspection of the real
        rendered login page (the previous JSON-style regexes never matched anything,
        since this data was never present as literal JSON text on the page)."""
        escaped = re.escape(attr_value)
        m = re.search(
            rf'<input[^>]*\b{attr_name}="{escaped}"[^>]*\bvalue="([^"]*)"', html
        )
        if m:
            return m.group(1)
        m = re.search(
            rf'<input[^>]*\bvalue="([^"]*)"[^>]*\b{attr_name}="{escaped}"', html
        )
        if m:
            return m.group(1)
        return None

    # Page items submitted on the login form, in the same order the browser
    # submits them. Only P102_NAZWA and P102_WLASCICIEL are session-state
    # protected (i.e. carry a "ck" checksum) — confirmed by inspecting a real
    # submission's payload.
    _LOGIN_ITEM_NAMES = (
        "P102_HTTP",
        "P102_IP",
        "P102_POMOC",
        "P102_NAZWA",
        "P102_WLASCICIEL",
        "P102_USERNAME",
        "P102_PASSWORD",
    )
    _LOGIN_PROTECTED_ITEMS = ("P102_NAZWA", "P102_WLASCICIEL")

    @classmethod
    def _scrape_login_page(cls, html: str) -> dict:
        """Extract all APEX hidden fields and checksums from the login page HTML."""

        def _find(pattern, text, group=1, default=""):
            m = re.search(pattern, text)
            return m.group(group) if m else default

        # APEX session instance embedded in the page JS
        p_instance = _find(r'"pInstance"\s*:\s*"(\d+)"', html)
        if not p_instance:
            # Fallback: URL pattern in form action
            p_instance = _find(r'logowanie/(\d+)', html)

        # One-time submission nonce — plain hidden input <input ... id="pSalt" value="...">
        salt = cls._find_input_value(html, "id", "pSalt") or ""

        # The "protected" HMAC covering read-only field names
        # <input type="hidden" id="pPageItemsProtected" value="...">
        protected = cls._find_input_value(html, "id", "pPageItemsProtected") or ""

        # Each page item's current value lives in its own hidden/text <input
        # id="ITEM_NAME" name="ITEM_NAME" value="...">. Protected items additionally
        # have a checksum in a sibling <input data-for="ITEM_NAME" value="...">.
        item_values = {}
        item_checksums = {}
        for name in cls._LOGIN_ITEM_NAMES:
            item_values[name] = cls._find_input_value(html, "id", name) or ""
            ck = cls._find_input_value(html, "data-for", name)
            if ck:
                item_checksums[name] = ck

        return {
            "p_instance": p_instance,
            "salt": salt,
            "protected": protected,
            "item_values": item_values,
            "item_checksums": item_checksums,
            # kept for the diagnostic log below
            "ck_nazwa": item_checksums.get("P102_NAZWA", ""),
            "ck_wlasciciel": item_checksums.get("P102_WLASCICIEL", ""),
            "v_nazwa": item_values.get("P102_NAZWA", ""),
            "v_wlasciciel": item_values.get("P102_WLASCICIEL", ""),
            "v_http": item_values.get("P102_HTTP", "") or "https:",
            "v_ip": item_values.get("P102_IP", ""),
        }

    @classmethod
    def _scrape_meters_page(cls, html: str) -> dict:
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

        # Checksum for P20_INFSIECINSTAL_ID (the only checksummed item on this page).
        # Same plain-hidden-input pattern confirmed on the login page: a sibling
        # <input data-for="P20_INFSIECINSTAL_ID" value="..."> holds the checksum,
        # not inline JSON text.
        ck_instal = cls._find_input_value(html, "data-for", "P20_INFSIECINSTAL_ID") or ""

        # Protected HMAC for the page's form region — plain hidden input.
        protected = cls._find_input_value(html, "id", "pPageItemsProtected") or ""

        # Salt / submission nonce — plain hidden input.
        salt = cls._find_input_value(html, "id", "pSalt") or ""

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

            # TEMPORARY DIAGNOSTIC LOGGING (remove once login is confirmed working):
            # logged at WARNING so it's visible without enabling debug logging.
            _LOGGER.warning(
                "KPWIK DIAG: p_instance=%r salt=%r protected_len=%s "
                "ck_nazwa=%r ck_wlasciciel=%r v_nazwa=%r v_wlasciciel=%r v_http=%r v_ip=%r",
                p_instance,
                fields["salt"],
                len(fields["protected"]) if fields["protected"] else 0,
                fields["ck_nazwa"],
                fields["ck_wlasciciel"],
                fields["v_nazwa"],
                fields["v_wlasciciel"],
                fields["v_http"],
                fields["v_ip"],
            )
            if not fields["salt"]:
                _LOGGER.warning(
                    "KPWIK DIAG: salt/submission-id came back EMPTY — "
                    "the login POST is very likely being rejected because of this"
                )

            # Step 2 — submit credentials
            # Build the p_json payload exactly as the browser does. Values for
            # every item come from the page's own hidden inputs (scraped above),
            # except the two credential fields which we override with the real
            # username/password. Only the items in _LOGIN_PROTECTED_ITEMS carry
            # a "ck" checksum — confirmed by capturing a real browser submission.
            item_values = dict(fields["item_values"])
            item_values["P102_USERNAME"] = self.username
            item_values["P102_PASSWORD"] = self.password

            items_to_submit = []
            for name in self._LOGIN_ITEM_NAMES:
                item = {"n": name, "v": item_values.get(name, "")}
                if name in self._LOGIN_PROTECTED_ITEMS:
                    ck = fields["item_checksums"].get(name)
                    if ck:
                        item["ck"] = ck
                items_to_submit.append(item)

            p_json = {
                "pageItems": {
                    "itemsToSubmit": items_to_submit,
                    "protected": fields["protected"],
                    "rowVersion": "",
                    "formRegionChecksums": [],
                },
                "salt": fields["salt"],
            }

            # p_page_submission_id is a fresh client-generated nonce — NOT the
            # same value as salt. The real browser generates a new random numeric
            # string for it on every submission (confirmed via live capture: it
            # never appears anywhere in the page HTML, unlike salt/protected/ck).
            page_submission_id = "".join(random.choices("0123456789", k=39))

            post_data = {
                "p_flow_id":            "110",
                "p_flow_step_id":       "102",
                "p_instance":           p_instance,
                "p_debug":              "",
                "p_request":            "P102_ZALOGUJ",
                "p_reload_on_submit":   "S",
                "p_page_submission_id": page_submission_id,
                "p_json":               json.dumps(p_json, separators=(",", ":")),
            }

            _LOGGER.debug("KPWIK: posting login credentials")
            resp = client.post(
                f"{APEX_BASE}/wwv_flow.accept?p_context=e/logowanie/{p_instance}",
                data=post_data,
                headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
            )
            resp.raise_for_status()

            # TEMPORARY DIAGNOSTIC LOGGING (remove once login is confirmed working):
            _LOGGER.warning(
                "KPWIK DIAG: login POST -> status=%s final_url=%s cookies=%s body_snippet=%.400r",
                resp.status_code,
                resp.url,
                list(client.cookies.keys()),
                resp.text,
            )

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
            _LOGGER.warning(
                "KPWIK DIAG: dashboard check -> status=%s final_url=%s",
                dash.status_code,
                dash.url,
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
