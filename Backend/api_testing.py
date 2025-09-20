# IMPORTS
import requests
import json
import pprintpp
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





class request:
    def __init__(self):
        self.url = 'https://musicbrainz.org/ws/2/release'
        self.headers = {'User-Agent': 'Resleeve/1.0'}

    def searchAlbums(self,artist,album):
        return requests.get(self.url,headers=self.headers,params={"query": f"release:'{album}' AND "
                                                                                    f"artist:'{artist}'",
                                                                           "fmt": "json"})
    def getTracklist(self,MBID):
        lookup_url = f"{self.url}/{MBID}"
        return requests.get(lookup_url,headers=self.headers,params={"fmt":"json","inc":"recordings"})


# MAIN BODY

test = request()
# response = test.searchAlbums("Bring Me The Horizon","Sempiternal")
response = test.getTracklist('ace8eb0b-888e-4156-a922-87ad1e6ce290')
pprintpp.pprint(response.json())