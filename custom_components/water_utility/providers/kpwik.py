"""KPWIK (Kobierzyckie Przedsiębiorstwo Wodociągów i Kanalizacji) water utility provider."""
import base64
import html
import json
import logging
import re
import ssl
from datetime import datetime
from typing import Optional, List
from urllib.parse import parse_qs, urljoin, urlparse

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

    # Sent only on the wwv_flow.ajax region fetch. The login page GET and the
    # wwv_flow.accept POST are ordinary browser navigations (the page submits a
    # plain <form method="post">), so flagging them as XHR misrepresents them.
    _AJAX_HEADERS = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
    }

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
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                ),
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/",
            },
        )

    @staticmethod
    def _find_input_value(html_text: str, attr_name: str, attr_value: str) -> Optional[str]:
        """Return the `value="..."` of a hidden <input> tag identified by another
        attribute (id, name, or data-for). APEX renders these as plain HTML hidden
        inputs — NOT as inline JSON — and the attribute order on the tag varies
        (sometimes `value` comes before the identifying attribute, sometimes after),
        so both orders are tried.

        The value is HTML-unescaped before being returned. This matters: APEX emits
        pPageItemsProtected as standard base64, so it can contain "/", which the page
        renders as `&#x2F;`. Submitting the escaped form corrupts the HMAC and the
        server rejects the login with a checksum error. (The per-item `ck` checksums
        are base64url and contain no "/", which is why they appeared to work.)"""
        escaped = re.escape(attr_value)
        m = re.search(
            rf'<input[^>]*\b{attr_name}="{escaped}"[^>]*\bvalue="([^"]*)"', html_text
        )
        if not m:
            m = re.search(
                rf'<input[^>]*\bvalue="([^"]*)"[^>]*\b{attr_name}="{escaped}"', html_text
            )
        if m:
            return html.unescape(m.group(1))
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
    def _scrape_login_page(cls, html_text: str) -> dict:
        """Extract all APEX hidden fields and checksums from the login page HTML."""

        # APEX 22.2 renders the session instance as a hidden input, not as inline
        # JSON. The form action carries it too, so keep that as a last resort.
        p_instance = (
            cls._find_input_value(html_text, "id", "pInstance")
            or cls._find_input_value(html_text, "name", "p_instance")
            or ""
        )
        if not p_instance:
            m = re.search(r'logowanie/(\d+)', html_text)
            p_instance = m.group(1) if m else ""

        # One-time submission nonce — plain hidden input <input ... id="pSalt" value="...">
        salt = cls._find_input_value(html_text, "id", "pSalt") or ""

        # Duplicate-submission token. APEX renders this on the page; it must be
        # echoed back verbatim, not invented client-side.
        page_submission_id = (
            cls._find_input_value(html_text, "id", "pPageSubmissionId") or ""
        )

        # The "protected" HMAC covering read-only field names
        # <input type="hidden" id="pPageItemsProtected" value="...">
        protected = cls._find_input_value(html_text, "id", "pPageItemsProtected") or ""

        # Each page item's current value lives in its own hidden/text <input
        # id="ITEM_NAME" name="ITEM_NAME" value="...">. Protected items additionally
        # have a checksum in a sibling <input data-for="ITEM_NAME" value="...">.
        item_values = {}
        item_checksums = {}
        for name in cls._LOGIN_ITEM_NAMES:
            item_values[name] = cls._find_input_value(html_text, "id", name) or ""
            ck = cls._find_input_value(html_text, "data-for", name)
            if ck:
                item_checksums[name] = ck

        return {
            "p_instance": p_instance,
            "salt": salt,
            "page_submission_id": page_submission_id,
            "protected": protected,
            "item_values": item_values,
            "item_checksums": item_checksums,
        }

    # Card regions on the wodomierze page, addressed by their APEX static id. The
    # static ids are set by the application author and survive redeployment; the
    # numeric region ids and the signed ajaxIdentifier tokens beside them are
    # regenerated whenever the app is republished, so those must be read off the
    # page every time rather than hardcoded.
    REGION_ACTIVE_METERS = "R_AKTYWNE_WODOMIERZE_20"
    REGION_METER_HISTORY = "R_HISTORIA_WODOMIERZY_20"

    @staticmethod
    def _js_unescape(text: str) -> str:
        r"""Decode the \uXXXX escapes APEX emits inside inline JS string literals.

        Matters for ajaxIdentifier, which is base64 and routinely contains "/" —
        written in the page as /. Sending the literal backslash-u form is
        rejected by the server."""
        return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), text)

    @classmethod
    def _scrape_regions(cls, html_text: str) -> dict:
        """Map each card region's static id to its numeric id and ajaxIdentifier."""
        pattern = re.compile(
            r'"regionId"\s*:\s*"(\d+)"\s*,\s*"regionStaticId"\s*:\s*"([^"]+)"'
            r'[^}]*?"ajaxIdentifier"\s*:\s*"([^"]+)"'
        )
        return {
            static_id: {"id": region_id, "ajax_id": cls._js_unescape(ajax_id)}
            for region_id, static_id, ajax_id in pattern.findall(html_text)
        }

    @classmethod
    def _scrape_page_items(cls, html_text: str) -> tuple:
        """Collect every APEX page item (P0_*, P20_*, ...) with its checksum.

        Values live in <input name="ITEM" value="...">; session-state-protected items
        additionally carry a sibling <input data-for="ITEM" value="<checksum>">.
        Reading them generically means we submit whatever the page actually declares,
        rather than a hand-maintained list that rots silently when the portal changes."""
        values: dict = {}
        checksums: dict = {}
        is_page_item = re.compile(r"^P\d+_")

        for tag in re.findall(r"<input[^>]*>", html_text):
            value_m = re.search(r'\bvalue="([^"]*)"', tag)
            value = html.unescape(value_m.group(1)) if value_m else ""

            data_for = re.search(r'\bdata-for="([^"]+)"', tag)
            if data_for:
                checksums[data_for.group(1)] = value
                continue

            name = re.search(r'\bname="([^"]+)"', tag)
            if name and is_page_item.match(name.group(1)):
                values[name.group(1)] = value

        # Filter items (P20_WODOMIERZ, P20_PUNKTY) are <select>, not <input>. Submit
        # the currently selected option — empty means "Wszystkie" (all meters).
        for select in re.finditer(
            r'<select[^>]*\bname="(P\d+_[^"]+)"[^>]*>(.*?)</select>', html_text, re.S
        ):
            selected = re.search(
                r'<option[^>]*\bvalue="([^"]*)"[^>]*\bselected\b', select.group(2)
            )
            values[select.group(1)] = (
                html.unescape(selected.group(1)) if selected else ""
            )

        return values, checksums

    @classmethod
    def _scrape_meters_page(cls, html_text: str) -> dict:
        """Extract everything needed to issue a region-fetch AJAX call against a page.

        Works for any APEX page, not just wodomierze — the meter-history page reached
        via the card's "Pokaż" link is scraped the same way."""
        values, checksums = cls._scrape_page_items(html_text)
        return {
            "regions": cls._scrape_regions(html_text),
            "item_values": values,
            "item_checksums": checksums,
            "protected": cls._find_input_value(html_text, "id", "pPageItemsProtected") or "",
            "salt": cls._find_input_value(html_text, "id", "pSalt") or "",
            # pContext already embeds the session, e.g. "e/wodomierze/6587303858507"
            "context": cls._find_input_value(html_text, "id", "pContext") or "",
            "flow_step_id": cls._find_input_value(html_text, "id", "pFlowStepId") or "",
        }

    def _fetch_region_on(
        self,
        page_html: str,
        context: str,
        flow_step_id: str,
        region_static_id: str,
        max_rows: int = 500,
    ) -> list:
        """Run an APEX region-fetch against an already-loaded page.

        Returns the region's raw rows (a list of column-value arrays).
        """
        fields = self._scrape_meters_page(page_html)
        region = fields["regions"].get(region_static_id)
        if not region:
            _LOGGER.error(
                "KPWIK: region %s not on page (found: %s)",
                region_static_id,
                ", ".join(fields["regions"]) or "none",
            )
            return []

        # Submit every page item the page declares, each with its checksum where it
        # has one. The server validates the set against `protected`.
        items_to_submit = []
        for name, value in fields["item_values"].items():
            item = {"n": name, "v": value}
            ck = fields["item_checksums"].get(name)
            if ck:
                item["ck"] = ck
            items_to_submit.append(item)

        p_json = {
            "regions": [
                {
                    "id": region["id"],
                    "ajaxIdentifier": region["ajax_id"],
                    "fetchData": {"version": 1, "firstRow": 1, "maxRows": max_rows},
                }
            ],
            "pageItems": {
                "itemsToSubmit": items_to_submit,
                "protected": fields["protected"],
                "rowVersion": "",
                "formRegionChecksums": [],
            },
            "salt": fields["salt"],
        }

        resp = self._session.post(
            f"{APEX_BASE}/wwv_flow.ajax",
            params={"p_context": context},
            data={
                "p_flow_id":      "110",
                "p_flow_step_id": flow_step_id,
                "p_instance":     self._p_instance,
                "p_debug":        "",
                "p_json":         json.dumps(p_json, separators=(",", ":")),
            },
            headers={
                **self._AJAX_HEADERS,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
        )
        resp.raise_for_status()
        return resp.json()["regions"][0]["fetchedData"]["values"]

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

            post_data = {
                "p_flow_id":            "110",
                "p_flow_step_id":       "102",
                "p_instance":           p_instance,
                "p_debug":              "",
                "p_request":            "P102_ZALOGUJ",
                "p_reload_on_submit":   "S",
                "p_page_submission_id": fields["page_submission_id"],
                "p_json":               json.dumps(p_json, separators=(",", ":")),
            }

            _LOGGER.debug("KPWIK: posting login credentials")
            resp = client.post(
                f"{APEX_BASE}/wwv_flow.accept?p_context=e/logowanie/{p_instance}",
                data=post_data,
                headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
            )
            resp.raise_for_status()

            # wwv_flow.accept answers with {"redirectURL": "..."} rather than an HTTP
            # redirect. That URL is the only place the post-login session id appears:
            # APEX rotates the id on successful authentication, so the pre-login
            # p_instance is dead from here on and must not be reused.
            #
            # The ORA_WWV_APP_110 cookie is set even for a *rejected* login, so its
            # presence proves nothing — the redirect target is what tells us whether
            # we actually got in.
            redirect_url = ""
            try:
                redirect_url = resp.json().get("redirectURL", "")
            except ValueError:
                pass

            if not redirect_url:
                _LOGGER.error(
                    "KPWIK: login failed — no redirectURL in the response to the "
                    "credential POST (status %s)", resp.status_code
                )
                return False

            if "logowanie" in redirect_url:
                _LOGGER.error(
                    "KPWIK: login rejected by the portal: %s",
                    self._decode_notification(redirect_url) or "credentials refused",
                )
                return False

            # Follow the redirect and adopt the new session id it carries.
            dash = client.get(urljoin(BASE_URL, redirect_url))
            if "logowanie" in dash.url.path:
                _LOGGER.error("KPWIK: login failed — redirected back to login page")
                return False

            new_instance = parse_qs(urlparse(str(dash.url)).query).get("session", [""])[0]
            self._session = client
            self._p_instance = new_instance or p_instance
            _LOGGER.info("KPWIK: login successful, p_instance=%s", self._p_instance)
            return True

        except Exception:
            _LOGGER.exception("KPWIK: login error")
            client.close()
            return False

    @staticmethod
    def _decode_notification(redirect_url: str) -> str:
        """Pull the human-readable reason out of a rejected login's redirect URL.

        APEX puts it in a `notification_msg` query parameter as base64 with a
        trailing HMAC, e.g. "Identyfikator lub hasło jest nieprawidłowe"."""
        raw = parse_qs(urlparse(redirect_url).query).get("notification_msg", [""])[0]
        if not raw:
            return ""
        # APEX appends a "/"-separated HMAC to the base64url payload. Both halves are
        # base64url (no "+" or "/"), so splitting on the first "/" is unambiguous.
        payload = raw.split("/")[0]
        try:
            return base64.b64decode(
                payload + "=" * (-len(payload) % 4), altchars=b"-_"
            ).decode("utf-8", "replace")
        except Exception:
            return ""

    def _ensure_session(self) -> bool:
        """Return True if a valid session exists, otherwise attempt login."""
        if self._session and self._p_instance:
            return True
        return self.login()

    def _get_meters_page(self) -> Optional[str]:
        """Fetch the wodomierze page HTML with the authenticated session.

        Deliberately no `clear=RP,20` here. That parameter asks APEX to reset page
        items, which Session State Protection only permits on a URL carrying a valid
        `cs=` checksum. Without one the server discards the whole page and renders
        "Naruszenie ochrony stanu sesji" instead — an error page with no regions on
        it, which is why the region fetch used to find no ajaxIdentifier."""
        resp = self._session.get(
            f"{APEX_BASE}/r/ebok/e/wodomierze",
            params={"session": self._p_instance},
        )
        resp.raise_for_status()
        if "Naruszenie ochrony stanu sesji" in resp.text:
            _LOGGER.error("KPWIK: meters page rejected by APEX session-state protection")
            return None
        return resp.text

    def _fetch_region(self, region_static_id: str, max_rows: int = 500) -> list:
        """Fetch a region on the wodomierze page. Returns its raw rows."""
        if not self._ensure_session():
            return []

        try:
            page = self._get_meters_page()
            if page is None:
                return []
            fields = self._scrape_meters_page(page)
            return self._fetch_region_on(
                page,
                fields["context"],
                fields["flow_step_id"],
                region_static_id,
                max_rows,
            )
        except Exception:
            _LOGGER.exception("KPWIK: error fetching region %s", region_static_id)
            return []

    def _fetch_meter_list(self) -> list:
        """Active meters with their latest readings."""
        return self._fetch_region(self.REGION_ACTIVE_METERS)

    @staticmethod
    def _parse_meter_row(row: list) -> Optional[WaterReading]:
        """
        Parse one row from the meter-list APEX response.

        Column layout (0-based), verified against live data from the portal:
          0  — installation ID            e.g. "39455"
          1  — JS dialog opener for the per-meter readings page (ignored here)
          2  — meter serial number        e.g. "C23FA094856"
          3  — address string
          4  — last reading date          "YYYY-MM-DD"
          5  — current meter reading      (m³, whitespace-padded, comma decimal)
          6  — consumption since previous (m³, whitespace-padded, comma decimal)
          14 — meter type                 "Główny" or "Podlicznik"
        """
        try:
            def _float(val) -> float:
                if val is None:
                    return 0.0
                return float(str(val).strip().replace(",", ".").replace(" ", ""))

            meter_number = str(row[2]).strip()
            date_str     = str(row[4]).strip()          # "2026-06-18"
            current      = _float(row[5])               # 55.00
            consumption  = _float(row[6])               # 3.00
            previous     = current - consumption        # 52.00
            meter_type   = str(row[14] or "").strip()   # "Główny" / "Podlicznik"

            timestamp = datetime.strptime(date_str, "%Y-%m-%d") if date_str else datetime.now()

            return WaterReading(
                timestamp=timestamp,
                current_reading=current,
                previous_reading=previous,
                consumption=consumption,
                meter_number=meter_number,
                meter_type=meter_type,
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
