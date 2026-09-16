import math
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class BboxTile:
    key: str
    west: float
    south: float
    east: float
    north: float


def subdivide_bbox(
    west: float, south: float, east: float, north: float, max_tiles: int = 144
) -> List[BboxTile]:
    width = max(east - west, 0.0001)
    height = max(north - south, 0.0001)
    ratio = width / height
    desired_tiles = min(max_tiles, max(1, int(math.ceil(width * height * 4))))
    columns = max(1, int(round(math.sqrt(desired_tiles * ratio))))
    columns = min(columns, desired_tiles)
    rows = max(1, int(math.ceil(desired_tiles / columns)))
    while columns * rows > max_tiles and rows > 1:
        rows -= 1
    columns = min(columns, 40)
    rows = min(rows, 40)
    step_x = width / columns
    step_y = height / rows
    tiles = []
    for row in range(rows):
        for column in range(columns):
            tile_west = west + column * step_x
            tile_south = south + row * step_y
            tiles.append(
                BboxTile(
                    key="r{:03d}c{:03d}".format(row, column),
                    west=tile_west,
                    south=tile_south,
                    east=east if column == columns - 1 else tile_west + step_x,
                    north=north if row == rows - 1 else tile_south + step_y,
                )
            )
    return tiles
