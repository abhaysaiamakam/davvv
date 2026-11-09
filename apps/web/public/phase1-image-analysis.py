#!/usr/bin/env python3
"""Reproducible inventory, image EDA, exact-duplicate scan, and color-histogram PCA.

This standalone script inspects an image dataset ZIP without changing it. Folder names
are reported as observed labels; the script does not rename or infer disease identity.
It is a local reproducibility tool, separate from CropLens's production analysis API.

Requirements: Python 3.10+, Pillow, NumPy. SVG charts use only the Python standard library.
Example: python phase1-image-analysis.py Rice_and_Maize_Dataset.zip --output analysis-output
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import zipfile
from collections import Counter, defaultdict
from pathlib import PurePosixPath
from typing import Any
from xml.sax.saxutils import escape

import numpy as np
from PIL import Image, UnidentifiedImageError

SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff", ".webp", ".jfif"}
SPLIT_NAMES = {"train", "training", "val", "valid", "validation", "test", "testing"}
STRUCTURAL_NAMES = SPLIT_NAMES | {"images", "image", "imgs", "data", "dataset"}


def image_inventory(archive: zipfile.ZipFile) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Decode every supported archive image and preserve each original relative path.

    Directory labels are captured from the immediate parent folder as an observed
    candidate label. This does not certify that folders contain authoritative labels.
    """
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for member in archive.infolist():
        path = PurePosixPath(member.filename)
        if member.is_dir() or path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
            continue
        record: dict[str, Any] = {
            "relative_path": path.as_posix(),
            "file_size_bytes": member.file_size,
            "extension": path.suffix.lower(),
            "top_level_folder": next((part for part in path.parts[:-1] if part.lower() not in STRUCTURAL_NAMES), None),
            "folder_label": path.parent.name if path.parent.name else None,
            # Keep the complete observed hierarchy so same-named labels such as Healthy
            # under different crop folders remain distinct in the inventory.
            "class_path": "/".join(part for part in path.parts[:-1] if part.lower() not in STRUCTURAL_NAMES) or "[archive root]",
            "category_folder": next((part for part in path.parts[:-1] if part.lower() in {"disease", "diseases", "healthy", "insect", "insects", "insect-pests", "pest", "pests"}), None),
            "split": next((part.lower() for part in path.parts[:-1] if part.lower() in SPLIT_NAMES), None),
        }
        try:
            # Read through ZipFile so the submitted archive remains untouched.
            with archive.open(member) as source:
                with Image.open(source) as image:
                    record.update({"format": image.format, "width": image.width, "height": image.height, "mode": image.mode})
                    image.verify()
            record["status"] = "valid"
        except Exception as error:  # Keep failures visible instead of dropping their paths.
            record["status"] = "unreadable"
            record["error"] = f"{type(error).__name__}: {error}"
            errors.append({"relative_path": path.as_posix(), "error": record["error"]})
        records.append(record)
    return records, errors


