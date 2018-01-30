import json
import math
import os
import sqlite3
import collections as col


def get_tile_box(zoom, x, y):
    """convert Google-style Mercator tile coordinate to
    (minlat, maxlat, minlng, maxlng) bounding box"""

    minlng, minlat = get_tile_lng_lat(zoom, x, y)
    maxlng, maxlat = get_tile_lng_lat(zoom, x + 1, y + 1)

    return (minlng, maxlng, minlat, maxlat)


def get_tile_lng_lat(zoom, x, y):
    """convert Google-style Mercator tile coordinate to
    (lng, lat) of top-left corner of tile"""

    # "map-centric" latitude, in radians:
    lat_rad = math.pi - 2*math.pi*y/(2**zoom)
    # true latitude:
    lat_rad = gudermannian(lat_rad)
    lat = lat_rad * 180.0 / math.pi

    # longitude maps linearly to map, so we simply scale:
    lng = -180.0 + 360.0*x/(2**zoom)

    return (lng, lat)


def get_lng_lat_tile(lng, lat, zoom):
    """convert lng/lat to Google-style Mercator tile coordinate (x, y)
    at the given zoom level"""

    lat_rad = lat * math.pi / 180.0
    # "map-centric" latitude, in radians:
    lat_rad = inv_gudermannian(lat_rad)

    x = 2**zoom * (lng + 180.0) / 360.0
    y = 2**zoom * (math.pi - lat_rad) / (2 * math.pi)

    return (x, y)


def gudermannian(x):
    return 2*math.atan(math.exp(x)) - math.pi/2


def inv_gudermannian(y):
    return math.log(math.tan((y + math.pi/2) / 2))


def get_tileset_info(tileset):
    if not os.path.isfile(tileset):
        return {
            'error': 'Tileset info is not available!'
        }

    db = sqlite3.connect(tileset)

    res = db.execute('SELECT * FROM tileset_info').fetchone()

    o = {
        'zoom_step': res[0],
        'tile_size': res[1],
        'max_zoom': res[2],
        'min_x': res[3],
        'max_x': res[4],
        'min_y': res[5],
        'max_y': res[6],
        'max_data_length': res[1] * 2 ** res[2],
    }

    return o


def get_tiles(db_file, zoom, x, y, width=1, height=1):
    '''
    Retrieve a contiguous set of tiles from a 2D db tile file.

    Parameters
    ----------
    db_file: str
        The filename of the sqlite db file
    zoom: int
        The zoom level
    x: int
        The x position of the first tile
    y: int
        The y position of the first tile
    width: int
        The width of the block of tiles to retrieve
    height: int
        The height of the block of tiles to retrieve

    Returns
    -------
    tiles: {pos: tile_value}
        A set of tiles, indexed by position
    '''
    conn = sqlite3.connect(db_file)

    c = conn.cursor()

    lng_from, _, lat_from, _ = get_tile_box(zoom, x, y)
    _, lng_to, _, lat_to = get_tile_box(zoom, x + width - 1, y + height - 1)

    query = '''
    SELECT
        minLng, maxLng, maxLat, minLat, uid, importance, geometry, properties
    FROM
        intervals,position_index
    WHERE
        intervals.id=position_index.id AND
        zoomLevel <= ? AND
        rMaxLng >= ? AND
        rMinLng <= ? AND
        rMaxLat <= ? AND
        rMinLat >= ?
    '''.format(zoom, lng_from, lng_to, lat_from, lat_to)

    rows = c.execute(
        query,
        (zoom, lng_from, lng_to, lat_from, lat_to)
    ).fetchall()

    new_rows = col.defaultdict(list)

    for r in rows:
        try:
            uid = r[4].decode('utf-8')
        except AttributeError:
            uid = r[4]

        x_start, y_start = get_lng_lat_tile(r[0], r[2], zoom)
        x_end, y_end = get_lng_lat_tile(r[1], r[3], zoom)

        try:
            geometry = json.loads(r[6])
        except Exception as e:
            geometry = None
            pass

        try:
            properties = json.loads(r[7])
        except Exception as e:
            properties = None
            pass

        for i in range(x, x + width):
            for j in range(y, y + height):
                # Add annotations to each tile in which they are visible
                if (
                    x_start < i + 1 and
                    x_end >= i and
                    y_start < j + 1 and
                    y_end >= j
                ):
                    # add the position offset to the returned values
                    new_rows[(i, j)] += [{
                        'xStart': r[0],
                        'xEnd': r[1],
                        'yStart': r[2],
                        'yEnd': r[3],
                        'importance': r[5],
                        'uid': uid,
                        'geometry': geometry,
                        'properties': properties,
                    }]
    conn.close()

    return new_rows
