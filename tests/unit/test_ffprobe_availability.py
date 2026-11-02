import pytest

from ayon_server.helpers.ffprobe import availability_from_media_info


def video_info(codec: str, **overrides):
    info = {
        "videoTrackIndex": 0,
        "duration": 10.0,
        "codec": codec,
        "majorBrand": "isom",
        "iframeOnly": True,
    }
    info.update(overrides)
    return info


@pytest.mark.parametrize("codec", ["h264", "vp9", "av1"])
def test_browser_codecs_are_ready(codec):
    assert availability_from_media_info(video_info(codec)) == "ready"


@pytest.mark.parametrize("codec", ["prores", "hevc", "dnxhd"])
def test_other_codecs_require_conversion(codec):
    assert availability_from_media_info(video_info(codec)) == "conversionRequired"


def test_av1_without_major_brand_is_ready():
    # webm files report no major brand
    info = video_info("av1", majorBrand=None)
    assert availability_from_media_info(info) == "ready"


def test_av1_with_inter_frames_recommends_conversion():
    info = video_info("av1", iframeOnly=False)
    assert availability_from_media_info(info) == "conversionRecommended"
