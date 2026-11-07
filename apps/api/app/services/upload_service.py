"""
M6 — Upload & Archive Processing Service.

Provides secure, resource-bounded extraction of evaluator dataset archives (.zip, .tar, .tar.gz),
deterministic content fingerprinting, and path traversal protection.
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set, Tuple

from app.core.config import settings
from app.core.errors import (
    ArchiveExtractionError,
    ArchiveSecurityError,
    InvalidArchiveError,
    PayloadTooLargeError,
)

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    target_dir: Path
    total_files: int
    total_bytes: int
    archive_format: str
    warnings: List[str]


class UploadService:
    """Service handling file upload validation, archive decompression, and content fingerprinting."""

    def __init__(self):
        self.max_upload_bytes = settings.MAX_UPLOAD_SIZE_BYTES
        self.max_extract_bytes = settings.MAX_EXTRACT_SIZE_BYTES
        self.max_files = settings.MAX_ARCHIVE_FILES

    def validate_filename(self, filename: str) -> str:
        """Validate archive file extension and return normalized format ('zip', 'tar', 'tar.gz')."""
        fn_lower = filename.lower()
        if fn_lower.endswith(".zip"):
            return "zip"
        elif fn_lower.endswith(".tar.gz") or fn_lower.endswith(".tgz"):
            return "tar.gz"
        elif fn_lower.endswith(".tar"):
            return "tar"
        else:
            raise InvalidArchiveError(
                f"Unsupported archive format for '{filename}'. Supported formats: .zip, .tar, .tar.gz, .tgz"
            )

    def extract_archive(self, archive_path: Path, target_dir: Path) -> ExtractionResult:
        """
        Safely extract archive contents to target_dir.
        Enforces path containment, prevents symlink escapes, and guards against decompression bombs.
        """
        if not archive_path.is_file():
            raise InvalidArchiveError(f"Uploaded archive file not found: {archive_path.name}")

        fmt = self.validate_filename(archive_path.name)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_resolved = target_dir.resolve()

        if fmt == "zip":
            return self._extract_zip(archive_path, target_resolved)
        else:
            return self._extract_tar(archive_path, target_resolved, fmt)

    def _extract_zip(self, archive_path: Path, target_resolved: Path) -> ExtractionResult:
        """Secure ZIP extraction with quota enforcement and directory traversal prevention."""
        warnings: List[str] = []
        total_extracted_bytes = 0
        total_files = 0

        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                # First pass: check file count and test archive integrity
                infolist = zf.infolist()
                if len(infolist) > self.max_files:
                    raise PayloadTooLargeError(
                        f"Archive file count ({len(infolist)}) exceeds maximum allowed ({self.max_files})."
                    )

                for member in infolist:
                    # Detect path traversal
                    member_path = member.filename
                    if member_path.startswith("/") or ".." in member_path.split("/"):
                        raise ArchiveSecurityError(
                            f"Archive member contains forbidden path traversal: '{member_path}'"
                        )

                    dest_path = (target_resolved / member_path).resolve()
                    if target_resolved != dest_path and target_resolved not in dest_path.parents:
                        raise ArchiveSecurityError(
                            f"Archive path escapes target directory: '{member_path}'"
                        )

                    # Accumulate uncompressed size check and ratio check
                    total_extracted_bytes += member.file_size
                    comp_ratio = member.file_size / max(member.compress_size, 1)
                    if comp_ratio > 100 and member.file_size > 10 * 1024 * 1024:
                        raise PayloadTooLargeError(
                            f"Compression ratio limit exceeded for '{member_path}' (ratio {comp_ratio:.1f}x > 100x)."
                        )

                    if total_extracted_bytes > self.max_extract_bytes:
                        raise PayloadTooLargeError(
                            f"Uncompressed archive size exceeds limit ({self.max_extract_bytes / (1024**3):.1f} GB)."
                        )

                    # Extract file or directory
                    if member.is_dir():
                        dest_path.mkdir(parents=True, exist_ok=True)
                    else:
                        dest_path.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(member) as source, open(dest_path, "wb") as target:
                            shutil.copyfileobj(source, target)
                        total_files += 1

        except zipfile.BadZipFile as exc:
            raise InvalidArchiveError(f"Malformed or corrupt ZIP file: {exc}")
        except (ArchiveSecurityError, PayloadTooLargeError):
            # Clean up partial extraction on security/quota failure
            shutil.rmtree(target_resolved, ignore_errors=True)
            raise
        except Exception as exc:
            shutil.rmtree(target_resolved, ignore_errors=True)
            raise ArchiveExtractionError(str(exc))

        return ExtractionResult(
            target_dir=target_resolved,
            total_files=total_files,
            total_bytes=total_extracted_bytes,
            archive_format="zip",
            warnings=warnings,
        )

    def _extract_tar(
        self, archive_path: Path, target_resolved: Path, fmt: str
    ) -> ExtractionResult:
        """Secure TAR extraction with quota enforcement and symlink verification."""
        warnings: List[str] = []
        total_extracted_bytes = 0
        total_files = 0
        mode = "r:gz" if "gz" in fmt else "r:"

        try:
            with tarfile.open(archive_path, mode) as tf:
                members = tf.getmembers()
                if len(members) > self.max_files:
                    raise PayloadTooLargeError(
                        f"Archive file count ({len(members)}) exceeds limit ({self.max_files})."
                    )

                for member in members:
                    name = member.name
                    if name.startswith("/") or ".." in name.split("/"):
                        raise ArchiveSecurityError(
                            f"Archive member contains forbidden path traversal: '{name}'"
                        )

                    dest_path = (target_resolved / name).resolve()
                    if target_resolved != dest_path and target_resolved not in dest_path.parents:
                        raise ArchiveSecurityError(
                            f"Archive path escapes target directory: '{name}'"
                        )

                    # Check symlink destination
                    if member.issym() or member.islnk():
                        link_target = (dest_path.parent / member.linkname).resolve()
                        if target_resolved != link_target and target_resolved not in link_target.parents:
                            warnings.append(f"Skipped unsafe symlink escaping dataset root: {name}")
                            continue

                    total_extracted_bytes += member.size
                    if total_extracted_bytes > self.max_extract_bytes:
                        raise PayloadTooLargeError(
                            f"Uncompressed archive size exceeds limit ({self.max_extract_bytes / (1024**3):.1f} GB)."
                        )

                    if member.isdir():
                        dest_path.mkdir(parents=True, exist_ok=True)
                    elif member.isfile():
                        dest_path.parent.mkdir(parents=True, exist_ok=True)
                        extracted = tf.extractfile(member)
                        if extracted:
                            with open(dest_path, "wb") as target:
                                shutil.copyfileobj(extracted, target)
                        total_files += 1

        except tarfile.TarError as exc:
            raise InvalidArchiveError(f"Malformed or corrupt TAR file: {exc}")
        except (ArchiveSecurityError, PayloadTooLargeError):
            shutil.rmtree(target_resolved, ignore_errors=True)
            raise
        except Exception as exc:
            shutil.rmtree(target_resolved, ignore_errors=True)
            raise ArchiveExtractionError(str(exc))

        return ExtractionResult(
            target_dir=target_resolved,
            total_files=total_files,
            total_bytes=total_extracted_bytes,
            archive_format=fmt,
            warnings=warnings,
        )

    def compute_content_fingerprint(self, dataset_dir: Path) -> str:
        """
        Compute a deterministic SHA-256 fingerprint for all dataset contents.
        Traverses directory tree, sorts relative paths, and digests paths + file sizes + byte hashes.
        Two datasets with identical files in identical structures produce identical fingerprints.
        """
        hasher = hashlib.sha256()
        file_entries: List[Tuple[str, int, str]] = []

        for root, _, files in os.walk(str(dataset_dir), followlinks=False):
            for fname in files:
                if fname.startswith(".") or fname.lower() in ("thumbs.db", "desktop.ini"):
                    continue
                fpath = Path(root) / fname
                try:
                    rel = str(fpath.relative_to(dataset_dir)).replace("\\", "/")
                    fsize = fpath.stat().st_size

                    # Hash file content in streaming chunks (4KB)
                    f_hash = hashlib.sha256()
                    with open(fpath, "rb") as f:
                        for chunk in iter(lambda: f.read(65536), b""):
                            f_hash.update(chunk)
                    file_entries.append((rel, fsize, f_hash.hexdigest()))
                except OSError:
                    continue

        # Deterministic sorting by relative path
        file_entries.sort(key=lambda x: x[0])

        for rel, size, digest in file_entries:
            hasher.update(rel.encode("utf-8"))
            hasher.update(str(size).encode("utf-8"))
            hasher.update(digest.encode("utf-8"))

        return hasher.hexdigest()


# Global upload service singleton
upload_service = UploadService()

