from app.db.models.asset_hub import AssetType
from app.services.crawler.service import CrawlerResult, crawler_result_asset_type


def _result(**overrides):
    return CrawlerResult(id="result-1", platform="canvas", **overrides)


def test_crawler_import_uses_semantic_asset_types():
    assert crawler_result_asset_type(_result(type="image", images=["https://example.test/cover.png"])) == AssetType.IMAGE
    assert crawler_result_asset_type(_result(type="article")) == AssetType.TEXT
    assert crawler_result_asset_type(_result(type="audio")) == AssetType.AUDIO
    assert crawler_result_asset_type(_result(type="video", video_url="https://example.test/video.mp4")) == AssetType.VIDEO


def test_crawler_import_treats_image_collections_as_images_without_an_explicit_type():
    assert crawler_result_asset_type(_result(images=["https://example.test/image.jpg"])) == AssetType.IMAGE