import time
import requests

BASE_URL = "https://tcgcsv.com"
USER_AGENT = "SnapDex/0.1.0"

def fetch(path, as_json=False):
    url = BASE_URL + path
    headers = {"User-Agent": USER_AGENT}
    response = requests.get(url, headers=headers, timeout=30)
    time.sleep(0.1)
    if as_json:
        return response.json()
    return response.text