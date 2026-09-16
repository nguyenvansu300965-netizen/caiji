from src.services.partition import subdivide_bbox


def test_partition_covers_bbox_without_exceeding_limit():
    tiles = subdivide_bbox(10.0, 20.0, 14.0, 22.0, max_tiles=20)
    assert 1 < len(tiles) <= 20
    assert min(tile.west for tile in tiles) == 10.0
    assert max(tile.east for tile in tiles) == 14.0
    assert min(tile.south for tile in tiles) == 20.0
    assert max(tile.north for tile in tiles) == 22.0
    assert len({tile.key for tile in tiles}) == len(tiles)


def test_small_area_does_not_create_hundreds_of_tiles():
    tiles = subdivide_bbox(113.8, 22.1, 114.5, 22.6, max_tiles=144)
    assert len(tiles) <= 4
