from flask import Flask, render_template, request
from api_testing import search_albums, get_tracklist, get_album_cover

# from pprintpp import pprint
import io
import base64
from barcode import UPCA, EAN13
from barcode.writer import ImageWriter
import numpy as np
import ast
from matplotlib.colors import rgb_to_hsv
from collections import Counter
from functools import wraps
import time
from PIL import Image
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures

app = Flask(__name__, template_folder="../templates", static_folder="../static")
app.secret_key = "Testing123!"

DEFAULT_COLOURS = ["#ffffff", "#d4d4d4", "#a0a0a0", "#6c6c6c", "#2c2c2c"]
TRANSPARENT_PIXEL = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8Xw8AAn8B9SClSxIAAAAASUVORK5CYII="
MAX_COVER_WORKERS = 10


def timeProgram(func):
    @wraps(func)
    def timeProgramWrapper(*args, **kwargs):
        startTime = time.perf_counter()
        result = func(*args, **kwargs)
        endTime = time.perf_counter()
        totalTime = endTime - startTime
        print(f"Function {func.__name__} Took {totalTime:.4f} seconds.")
        return result

    return timeProgramWrapper


@timeProgram
def fetch_single_cover(mbid):
    # Fetches a single album cover as opposed to multiple like the usual function
    try:
        return mbid, get_album_cover(mbid)
    except Exception:
        return mbid, None

@timeProgram
def hex_to_rgb(hex_color: str):
    if hex_color != "default":
        hex_color = hex_color.lstrip("#")  # remove '#' if present

        if len(hex_color) == 3:  # short form e.g. #FAB
            hex_color = "".join([c * 2 for c in hex_color])

        if len(hex_color) != 6:
            raise ValueError("Invalid HEX color format.")

        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)

        return (r, g, b)
    return None
# Creates a List of the Album Options based on the users search query.
@timeProgram
def createList(album_list):
    # First pass: collect all release data without cover art
    releases_data = []

    for i, release in enumerate(album_list["releases"]):
        # Set the variables based on the information in the JSON
        artist = release["artist-credit"][0]["name"]
        # Country can be found in two places
        country = release.get("country")
        # If not found above, then look for it in the other place
        if not country and "release-events" in release:
            for event in release["release-events"]:
                # Check release events
                if "area" in event and "iso-3166-1-codes" in event["area"]:
                    country = event["area"]["iso-3166-1-codes"][0]
                    break
        # Get other variables
        mbid = release["id"]
        track_count = release["track-count"]
        title = release["title"]
        # Some entries don't have these variables - make sure they do not raise a ValueError if they do not exist
        try:
            barcode = release["barcode"]
        except Exception:
            barcode = "794558113229"
        try:
            format = release["media"][0]["format"]
        except Exception:
            format = None
        release_type = release["release-group"]["primary-type"]
        # The date variable can be found in two different places - so check both
        date = release.get("date")
        if date is None:
            date = release.get("release-events", [{}])[0].get("date")

        # Create the dictionary of all of the album data
        releases_data.append(
            {
                "Artist": artist,
                "Title": title,
                "Country": country,
                "Track Count": track_count,
                "MBID": mbid,
                "Format": format,
                "Release Type": release_type,
                "Date": date,
                "Barcode": barcode,
            }
        )

    # Second pass: fetch all covers concurrently
    cover_results = {}
    with ThreadPoolExecutor(max_workers=MAX_COVER_WORKERS) as executor:
        # Submit all cover art requests
        future_to_mbid = {
            executor.submit(fetch_single_cover, release["MBID"]): release
            for release in releases_data
        }

        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_mbid):
            mbid, cover_image = future.result()
            cover_results[mbid] = cover_image

    # Third pass: build final dictionary with covers, only including releases with cover art
    parsed_releases = {}
    count = 1

    # for all of the releases
    for release in releases_data:
        mbid = release["MBID"]
        # get the cover image
        cover_image = cover_results.get(mbid)

        # if the cover image exists
        if cover_image:
            release["Cover Image"] = cover_image
            parsed_releases[count] = release
            count += 1

    return parsed_releases


