"""
Scalable Image Processing & On-Demand Thumbnail Service.

Provides thumbnail generation, disk caching, and bounded memory image inspection
for large image classification and annotation datasets.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image as PILImage

from app.core.config import settings
from app.core.errors import DatasetNotFoundError, InvalidDatasetStateError

logger = logging.getLogger(__name__)

# Enforce PIL safety limits against decompression bomb images
PILImage.MAX_IMAGE_PIXELS = settings.MAX_IMAGE_DECODE_PIXELS


class ImageThumbnailService:
    """Handles cached thumbnail creation and safe image rendering."""

    def get_or_create_thumbnail(
        self,
        dataset_root: Path,
        relative_image_path: str,
        max_dim: int = 300,
    ) -> Tuple[Path, str]:
        """
        Locate or generate a thumbnail image on disk.
        Returns tuple of (thumbnail_abs_path, mime_type).
        """
        clean_rel = relative_image_path.lstrip("/\\")
        image_path = (dataset_root / clean_rel).resolve()

        if not image_path.is_file() or dataset_root.resolve() not in image_path.parents:
            raise FileNotFoundError(f"Image '{relative_image_path}' not found in dataset root.")

        thumb_dir = dataset_root / ".thumbnails" / f"dim_{max_dim}"
        thumb_dir.mkdir(parents=True, exist_ok=True)

        thumb_filename = f"{image_path.stem}_{image_path.stat().st_size}_{max_dim}.jpg"
        thumb_path = thumb_dir / thumb_filename

        if thumb_path.exists() and thumb_path.stat().st_size > 0:
            return thumb_path, "image/jpeg"

        # Generate thumbnail
        try:
            with PILImage.open(image_path) as img:
                img = img.convert("RGB")
                img.thumbnail((max_dim, max_dim), PILImage.Resampling.LANCZOS)
                img.save(thumb_path, format="JPEG", quality=85, optimize=True)
            return thumb_path, "image/jpeg"
        except Exception as e:
            logger.error(f"Failed to generate thumbnail for '{relative_image_path}': {e}")
            raise InvalidDatasetStateError(f"Corrupted image file: {relative_image_path}")

    def inspect_image_metadata_safe(self, image_path: Path) -> Optional[dict]:
        """Header-only image inspection without decoding full pixel array into memory."""
        if not image_path.is_file():
            return None
        try:
            with PILImage.open(image_path) as img:
                width, height = img.size
                format_name = img.format or "UNKNOWN"
                mode = img.mode
                file_bytes = image_path.stat().st_size
                return {
                    "width": width,
                    "height": height,
                    "format": format_name,
                    "mode": mode,
                    "file_size": file_bytes,
                    "aspect_ratio": round(width / max(height, 1), 4),
                }
        except Exception:
            return None


image_thumbnail_service = ImageThumbnailService()
