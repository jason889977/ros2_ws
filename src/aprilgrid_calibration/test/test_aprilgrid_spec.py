import math

from aprilgrid_calibration.spec import AprilGridSpec


def test_aprilgrid_spec_matches_latest_requirements():
    spec = AprilGridSpec(
        rows=4,
        cols=3,
        tag_size_m=0.05,
        tag_spacing_m=0.01,
        tag_family='tag36h11',
    )

    assert spec.tag_family == 'tag36h11'
    assert spec.rows == 4
    assert spec.cols == 3
    assert spec.tag_size_m == 0.05
    assert spec.tag_spacing_m == 0.01
    assert spec.num_tags == 12
    assert spec.tag_ids == list(range(12))
    assert math.isclose(spec.tag_center_spacing_m, 0.06, rel_tol=1e-9)
    assert len(spec.tag_corner_points(0)) == 4
    assert spec.tag_corner_points(0)[0].tolist() == [0.0, 0.0, 0.0]