# change the barcode string into an actual barcode
@timeProgram
def barcode_data_uri(code: str, type,background) -> str:
    # format it correctly ( adds a leading 0 )
    fmt = UPCA if len(code) == 12 else EAN13
    writer = ImageWriter()
    # customisation options for the final output image
    opts = {
        "write_text": False,  # ← bars only, no numbers
        "quiet_zone": 0.0,  # minimal side margins
        "module_width": 0.26,  # tweak thickness if needed
        "module_height": 7.0,  # tall; we'll fit it with CSS
        "dpi": 300,
    }
    if type == "white":
        if background != None:

            opts["background"] = background
        else:
            opts["background"] = "transparent"
            opts["background"] = (255, 250, 236)
    else:
        opts["foreground"] = (255, 255, 255)
        if background != None:
            opts["background"] = background
        else:
            opts["background"] = (0, 1, 10)

    # encodes the image to a base64 string
    buf = io.BytesIO()
    fmt(code, writer=writer).write(buf, opts)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


# extracts the 5 most prominent colours from the album cover
@timeProgram
def colourExtractor(data_uri, k_out=5, k_quant=48, max_side=300):
    if not data_uri or "," not in data_uri:
        return DEFAULT_COLOURS[:k_out]

    try:
        b64 = data_uri.split(",", 1)[1]
        img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
    except Exception:
        return DEFAULT_COLOURS[:k_out]

    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)

    # quantize to reduce unique colours (stable & fast)
    q = img.quantize(colors=k_quant, method=Image.Quantize.MEDIANCUT)

    pal = q.getpalette()
    if pal is None:
        # shouldn't happen after quantize, but keep it safe for Pyright & runtime
        return DEFAULT_COLOURS[:k_out]

    pal = pal[: k_quant * 3]  # take first k_quant colours (RGB triplets)
    palette = [tuple(pal[i : i + 3]) for i in range(0, len(pal), 3)]

    idxs = np.array(q.getdata(), dtype=np.int32)
    counts = Counter(idxs.tolist())

    # (count, rgb) list, dropping invalid indices
    colors = [(n, palette[i]) for i, n in counts.items() if 0 <= i < len(palette)]
    if not colors:
        return ["#000000"] * k_out

    def luminance(rgb):
        r, g, b = [c / 255.0 for c in rgb]
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    rgbs = np.array([c for _, c in colors], dtype=np.float32) / 255.0
    sats = rgb_to_hsv(rgbs.reshape(-1, 1, 3)).reshape(-1, 3)[:, 1]  # S channel
    lums = np.array([luminance(c) for _, c in colors], dtype=np.float32)
    freqs = np.array([n for n, _ in colors], dtype=np.float32)

    # prominence score: frequency * (saturation boosted)
    score = freqs * (0.25 + sats) ** 2.0

    def too_close(c, picked, thr=20):
        cr = np.array(c, dtype=np.int16)
        return any(
            np.linalg.norm(cr - np.array(p, dtype=np.int16)) < thr for p in picked
        )

    rgb_list = [c for _, c in colors]
    darkest = rgb_list[int(np.argmin(lums))]
    lightest = rgb_list[int(np.argmax(lums))]

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

    if len(picked) < max(0, k_out - 2):
        by_freq = np.argsort(-freqs)
        for idx in by_freq:
            c = colors[idx][1]
            if c in (darkest, lightest) or too_close(c, picked + [darkest, lightest]):
                continue
            picked.append(c)
            if len(picked) >= max(0, k_out - 2):
                break

    mids = sorted(picked[: max(0, k_out - 2)], key=lambda c: luminance(c))
    final = [lightest, *mids, darkest]
    return [_hex(c) for c in final]


