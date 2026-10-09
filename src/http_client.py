"""
HTTP client for TCGCSV.

Single point of access to the TCGCSV API. All requests go through here.
Handles User-Agent (required by TCGCSV), rate limiting, and timeouts.
"""

import logging
import time
import requests

from src import config

logger = logging.getLogger(__name__)


class TCGCSVClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": config.USER_AGENT})

    def _get(self, path: str) -> requests.Response:
        url = config.BASE_URL + path
        logger.info("GET %s", url)
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        time.sleep(config.REQUEST_DELAY_SECONDS)
        return response

    def fetch_text(self, path: str) -> str:
        return self._get(path).text

    def fetch_json(self, path: str) -> dict:
        return self._get(path).json()