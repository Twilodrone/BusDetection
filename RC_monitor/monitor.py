import logging
import os
import time

import requests
import urllib3
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from Common.storage import DetectionStorage, LoopEvent, utc_now_iso_ms


def parse_cookies_from_browser(cookie_string: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for part in cookie_string.split(";"):
        token = part.strip()
        if "=" not in token:
            continue
        name, value = token.split("=", 1)
        if name.lower() in {"expires", "path", "domain", "httponly", "secure", "samesite"}:
            continue
        cookies[name] = value
    return cookies


class LoopControllerClient:
    def __init__(self, host: str, browser_cookies: str, timeout: int = 5) -> None:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self.host = host
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            }
        )
        for name, value in parse_cookies_from_browser(browser_cookies).items():
            self.session.cookies.set(name, value)

    def get_status(self) -> dict[str, str]:
        response = self.session.get(
            f"https://{self.host}/detectors/status", verify=False, timeout=self.timeout
        )
        response.raise_for_status()
        if "Авторизация" in response.text:
            raise RuntimeError("Контроллер запросил авторизацию: проверьте BROWSER_COOKIES")

        soup = BeautifulSoup(response.text, "html.parser")
        tbody = soup.find("tbody", {"id": "table_detectors"})
        if not tbody:
            raise RuntimeError("Не найдена таблица детекторов (tbody#table_detectors)")

        statuses: dict[str, str] = {}
        for row in tbody.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 4:
                continue
            det_id = cells[0].get_text(strip=True)
            span = cells[3].find("span", {"id": "det_status"})
            statuses[det_id] = span.get_text(strip=True) if span else "N/A"
        return statuses


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    controller_host = os.getenv("CONTROLLER_HOST")
    browser_cookies = os.getenv("BROWSER_COOKIES")
    db_path = os.getenv("DB_PATH", "data/detections.sqlite3")
    poll_interval_sec = float(os.getenv("LOOP_POLL_INTERVAL_SEC", "1"))

    if not controller_host or not browser_cookies:
        raise RuntimeError("Нужно задать CONTROLLER_HOST и BROWSER_COOKIES")

    client = LoopControllerClient(controller_host, browser_cookies)
    storage = DetectionStorage(db_path)

    logging.info("Loop monitor started")
    while True:
        started = time.time()
        ts_utc = utc_now_iso_ms()
        statuses = client.get_status()
        active_count = sum(1 for value in statuses.values() if value == "1")

        storage.insert_loop_event(
            LoopEvent(
                ts_utc=ts_utc,
                source_host=controller_host,
                active_count=active_count,
                values=statuses,
            )
        )
        logging.info("loop_active=%s total=%s", active_count, len(statuses))
        time.sleep(max(0.0, poll_interval_sec - (time.time() - started)))


if __name__ == "__main__":
    main()
