"""WODKAN Krzeszowice water utility provider."""
import re
from datetime import datetime
from typing import Optional, List

import httpx

from . import WaterProvider, WaterReading, AccountBalance, ProviderInfo, ProviderRegistry


@ProviderRegistry.register
class WodkanKrzeszowiceProvider(WaterProvider):
    """Provider for WODKAN Krzeszowice (ibo.wikkrzeszowice.pl)."""

    BASE_URL = "https://ibo.wikkrzeszowice.pl/client"
    LOGIN_URL = "https://ibo.wikkrzeszowice.pl/client/Login.aspx"

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(
            id="wik_krzeszowice",
            name="WODKAN Krzeszowice",
            description="Wodociągi i Kanalizacja Krzeszowice",
        )

    def __init__(self, client_code: str, password: str):
        self.client_code = client_code
        self.password = password
        self._cookies: dict = {}

    def login(self) -> bool:
        """Login to WODKAN IBO using HTTP requests."""
        client = httpx.Client(
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )

        try:
            response = client.get(self.LOGIN_URL)

            form_data = {}
            for inp in re.findall(r'<input[^>]*>', response.text):
                name_match = re.search(r'name="([^"]+)"', inp)
                value_match = re.search(r'value="([^"]*)"', inp)
                if name_match:
                    form_data[name_match.group(1)] = value_match.group(1) if value_match else ""

            form_data["tbUserName"] = self.client_code
            form_data["tbUserName_I"] = self.client_code
            form_data["tbPassword"] = self.password
            form_data["tbPassword_I"] = self.password
            form_data["btLogin"] = "Zaloguj"

            response = client.post(self.LOGIN_URL, data=form_data)

            self._cookies = {k: v for k, v in client.cookies.items()}
            client.close()

            return len(self._cookies) > 0

        except Exception:
            client.close()
            return False

    def _get_meter_ids(self) -> List[tuple]:
        """Get list of (id, meter_number) from the portal."""
        if not self._cookies:
            if not self.login():
                return []

        client = httpx.Client(cookies=self._cookies, follow_redirects=True)

        try:
            response = client.get(f"{self.BASE_URL}/FormularzZgloszeniaWybor.aspx")
            text = response.text

            # Parse itemsInfo to get meter IDs and numbers
            # Format: {'value':'17441','text':'[412/119-01] Rozliczany przez: Wodomierz Nr: 8SEN0122012166 ...'}
            # Use simpler pattern to extract value and meter number
            result = []

            # Find all meter entries
            entries = re.findall(r"\{'value':'([^']+)',text:'.*?Nr:\s*([A-Z0-9]+)", text)
            for meter_id, meter_num in entries:
                result.append((meter_id, meter_num))

            # If above didn't work, try alternative
            if not result:
                # Try extracting ID and full text then parse
                id_matches = re.findall(r"'value':'(\d+)','text':'.*?Nr:\s*([A-Z0-9 ]+)", text)
                for meter_id, meter_num in id_matches:
                    result.append((meter_id, meter_num.replace(" ", "")))

            client.close()
            return result

        except Exception:
            client.close()
            return []

    def get_current_reading(self) -> Optional[WaterReading]:
        """Get the most recent water reading from the portal."""
        if not self._cookies:
            if not self.login():
                return None

        meter_ids = self._get_meter_ids()

        if not meter_ids:
            return None

        # Get reading from the first meter (or iterate all to find the latest)
        meter_id, meter_number = meter_ids[0]
        return self.get_current_reading_for_meter(meter_id)

    def get_current_reading_for_meter(self, meter_id: str) -> Optional[WaterReading]:
        """Get water reading for a specific meter ID."""
        if not self._cookies:
            if not self.login():
                return None

        client = httpx.Client(cookies=self._cookies, follow_redirects=True)

        try:
            response = client.get(f"{self.BASE_URL}/FormularzZgloszenia.aspx?id={meter_id}")
            text = response.text

            # Find meter number
            meter_num_match = re.search(r'XWodomierz.*?Nr:\s*([A-Z0-9]+)', text)
            meter_number = meter_num_match.group(1) if meter_num_match else meter_id

            # Find current reading
            current_match = re.search(r'XOdczytBiezacy.*?(\d{3,})', text)
            if not current_match:
                client.close()
                return None

            current_reading = int(current_match.group(1))

            # Find previous reading (if available)
            previous_match = re.search(r'XOdczytPoprzedni.*?(\d{3,})', text)
            previous_reading = int(previous_match.group(1)) if previous_match else 0

            consumption = current_reading - previous_reading if previous_reading > 0 else 0

            client.close()

            return WaterReading(
                timestamp=datetime.now(),
                current_reading=float(current_reading),
                previous_reading=float(previous_reading),
                consumption=float(consumption),
                meter_number=meter_number
            )

        except Exception:
            client.close()
            return None

    def get_account_balance(self) -> Optional[AccountBalance]:
        """Get account balance from the payments page."""
        if not self._cookies:
            if not self.login():
                return None

        client = httpx.Client(cookies=self._cookies, follow_redirects=True)

        try:
            response = client.get(f"{self.BASE_URL}/WszystkiePlatnosci.aspx")
            text = response.text

            saldo_match = re.search(r'Saldo[^0-9]*([\d]+,[\d]+)', text)
            if saldo_match:
                saldo_str = saldo_match.group(1).replace(' ', '').replace(',', '.')
                amount = float(saldo_str)

                status = "do zapłaty" if amount > 0 else "nadpłata"

                client.close()
                return AccountBalance(
                    amount=amount,
                    status=status,
                    meter_number=""
                )

            client.close()
            return None

        except Exception:
            client.close()
            return None
