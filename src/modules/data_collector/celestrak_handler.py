import json
import pathlib
import requests
from typing import Dict, Any, List, Optional
from src.core.datatypes import SatelliteConfig

__all__ = ["fetch_celestrak_metadata", "fetch_group_from_celestrak"]

CELESTRAK_GP_URL = "https://celestrak.org/NORAD/elements/gp.php"
CACHE_DIR = pathlib.Path("data/cache")

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/plain, text/html, application/xhtml+xml, application/xml;q=0.9, image/webp, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5"
}


def _load_cached_group(cache_path: pathlib.Path) -> List[SatelliteConfig]:
    """
    Deserializes a local JSON cache file containing standard orbital metadata parameters.

    Args:
        cache_path: Path object pointing to the local fallback JSON file registry.

    Returns:
        A list of pre-cached SatelliteConfig data objects representing known assets.
    """
    satellites = []
    try:
        with cache_path.open("r", encoding="utf-8") as f:
            cached_data = json.load(f)
            for sat in cached_data:
                satellites.append(
                    SatelliteConfig(
                        norad_id=sat["norad_id"],
                        name=sat["name"],
                        tle_line1=sat["tle_line1"],
                        tle_line2=sat["tle_line2"]
                    )
                )
    except (json.JSONDecodeError, KeyError):
        pass
    return satellites


def fetch_celestrak_metadata(norad_id: int) -> Optional[Dict[str, Any]]:
    """
    Queries CelesTrak's General Perturbations (GP) API to retrieve TLE data for a single asset.

    Args:
        norad_id: The unique five-digit catalog tracking number assigned by NORAD.

    Returns:
        A dictionary containing parsed metadata strings (norad_id, name, tle_line1, tle_line2) 
        if the request succeeds, or None if network errors or missing entries are encountered.
    """
    url = f"{CELESTRAK_GP_URL}?CATNR={norad_id}&FORMAT=2LE"
    try:
        response = requests.get(url, headers=HTTP_HEADERS, timeout=10)
        if response.status_code == 200:
            lines = [line.strip() for line in response.text.splitlines() if line.strip()]
            if len(lines) == 2 and lines[0].startswith("1 ") and lines[1].startswith("2 "):
                return {
                    "norad_id": norad_id,
                    "name": f"NORAD_{norad_id}",
                    "tle_line1": lines[0],
                    "tle_line2": lines[1]
                }
            if len(lines) >= 3:
                return {
                    "norad_id": norad_id,
                    "name": lines[0],
                    "tle_line1": lines[1],
                    "tle_line2": lines[2]
                }
    except requests.RequestException:
        pass
    return None


def fetch_group_from_celestrak(group_name: str) -> List[SatelliteConfig]:
    """
    Retrieves a complete constellation group file from CelesTrak with internal JSON caching.

    Attempts to pull raw multi-line TLE element structures from external servers. If the 
    request succeeds, it rebuilds a local JSON payload cache and streams parsed satellite 
    configurations. In the case of HTTP network blocks, timeouts, or 403 authorization failures, 
    it falls back dynamically to the local cache registry.

    Args:
        group_name: Target constellation string tag corresponding to CelesTrak's text endpoint.

    Returns:
        A list of fully configured SatelliteConfig instances matching the requested orbital group.

    Raises:
        ConnectionError: If live synchronization protocols fail and no valid local JSON 
            backup file can be read from the environment cache path.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"celestrak_{group_name}.json"
    url = f"https://celestrak.org/NORAD/elements/{group_name}.txt"
    satellites = []

    try:
        response = requests.get(url, headers=HTTP_HEADERS, timeout=15)
        if response.status_code == 200:
            raw_lines = response.text.splitlines()
            i = 0
            payload_to_cache = []
            
            while i < len(raw_lines):
                line = raw_lines[i].strip()
                if not line:
                    i += 1
                    continue
                    
                if not line.startswith("1 ") and not line.startswith("2 ") and (i + 2 < len(raw_lines)):
                    name = line
                    l1 = raw_lines[i+1].strip()
                    l2 = raw_lines[i+2].strip()
                    
                    if l1.startswith("1 ") and l2.startswith("2 "):
                        try:
                            nid = int(l1[2:7])
                            satellites.append(
                                SatelliteConfig(
                                    norad_id=nid,
                                    name=name,
                                    tle_line1=l1,
                                    tle_line2=l2
                                )
                            )
                            payload_to_cache.append({
                                "norad_id": nid,
                                "name": name,
                                "tle_line1": l1,
                                "tle_line2": l2
                            })
                        except ValueError:
                            pass
                    i += 3
                else:
                    i += 1
            
            if payload_to_cache:
                with cache_path.open("w", encoding="utf-8") as f:
                    json.dump(payload_to_cache, f, indent=2, ensure_ascii=False)
                return satellites

    except requests.RequestException:
        print(f"[CACHE FALLBACK] Network constraints or 403 detected. Loading static backup JSON for group: '{group_name}'")
        if cache_path.exists():
            satellites = _load_cached_group(cache_path)
            if satellites:
                return satellites

    if cache_path.exists():
        satellites = _load_cached_group(cache_path)
        if satellites:
            return satellites

    raise ConnectionError(f"Failed to fetch fresh data and no valid local JSON cache found at {cache_path.resolve()}")