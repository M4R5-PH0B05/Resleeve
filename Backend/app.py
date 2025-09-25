import flask
from flask import Flask, render_template, request, redirect, url_for, session, flash
from api_testing import search_albums,get_tracklist,get_album_cover
from pprintpp import pprint

app = Flask(__name__,template_folder='../templates', static_folder='../static')
app.secret_key = 'Testing123!'
# Creates a List of the Album Options based on the users search query.
def createList(album_list):
    # Create dictioanary that parsed releases will be storedin
    parsed_releases = {}
    # Loop through the json
    count = 1
    for i,release in enumerate(album_list['releases']):
        # Set the variables based on the information in the JSON
        artist = release['artist-credit'][0]['name']
        # Country can be found in two places
        country = release.get('country')
        # If not found above, then look for it in the other place
        if not country and 'release-events' in release:
            for event in release['release-events']:
                # Check release events
                if 'area' in event and 'iso-3166-1-codes' in event['area']:
                    country = event['area']['iso-3166-1-codes'][0]
                    break
        # Get other variables
        mbid = release['id']
        track_count = release['track-count']
        title = release['title']
        # Dynamically create dictionary with important information in
        cover_image = get_album_cover(mbid)
        if cover_image != None:
            parsed_releases[count] = {
                    'Artist': artist,
                    'Title': title,
                    'Country': country,
                    'Track Count': track_count,
                    'MBID': mbid,
                    'Cover Image': cover_image
            }
            count += 1
    # Return dictionary
    return parsed_releases


def ms_to_min_sec(ms):
    total_seconds = ms // 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:02d}"

def createTracklist(json_tracklist):
    tracklist = {}
    for item in json_tracklist:
        # # title, position, length
        tracklist[item['position']] = {
            'title': item['title'],
            'length': str(ms_to_min_sec(item['recording']['length']))
        }
    return tracklist


# Subprograms i need to write
# Get 5 most prominent colours from image
# Number to barcode
# Calculate longest track, and then work out percentage of each track compared to the longest track, then create a
# status bar based on these measurements
# Html Template Parser

# Index Route
@app.route('/',methods=['GET','POST'])
def index():
    # Form Submission
    if request.method == 'POST':
        if 'selected_MBID' in request.form:
            selected_artist = request.form['selected_artist']
            selected_album = request.form['selected_album']
            selected_country = request.form['selected_country']
            selected_track_count = request.form['selected_track_count']
            selected_mbid = request.form['selected_MBID']
            selected_cover_image = get_album_cover(selected_mbid)
            json_tracklist = get_tracklist(selected_mbid).json()
            pprint(json_tracklist)
            tracklist = createTracklist(json_tracklist['media'][0]['tracks'])
            return render_template('index.html',
                                   selected_cover_image=selected_cover_image,
                                   selected_artist=selected_artist,
                                   selected_album=selected_album,
                                   selected_country=selected_country,
                                   selected_track_count=selected_track_count,
                                   selected_mbid=selected_mbid,tracklist=tracklist)


        else:
            # Get details from form
            artist = request.form['artist']
            album = request.form['album']
            # Create new API instance
            album_list = search_albums(artist, album).json()
            # Create dictionary of results through parsing JSON data
            # pprint(album_list)
            pprint(album_list)
            parsed_albums = createList(album_list)
            return render_template('index.html', releases=parsed_albums)

    return render_template('index.html')

@app.route('/template')
def template():
    sample_tracklist = {
        1: {'title': 'Going Under', 'length': '3:34','date':'idk'},
        2: {'title': 'Bring Me to Life', 'length': '3:57'},
        3: {'title': "Everybody's Fool", 'length': '3:15'},
        4: {'title': 'My Immortal', 'length': '4:24'},
        5: {'title': 'Haunted', 'length': '3:06'},
        6: {'title': 'Tourniquet', 'length': '4:38'},
        7: {'title': 'Imaginary', 'length': '4:17'},
        8: {'title': 'Taking Over Me', 'length': '3:49'},
        9: {'title': 'Hello', 'length': '3:40'},
        10: {'title': 'My Last Breath', 'length': '4:07'},
        11: {'title': 'Whisper', 'length': '5:27'},
        12: {'title': 'My Immortal (Band Version)', 'length': '4:33'}
    }
    json_tracklist = get_tracklist("e7e0369a-3784-4934-9419-d21483e6168d").json()
    pprint(json_tracklist)
    tracklist = createTracklist(json_tracklist['media'][0]['tracks'])
    return render_template('desktop-white.html',tracklist=tracklist,artist="Bring Me The Horizon",album="Post Human: Survival Horror")
if __name__ == '__main__':
    app.run(debug=True)