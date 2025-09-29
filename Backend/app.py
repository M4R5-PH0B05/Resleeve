import flask
from flask import Flask, render_template, request, redirect, url_for, session, flash
from api_testing import search_albums, get_tracklist, get_album_cover
from pprintpp import pprint
import io, base64
from barcode import UPCA, EAN13
from barcode.writer import ImageWriter
from sklearn.cluster import KMeans
import numpy as np
import ast
from matplotlib.colors import rgb_to_hsv
from collections import Counter
from PIL import Image
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.secret_key = 'Testing123!'


def fetch_single_cover(mbid):
    """Helper function to fetch a single cover art"""
    return mbid, get_album_cover(mbid)


# Creates a List of the Album Options based on the users search query.
def createList(album_list):
    # First pass: collect all release data without cover art
    releases_data = []

    for i, release in enumerate(album_list['releases']):
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
        try:
            barcode = release['barcode']
        except:
            barcode = "794558113229"
        try:
            format = release['media'][0]['format']
        except:
            format = None
        release_type = release['release-group']['primary-type']
        date = release.get('date')
        if date == None:
            date = release.get('release-events', [{}])[0].get('date')

        releases_data.append({
            'Artist': artist,
            'Title': title,
            'Country': country,
            'Track Count': track_count,
            'MBID': mbid,
            'Format': format,
            'Release Type': release_type,
            'Date': date,
            'Barcode': barcode
        })

    # Second pass: fetch all covers concurrently
    cover_results = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        # Submit all cover art requests
        future_to_mbid = {executor.submit(fetch_single_cover, release['MBID']): release for release in releases_data}

        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_mbid):
            mbid, cover_image = future.result()
            cover_results[mbid] = cover_image

    # Third pass: build final dictionary with covers, only including releases with cover art
    parsed_releases = {}
    count = 1

    for release in releases_data:
        mbid = release['MBID']
        cover_image = cover_results.get(mbid)

        if cover_image is not None:
            release['Cover Image'] = cover_image
            parsed_releases[count] = release
            count += 1

    return parsed_releases


def barcode_data_uri(code: str) -> str:
    fmt = UPCA if len(code) == 12 else EAN13
    writer = ImageWriter()
    opts = {
        "write_text": False,  # ← bars only, no numbers
        "quiet_zone": 0.0,  # minimal side margins
        "module_width": 0.26,  # tweak thickness if needed
        "module_height": 7.0,  # tall; we'll fit it with CSS
        "dpi": 300,
        "background": (255, 250, 236)
    }
    buf = io.BytesIO()
    fmt(code, writer=writer).write(buf, opts)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def colourExtractor(data_uri, k_out=5, k_quant=48, max_side=300):
    """
    Returns 5 CSS hex colours highlighting prominent hues (accents included),
    not just the most common neutrals.
    Order: lightest, three mids, darkest (tweak at the end if you prefer).
    """
    # --- load from data URI ---
    b64 = data_uri.split(",", 1)[1]
    img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.LANCZOS)

    # --- quantize to reduce unique colours (stable & fast) ---
    q = img.quantize(colors=k_quant, method=Image.MEDIANCUT)
    palette = q.getpalette()[:k_quant * 3]
    palette = [tuple(palette[i:i + 3]) for i in range(0, len(palette), 3)]

    idxs = np.array(q.getdata(), dtype=np.int32)
    counts = Counter(idxs.tolist())

    # build (count, rgb) list (drop invalid indices)
    colors = [(n, palette[i]) for i, n in counts.items() if 0 <= i < len(palette)]

    if not colors:
        return ["#000000"] * k_out

    # --- compute saturation + luminance for each palette colour ---
    def luminance(rgb):
        r, g, b = [c / 255.0 for c in rgb]
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    rgbs = np.array([c for _, c in colors], dtype=np.float32) / 255.0
    sats = rgb_to_hsv(rgbs.reshape(-1, 1, 3)).reshape(-1, 3)[:, 1]  # S channel
    lums = np.array([luminance(c) for _, c in colors], dtype=np.float32)
    freqs = np.array([n for n, _ in colors], dtype=np.float32)

    # --- prominence score: frequency * (saturation boosted) ---
    # tweak exponents to taste; this strongly lifts vivid colours
    score = freqs * (0.25 + sats) ** 2.0

    # de-dup: skip very similar colours (Euclidean in RGB)
    def too_close(c, picked, thr=20):
        cr = np.array(c, dtype=np.int16)
        return any(np.linalg.norm(cr - np.array(p, dtype=np.int16)) < thr for p in picked)

    # always include darkest & lightest to anchor the palette
    rgb_list = [c for _, c in colors]
    darkest = rgb_list[int(np.argmin(lums))]
    lightest = rgb_list[int(np.argmax(lums))]

    # pick top by prominence (excluding extremes) with de-dup
    order = np.argsort(-score)
    picked = []
    for idx in order:
        c = colors[idx][1]
        if c == darkest or c == lightest:
            continue
        if too_close(c, picked + [darkest, lightest]):
            continue
        picked.append(c)
        if len(picked) >= max(0, k_out - 2):
            break

    # if not enough, backfill by frequency
    if len(picked) < max(0, k_out - 2):
        by_freq = np.argsort(-freqs)
        for idx in by_freq:
            c = colors[idx][1]
            if c in (darkest, lightest) or too_close(c, picked + [darkest, lightest]):
                continue
            picked.append(c)
            if len(picked) >= max(0, k_out - 2):
                break

    # final ordering: lightest, mids (by luminance), darkest
    mids = sorted(picked[:k_out - 2], key=lambda c: luminance(c))
    final = [lightest, *mids, darkest]

    # to CSS hex
    return [_hex(c) for c in final]