def exact_duplicate_groups(archive: zipfile.ZipFile, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hash image bytes in blocks and return groups with identical SHA-256 content."""
    by_hash: dict[str, list[str]] = defaultdict(list)
    for record in records:
        if record["status"] != "valid":
            continue
        digest = hashlib.sha256()
        with archive.open(record["relative_path"]) as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        by_hash[digest.hexdigest()].append(record["relative_path"])
    return [{"sha256": digest, "files": paths} for digest, paths in sorted(by_hash.items()) if len(paths) > 1]


def color_histogram_features(archive: zipfile.ZipFile, records: list[dict[str, Any]], bins: int = 16) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Create normalized RGB histograms and a two-component PCA from valid images.

    Each image is resized in memory to 64x64 before a per-channel histogram is made.
    PCA describes these coarse color distributions only; it is not a disease classifier.
    """
    valid = [record for record in records if record["status"] == "valid"]
    if len(valid) < 2:
        return [], None
    vectors: list[np.ndarray] = []
    labels: list[str] = []
    paths: list[str] = []
    for record in valid:
        with archive.open(record["relative_path"]) as source:
            with Image.open(source) as image:
                pixels = np.asarray(image.convert("RGB").resize((64, 64)), dtype=np.uint8)
        parts = [np.histogram(pixels[:, :, channel], bins=bins, range=(0, 256), density=False)[0] for channel in range(3)]
        vector = np.concatenate(parts).astype(np.float64)
        vector /= vector.sum() or 1.0
        vectors.append(vector)
        labels.append(str(record["class_path"]))
        paths.append(record["relative_path"])

    matrix = np.vstack(vectors)
    centered = matrix - matrix.mean(axis=0, keepdims=True)
    # SVD computes principal axes without a covariance matrix over all image pairs.
    _, singular_values, right_vectors = np.linalg.svd(centered, full_matrices=False)
    components = centered @ right_vectors[:2].T
    variance = singular_values**2
    ratios = variance[:2] / variance.sum() if variance.sum() else np.zeros(2)
    projected = [
        {"relative_path": path, "class_path": label, "PC1": float(point[0]), "PC2": float(point[1])}
        for path, label, point in zip(paths, labels, components)
    ]
    pca = {
        "feature_representation": f"normalized RGB histogram ({bins} bins per channel; {3 * bins} values per image)",
        "resize_for_histogram": "64x64 pixels in memory; source images are unchanged",
        "image_count": len(valid),
        "explained_variance_ratio": [float(value) for value in ratios],
        "cumulative_explained_variance": [float(ratios[:index + 1].sum()) for index in range(len(ratios))],
        "limitation": "Color histogram PCA shows coarse color-distribution variation only; it does not establish disease separation or classification performance.",
    }
    return projected, pca


def write_csv(path: str, rows: list[dict[str, Any]], columns: list[str]) -> None:
    """Write a deterministic CSV artifact with a known header and row ordering."""
    with open(path, "w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_class_distribution_svg(path: Path, rows: list[dict[str, Any]]) -> None:
    """Render a scalable horizontal count chart from the measured class table."""
    width, left, right, row_height, top = 1280, 370, 80, 28, 56
    height = top + row_height * max(len(rows), 1) + 28
    maximum = max((int(row["image_count"]) for row in rows), default=1)
    chart_width = width - left - right
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="Class image counts">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        '<text x="24" y="32" font-family="sans-serif" font-size="18" font-weight="700" fill="#17231c">Image counts by observed class folder</text>',
    ]
    for index, row in enumerate(sorted(rows, key=lambda value: (value["top_level_folder"], value["class_path"]))):
        y = top + index * row_height
        count = int(row["image_count"])
        bar_width = chart_width * count / maximum
        label = escape(str(row["class_path"]))
        elements.extend([
            f'<text x="{left - 12}" y="{y + 16}" text-anchor="end" font-family="sans-serif" font-size="11" fill="#374151">{label}</text>',
            f'<rect x="{left}" y="{y}" width="{bar_width:.2f}" height="17" rx="4" fill="#23834f"/>',
            f'<text x="{left + bar_width + 8:.2f}" y="{y + 13}" font-family="sans-serif" font-size="11" fill="#374151">{count} · {row["percentage_of_all_images"]}%</text>',
        ])
    elements.append("</svg>")
    path.write_text("\n".join(elements), encoding="utf-8")


def write_pca_svg(path: Path, rows: list[dict[str, Any]], pca: dict[str, Any]) -> None:
    """Render a PCA scatter plot from the computed projection and variance values."""
    width, height = 1120, 680
    left, top, plot_width, plot_height = 76, 74, 790, 520
    x_values = [float(row["PC1"]) for row in rows]
    y_values = [float(row["PC2"]) for row in rows]
    x_low, x_high = min(x_values, default=-1.0), max(x_values, default=1.0)
    y_low, y_high = min(y_values, default=-1.0), max(y_values, default=1.0)
    x_span, y_span = max(x_high - x_low, 1e-9), max(y_high - y_low, 1e-9)
    classes = sorted({str(row["class_path"]) for row in rows})
    colors = {name: f"hsl({int(index * 360 / max(len(classes), 1))}, 62%, 42%)" for index, name in enumerate(classes)}
    ratios = pca["explained_variance_ratio"]
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="PCA projection of image color histograms">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        '<text x="24" y="32" font-family="sans-serif" font-size="18" font-weight="700" fill="#17231c">PCA of normalized RGB color histograms</text>',
        f'<text x="24" y="54" font-family="sans-serif" font-size="11" fill="#4b5563">PC1 {ratios[0] * 100:.2f}% · PC2 {ratios[1] * 100:.2f}% · cumulative {pca["cumulative_explained_variance"][1] * 100:.2f}%</text>',
        f'<path d="M{left} {top + plot_height}H{left + plot_width}M{left} {top}V{top + plot_height}" stroke="#9ca3af" fill="none"/>',
    ]
    for row in rows:
        x = left + (float(row["PC1"]) - x_low) / x_span * plot_width
        y = top + plot_height - (float(row["PC2"]) - y_low) / y_span * plot_height
        label = str(row["class_path"])
        elements.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3" fill="{colors[label]}" fill-opacity="0.58"><title>{escape(label)}</title></circle>')
    for index, name in enumerate(classes):
        y = top + 12 + index * 25
        elements.extend([
            f'<circle cx="{left + plot_width + 26}" cy="{y - 4}" r="4" fill="{colors[name]}"/>',
            f'<text x="{left + plot_width + 38}" y="{y}" font-family="sans-serif" font-size="10" fill="#374151">{escape(name)}</text>',
        ])
    elements.extend([
        f'<text x="{left + plot_width / 2}" y="{top + plot_height + 36}" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#374151">Principal component 1</text>',
        f'<text x="18" y="{top + plot_height / 2}" transform="rotate(-90 18 {top + plot_height / 2})" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#374151">Principal component 2</text>',
        "</svg>",
    ])
    path.write_text("\n".join(elements), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", help="Path to the original dataset ZIP archive")
    parser.add_argument("--output", default="phase1-analysis-output", help="Directory for JSON and CSV analysis artifacts")
    args = parser.parse_args()

    from pathlib import Path
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.archive) as archive:
        all_files = [entry for entry in archive.infolist() if not entry.is_dir()]
        records, errors = image_inventory(archive)
        valid = [item for item in records if item["status"] == "valid"]
        counts = Counter(str(item["class_path"]) for item in records)
        root_groups = Counter(str(item["top_level_folder"] or "[archive root]") for item in records)
        category_counts = Counter(str(item["category_folder"] or "[category not encoded]") for item in records)
        split_counts = Counter(item["split"] or "[no explicit split folder]" for item in records)
        class_by_root: dict[str, Counter[str]] = defaultdict(Counter)
        for item in records:
            root_name = str(item["top_level_folder"] or "[archive root]")
            class_by_root[root_name][str(item["class_path"])] += 1
        class_distribution = [
            {
                "class_path": class_name,
                "top_level_folder": root_name,
                "image_count": count,
                "percentage_of_all_images": round(count * 100 / len(records), 4) if records else 0.0,
                "percentage_within_top_level_folder": round(count * 100 / sum(class_by_root[root_name].values()), 4) if class_by_root[root_name] else 0.0,
            }
            for root_name, per_class in sorted(class_by_root.items())
            for class_name, count in sorted(per_class.items())
        ]
        sizes = [item["file_size_bytes"] for item in records]
        dimension_counts = Counter(f"{item['width']}x{item['height']}" for item in valid)
        formats = Counter(str(item.get("format") or "unknown") for item in valid)
        modes = Counter(str(item.get("mode") or "unknown") for item in valid)
        duplicates = exact_duplicate_groups(archive, records)
        pca_rows, pca_summary = color_histogram_features(archive, records)

    summary: dict[str, Any] = {
        "source_archive": str(Path(args.archive).name),
        "archive_file_count": len(all_files),
        "archive_uncompressed_bytes": sum(item.file_size for item in all_files),
        "supported_image_count": len(records),
        "valid_image_count": len(valid),
        "unreadable_images": errors,
        "top_level_folder_counts": dict(sorted(root_groups.items())),
        "top_level_folder_percentages": {name: round(count * 100 / len(records), 4) for name, count in sorted(root_groups.items())} if records else {},
        "observed_class_path_counts": dict(sorted(counts.items())),
        "class_distribution": class_distribution,
        "category_folder_counts": dict(sorted(category_counts.items())),
        "split_folder_counts": dict(sorted(split_counts.items())),
        "split_folder_percentages": {name: round(count * 100 / len(records), 4) for name, count in sorted(split_counts.items())} if records else {},
        "format_counts": dict(sorted(formats.items())),
        "image_mode_counts": dict(sorted(modes.items())),
        "dimension_counts": dict(sorted(dimension_counts.items())),
        "file_size_bytes": {
            "min": min(sizes) if sizes else None,
            "median": statistics.median(sizes) if sizes else None,
            "mean": statistics.mean(sizes) if sizes else None,
            "max": max(sizes) if sizes else None,
            "total": sum(sizes),
        },
        "exact_duplicate_groups": duplicates,
        "pca": pca_summary,
        "label_note": "Folder labels are reported as observed; confirm the archive's labeling convention before treating them as ground truth.",
    }
    (output / "dataset_inventory.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_csv(str(output / "image_inventory.csv"), records, ["relative_path", "top_level_folder", "category_folder", "folder_label", "class_path", "split", "status", "format", "width", "height", "mode", "file_size_bytes", "extension"])
    write_csv(str(output / "class_distribution.csv"), class_distribution, ["class_path", "top_level_folder", "image_count", "percentage_of_all_images", "percentage_within_top_level_folder"])
    write_csv(str(output / "exact_duplicates.csv"), [member | {"group_sha256": group["sha256"]} for group in duplicates for member in ({"relative_path": path} for path in group["files"])], ["group_sha256", "relative_path"])
    write_csv(str(output / "color_histogram_pca.csv"), pca_rows, ["relative_path", "class_path", "PC1", "PC2"])
    write_class_distribution_svg(output / "class_distribution.svg", class_distribution)
    if pca_rows:
        write_pca_svg(output / "color_histogram_pca.svg", pca_rows, pca_summary)
    print(json.dumps({"output_directory": str(output), "inventory_images": len(records), "valid_images": len(valid), "duplicate_groups": len(duplicates), "pca_images": len(pca_rows)}, indent=2))


if __name__ == "__main__":
    main()
