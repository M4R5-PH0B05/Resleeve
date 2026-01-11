import base64
import time
from functools import lru_cache

import requests
from requests import RequestException


'''
API INFORMATION
--
Requests are made via MBID ( Music Brainz IDs ). The general flow is that you do a search, find the match and then 
get its MBID. Future requests for any other extra information make use of the MBID after that.

Releases will be different based on different variables. Maybe these could be filter options eventually.
They are:
- Year
- Format ( CD, Vinyl, Digital )
- Country / Reigon
- Special Editions
- Label Differences

Basic API Call
--

https://musicbrainz.org/ws/2/release?query=release:"OK Computer"&fmt=json
'''

USER_AGENT = {'User-Agent': 'Resleeve/1.0 ( morganbennett100@gmail.com )'}
COVER_TIMEOUT = 5
TRACKLIST_TIMEOUT = 10
SUGGEST_TIMEOUT = 5
SUGGEST_LIMIT = 6


class CoverFetchError(Exception):
    """Raised when the cover art API cannot provide an image."""


class TracklistFetchError(Exception):
    """Raised when the tracklist API cannot provide data."""


class SearchAlbumsError(Exception):
    """Raised when album search fails entirely."""


def search_albums(artist, album):
    url = 'https://musicbrainz.org/ws/2/release'
    for attempt in range(3):
        try:
            response = requests.get(
                url,
                headers=USER_AGENT,
                params={
                    "query": f"release:'{album}' AND artist:'{artist}'",
                    "fmt": "json"
                },
                timeout=TRACKLIST_TIMEOUT,
            )
            if response.status_code == 200:
                return response.json()
            if 400 <= response.status_code < 500:
                raise SearchAlbumsError
        except RequestException as exc:
            if attempt == 2:
                raise SearchAlbumsError from exc
        time.sleep(0.5 * (attempt + 1))
    raise SearchAlbumsError


def _unique_first(items):
    seen = set()
    results = []
    for item in items:
        if not item:
            continue
        if item in seen:
            continue
        seen.add(item)
        results.append(item)
    return results


@lru_cache(maxsize=512)
def _fetch_artist_suggestions(query):
    url = 'https://musicbrainz.org/ws/2/artist'
    for attempt in range(3):
        try:
            response = requests.get(
                url,
                headers=USER_AGENT,
                params={
                    "query": f'artist:"{query}"',
                    "fmt": "json",
                    "limit": SUGGEST_LIMIT,
                },
                timeout=SUGGEST_TIMEOUT,
            )
            if response.status_code == 200:
                artists = response.json().get("artists", [])
                names = [artist.get("name") for artist in artists]
                return _unique_first(names)[:SUGGEST_LIMIT]
            if 400 <= response.status_code < 500:
                return []
        except RequestException:
            if attempt == 2:
                return []
        time.sleep(0.25 * (attempt + 1))
    return []


@lru_cache(maxsize=512)
def _fetch_album_suggestions(artist, query):
    url = 'https://musicbrainz.org/ws/2/release'
    for attempt in range(3):
        try:
            response = requests.get(
                url,
                headers=USER_AGENT,
                params={
                    "query": f'release:"{query}" AND artist:"{artist}"',
                    "fmt": "json",
                    "limit": SUGGEST_LIMIT,
                },
                timeout=SUGGEST_TIMEOUT,
            )
            if response.status_code == 200:
                releases = response.json().get("releases", [])
                titles = [release.get("title") for release in releases]
                return _unique_first(titles)[:SUGGEST_LIMIT]
            if 400 <= response.status_code < 500:
                return []
        except RequestException:
            if attempt == 2:
                return []
        time.sleep(0.25 * (attempt + 1))
    return []


def get_artist_suggestions(query):
    if not query:
        return []
    return _fetch_artist_suggestions(query)


def get_album_suggestions(artist, query):
    if not artist or not query:
        return []
    return _fetch_album_suggestions(artist, query)

# Get detailed tracklist and album info using MBID
@lru_cache(maxsize=256)
def _fetch_tracklist_json(mbid):
    url = f'https://musicbrainz.org/ws/2/release/{mbid}'
    for attempt in range(3):
        try:
            response = requests.get(
                url,
                headers=USER_AGENT,
                params={
                    "fmt": "json",
                    "inc": "recordings"
                },
                timeout=TRACKLIST_TIMEOUT
            )
            if response.status_code == 200:
                return response.json()
            if 400 <= response.status_code < 500:
                raise TracklistFetchError
        except RequestException as exc:
            if attempt == 2:
                raise TracklistFetchError from exc
        time.sleep(0.5 * (attempt + 1))
    raise TracklistFetchError


def get_tracklist(mbid):
    if not mbid:
        return None
    try:
        return _fetch_tracklist_json(mbid)
    except TracklistFetchError:
        return None

# Get album cover art as base64 encoded string
@lru_cache(maxsize=256)
def _fetch_cover_data(mbid):
    cover_url = f"https://coverartarchive.org/release/{mbid}/front"
    try:
        response = requests.get(cover_url, headers=USER_AGENT, timeout=COVER_TIMEOUT)
    except RequestException as exc:
        raise CoverFetchError from exc
    if response.status_code == 200:
        b64_image = base64.b64encode(response.content).decode('utf-8')
        content_type = response.headers.get('content-type', 'image/jpeg')
        return f"data:{content_type};base64,{b64_image}"
    raise CoverFetchError


def get_album_cover(mbid):
    if not mbid:
        return None
    try:
        return _fetch_cover_data(mbid)
    except CoverFetchError:
        return None

# print(search_albums("Bring me the horizon","Post Human: Survival Horror").json())
