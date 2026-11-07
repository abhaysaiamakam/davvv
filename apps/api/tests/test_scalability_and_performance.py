"""
Tests for CropLens Scalability, Memory-Efficient Processing & Performance Enhancements.
"""
from __future__ import annotations

import io
import zipfile
import pytest
from pathlib import Path

from app.services.tabular_engine import tabular_engine
from app.services.image_thumbnail_service import image_thumbnail_service
from app.services.upload_service import upload_service


def test_tabular_engine_scalability(tmp_path):
    """Verify DuckDB / streaming tabular engine statistics and row sampling."""
    csv_file = tmp_path / "large_mock.csv"
    lines = ["id,val_a,val_b"]
    for i in range(1, 2000):
        lines.append(f"{i},{i * 1.5},{i * 2.0}")
    csv_file.write_text("\n".join(lines), encoding="utf-8")

    # Row count
    assert tabular_engine.get_row_count(csv_file) == 1999

    # Headers
    headers = tabular_engine.get_column_headers(csv_file)
    assert headers == ["id", "val_a", "val_b"]

    # Exact stats
    stats = tabular_engine.compute_exact_column_stats(csv_file)
    assert stats["total_rows"] == 1999
    assert "val_a" in stats["columns"]
    assert stats["columns"]["val_a"]["mean"] is not None

    # Sampling
    samples, is_exact, total = tabular_engine.sample_rows(csv_file, sample_limit=50)
    assert len(samples) <= 50
    assert total == 1999


def test_image_thumbnail_generation(tmp_path):
    """Verify on-demand thumbnail generation and caching."""
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    img_path = img_dir / "sample.jpg"

    from PIL import Image as PILImage
    img = PILImage.new("RGB", (1200, 800), color=(100, 150, 200))
    img.save(img_path, format="JPEG")

    thumb_path, mime = image_thumbnail_service.get_or_create_thumbnail(
        dataset_root=tmp_path,
        relative_image_path="images/sample.jpg",
        max_dim=150,
    )
    assert thumb_path.is_file()
    assert mime == "image/jpeg"

    with PILImage.open(thumb_path) as thumb:
        w, h = thumb.size
        assert w <= 150 and h <= 150


def test_upload_service_compression_ratio_safeguard(tmp_path):
    """Verify zip bomb protection rejecting high compression ratios."""
    zip_path = tmp_path / "bomb.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # Create a large uncompressed payload stream with small compression
        large_data = b"A" * (15 * 1024 * 1024)  # 15 MB
        zf.writestr("large_payload.csv", large_data)

    target_dir = tmp_path / "extracted"
    with pytest.raises(Exception):
        upload_service.extract_archive(zip_path, target_dir)
