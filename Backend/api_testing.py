# IMPORTS
import base64

import requests
from requests import RequestException
import json
import pprintpp
import time
# FUNCTIONS & CLASSES


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

# Search for album releases by artist and album name
def search_albums(artist, album):
    url = 'https://musicbrainz.org/ws/2/release'
    headers = {'User-Agent': 'Resleeve/1.0 ( morganbennett100@gmail.com )'}

    return requests.get(url, headers=headers, params={
        "query": f"release:'{album}' AND artist:'{artist}'",
        "fmt": "json"
    })

# Get detailed tracklist and album info using MBID
def get_tracklist(mbid):
    url = f'https://musicbrainz.org/ws/2/release/{mbid}'
    headers = {'User-Agent': 'Resleeve/1.0 ( morganbennett100@gmail.com )' }

    for attempt in range(3):
        try:
            response = requests.get(
                url,
                headers=headers,
                params={
                    "fmt": "json",
                    "inc": "recordings"
                },
                timeout=10
            )
            if response.status_code == 200:
                return response
            if 400 <= response.status_code < 500:
                return None
        except RequestException:
            if attempt == 2:
                return None
        time.sleep(0.5 * (attempt + 1))
    return None

# Get album cover art as base64 encoded string
def get_album_cover(mbid):
    cover_url = f"https://coverartarchive.org/release/{mbid}/front"
    headers = {'User-Agent': 'Resleeve/1.0 ( morganbennett100@gmail.com )' }

    for attempt in range(3):
        try:
            response = requests.get(cover_url, headers=headers, timeout=10)
        except RequestException:
            if attempt == 2:
                return None
        else:
            if response.status_code == 200:
                b64_image = base64.b64encode(response.content).decode('utf-8')
                content_type = response.headers.get('content-type', 'image/jpeg')
                return f"data:{content_type};base64,{b64_image}"
            if 400 <= response.status_code < 500:
                return None
        time.sleep(0.5 * (attempt + 1))
    return None


# print(search_albums("Bring me the horizon","Post Human: Survival Horror").json())