def _hex(rgb):
    r, g, b = map(int, rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def ms_to_min_sec(ms):
    total_seconds = ms // 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:02d}"


def createTracklist(json_tracklist):
    tracklist = {}
    release_length = 0
    max_sec = 1  # avoid divide-by-zero

    # first pass — collect seconds & find the max
    for item in json_tracklist:
        pos = int(item['position'])  # numeric sort later
        rec_len = item['recording'].get('length')  # ms or None

        if rec_len is None:
            length_str = 'N/A'
            seconds = None
        else:
            seconds = rec_len // 1000
            length_str = ms_to_min_sec(rec_len)
            release_length += rec_len
            if seconds > max_sec:
                max_sec = seconds

        tracklist[pos] = {
            'title': item['title'],
            'length': length_str,
            'seconds': seconds,
        }

    # second pass — percent relative to the longest track
    for v in tracklist.values():
        v['pct'] = 0 if v['seconds'] is None else (v['seconds'] / max_sec * 100)

    return tracklist, release_length


# Index Route
@app.route('/', methods=['GET', 'POST'])
def index():
    # Form Submission
    if request.method == 'POST':
        if 'selected_MBID' in request.form:
            selected_album_information = []
            selected_artist = request.form['selected_artist']
            selected_album = request.form['selected_album']
            selected_date = request.form['selected_date']
            selected_country = request.form['selected_country']
            selected_track_count = request.form['selected_track_count']
            selected_mbid = request.form['selected_MBID']
            selected_format = request.form['selected_format']
            selected_type = request.form['selected_type']
            selected_barcode = request.form['selected_barcode']
            selected_album_information.extend([
                selected_artist,
                selected_album,
                selected_date,
                selected_country,
                selected_track_count,
                selected_mbid,
                selected_format,
                selected_type,
                selected_barcode
            ])
            selected_cover_image = get_album_cover(selected_mbid)
            json_tracklist = get_tracklist(selected_mbid).json()
            # pprint(json_tracklist)
            tracklist, release_length = createTracklist(json_tracklist['media'][0]['tracks'])
            return render_template('index.html',
                                   selected_cover_image=selected_cover_image,
                                   selected_artist=selected_artist,
                                   selected_album=selected_album,
                                   selected_country=selected_country,
                                   selected_track_count=selected_track_count,
                                   selected_mbid=selected_mbid, tracklist=tracklist,
                                   selected_details=selected_album_information)
        if 'selected_details' in request.form:
            selected_details = request.form['selected_details']
            details = ast.literal_eval(selected_details)
            json_tracklist = get_tracklist(details[5]).json()
            cover_image = get_album_cover(details[5])
            # pprint(json_tracklist)
            tracklist, release_length = createTracklist(json_tracklist['media'][0]['tracks'])
            colours = colourExtractor(cover_image)
            return render_template('desktop-white.html', artist=details[0], album=details[1],
                                   date=details[2], country=details[3], track_count=details[4], format=details[6],
                                   type=details[7],
                                   barcode_src=barcode_data_uri(details[8]), cover_image=cover_image,
                                   run_time=ms_to_min_sec(release_length), tracklist=tracklist, colours=colours)


        else:
            # Get details from form
            artist = request.form['artist']
            album = request.form['album']
            # Create new API instance
            album_list = search_albums(artist, album).json()
            # Create dictionary of results through parsing JSON data
            # pprint(album_list)
            parsed_albums = createList(album_list)
            return render_template('index.html', releases=parsed_albums)

    return render_template('index.html')


@app.route('/template')
def template():
    pass


if __name__ == '__main__':
    app.run(debug=True)