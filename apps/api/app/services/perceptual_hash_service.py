import math
from pathlib import Path
from typing import Optional, Tuple
import imagehash
from PIL import Image, ImageOps, UnidentifiedImageError

from app.schemas.dataset import PerceptualHashAlgorithm


class PerceptualHashService:
    """
    Dedicated service for computing perceptual image hashes (pHash, dHash, aHash),
    calculating Hamming distances, and deriving normalized similarity scores.
    """

    SUPPORTED_ALGORITHMS = {
        PerceptualHashAlgorithm.PHASH: "pHash (perceptual discrete cosine transform hash)",
        PerceptualHashAlgorithm.DHASH: "dHash (gradient difference hash)",
        PerceptualHashAlgorithm.AHASH: "aHash (average pixel intensity hash)",
    }

    def preprocess_image(self, img: Image.Image) -> Image.Image:
        """
        Normalize image for deterministic perceptual hashing:
        1. Correct orientation using EXIF orientation tags.
        2. Convert palette (P) or RGBA/LA images to standardized RGB.
        3. Convert RGB to grayscale (L) if required.
        """
        # EXIF orientation normalization
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass  # Fall back to raw orientation if EXIF is malformed

        # Consistent mode handling
        if img.mode in ("RGBA", "LA"):
            # Composite transparent background onto neutral white
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "RGBA":
                bg.paste(img, mask=img.split()[3])
            else:
                bg.paste(img.convert("RGB"))
            return bg
        elif img.mode == "P":
            return img.convert("RGB")
        elif img.mode not in ("RGB", "L"):
            return img.convert("RGB")

        return img

    def compute_hash(
        self,
        file_path: Path,
        algorithm: PerceptualHashAlgorithm = PerceptualHashAlgorithm.PHASH,
        hash_size: int = 8,
    ) -> str:
        """
        Compute perceptual hash string (hex digest) for an image file.
        Preserves original image files (strictly read-only).
        """
        with Image.open(file_path) as raw_img:
            processed = self.preprocess_image(raw_img)

            if algorithm == PerceptualHashAlgorithm.PHASH:
                h = imagehash.phash(processed, hash_size=hash_size)
            elif algorithm == PerceptualHashAlgorithm.DHASH:
                h = imagehash.dhash(processed, hash_size=hash_size)
            elif algorithm == PerceptualHashAlgorithm.AHASH:
                h = imagehash.average_hash(processed, hash_size=hash_size)
            else:
                raise ValueError(f"Unsupported algorithm: {algorithm}")

            return str(h)

    def compute_hamming_distance(self, hash_a: str, hash_b: str) -> int:
        """
        Calculate bit-level Hamming distance between two perceptual hash hex strings.
        Validates hash lengths before comparison.
        """
        if len(hash_a) != len(hash_b):
            raise ValueError(
                f"Hash length mismatch: {len(hash_a)} chars vs {len(hash_b)} chars"
            )

        val_a = int(hash_a, 16)
        val_b = int(hash_b, 16)
        return (val_a ^ val_b).bit_count()

    def compute_similarity(
        self, hamming_distance: int, total_bits: int = 64
    ) -> float:
        """
        Derive normalized similarity score from Hamming distance.
        Formula: 1.0 - (hamming_distance / total_bits)
        Technical metric bounded strictly between 0.0 and 1.0.
        """
        if total_bits <= 0:
            return 0.0
        clamped_dist = max(0, min(hamming_distance, total_bits))
        return round(1.0 - (clamped_dist / total_bits), 4)


# Global singleton instance
perceptual_hash_service = PerceptualHashService()