# converts an rgb value to a hex value
@timeProgram
def _hex(rgb):
    r, g, b = map(int, rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


# converts ms to formatted minutes and seconds
@timeProgram
def ms_to_min_sec(ms):
    total_seconds = ms // 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:02d}"


# creates the formatted tracklist
@timeProgram
def createTracklist(json_tracklist):
    tracklist = {}
    release_length = 0
    max_sec = 1  # avoid divide-by-zero

    # first pass — collect seconds & find the max
    for item in json_tracklist:
        pos = int(item["position"])  # numeric sort later
        rec_len = item["recording"].get("length")  # ms or None

        # setting the length of the recording
        if rec_len is None:
            length_str = "N/A"
            seconds = None
        else:
            seconds = rec_len // 1000
            length_str = ms_to_min_sec(rec_len)
            release_length += rec_len
            if seconds > max_sec:
                max_sec = seconds

        tracklist[pos] = {
            "title": item["title"],
            "length": length_str,
            "seconds": seconds,
        }

    # second pass — percent relative to the longest track
    for v in tracklist.values():
        v["pct"] = 0 if v["seconds"] is None else (v["seconds"] / max_sec * 100)

    return tracklist, release_length


# Index Route
@app.route("/", methods=["GET", "POST"])
def index():
    # Form Submission
    if request.method == "POST":
        # If the FORM is the Initial Selection
        if "selected_MBID" in request.form:
            # Set variables that will be passed through
            selected_album_information = []
            selected_artist = request.form["selected_artist"]
            selected_album = request.form["selected_album"]
            selected_date = request.form["selected_date"]
            selected_country = request.form["selected_country"]
            selected_track_count = request.form["selected_track_count"]
            selected_mbid = request.form["selected_MBID"]
            selected_format = request.form["selected_format"]
            selected_type = request.form["selected_type"]
            selected_barcode = request.form.get("selected_barcode") or "794558113229"
            # Adds the variables to the list of album information
            selected_album_information.extend(
                [
                    selected_artist,
                    selected_album,
                    selected_date,
                    selected_country,
                    selected_track_count,
                    selected_mbid,
                    selected_format,
                    selected_type,
                    selected_barcode,
                ]
            )
            # dynamically load the album cover
            selected_cover_image = get_album_cover(selected_mbid)

            track_response = get_tracklist(selected_mbid)
            if track_response is not None:
                json_tracklist = track_response.json()
                tracklist, release_length = createTracklist(
                    json_tracklist["media"][0]["tracks"]
                )
            else:
                json_tracklist = None
                tracklist, release_length = {}, 0
            # return the index.html template but with the selected album on the right of the screen
            return render_template(
                "index.html",
                selected_cover_image=selected_cover_image,
                selected_artist=selected_artist,
                selected_album=selected_album,
                selected_country=selected_country,
                selected_track_count=selected_track_count,
                selected_mbid=selected_mbid,
                tracklist=tracklist,
                selected_details=selected_album_information,
            )
        # if the album has been fully selected
        if "selected_details" in request.form:
            # set variables
            selected_details = request.form["selected_details"]
            template_type = request.form["templateSelector"]

            details = ast.literal_eval(selected_details)
            track_response = get_tracklist(details[5])
            cover_image = get_album_cover(details[5])
            background_choice = request.form.get("backgroundSelector", "default")
            custom_background = request.form.get("custom", "").strip()
            if background_choice == "custom":
                background = custom_background or "default"
            else:
                background = background_choice or "default"
            # pprint(json_tracklist)
            if track_response is not None:
                json_tracklist = track_response.json()
                tracklist, release_length = createTracklist(
                    json_tracklist["media"][0]["tracks"]
                )
            else:
                json_tracklist = None
                tracklist, release_length = {}, 0
            if cover_image and cover_image.startswith("data:"):
                colours = colourExtractor(cover_image)
            else:
                colours = DEFAULT_COLOURS

            # return the template with the completed variables
            # print(cover_image)
            return render_template(
                f"desktop-{template_type}.html",
                artist=details[0],
                album=details[1],
                date=details[2],
                country=details[3],
                track_count=details[4],
                format=details[6],
                type=details[7],
                barcode_src=barcode_data_uri(details[8], template_type, hex_to_rgb(background)),
                cover_image=cover_image,
                run_time=ms_to_min_sec(release_length),
                tracklist=tracklist,
                colours=colours,
                background=background
            )

        else:
            # Get details from form
            artist = request.form["artist"]
            album = request.form["album"]
            # Create new API instance
            album_list = search_albums(artist, album).json()
            # Create dictionary of results through parsing JSON data
            # pprint(album_list)
            parsed_albums = createList(album_list)
            return render_template("index.html", releases=parsed_albums)
    # if no routes are matched, return default template
    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True,port=5001)
