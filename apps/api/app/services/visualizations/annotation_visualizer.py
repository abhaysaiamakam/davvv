"""
Annotation Dataset Visualizer for CropLens.

Inspects datasets for bounding-box and object-detection annotation files
(COCO JSON, YOLO TXT) and generates object count distributions and class annotation statistics.
Does NOT fabricate annotation visualizations if none exist.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any, Dict, List

from app.schemas.visualization import (
    AxisScale,
    AxisSpec,
    ChartType,
    SeriesSpec,
    VisualizationCategory,
    VisualizationSpecification,
)
from app.services.visualizations.base import BaseVisualizer


class AnnotationVisualizer(BaseVisualizer):
    """Generates visualizations for annotated object-detection datasets."""

    @property
    def name(self) -> str:
        return "annotation_visualizer"

    def can_handle(self, dataset_id: str, version_id: str, context: Dict[str, Any]) -> bool:
        """Applicable only if valid annotation files exist."""
        dataset_dir = context.get("dataset_dir")
        if not dataset_dir or not Path(dataset_dir).exists():
            return False
        return self._detect_annotations(Path(dataset_dir))

    def _detect_annotations(self, dataset_dir: Path) -> bool:
        """Check for presence of COCO JSON or YOLO label TXT files."""
        # 1. Look for COCO JSON
        for json_file in dataset_dir.rglob("*.json"):
            if json_file.is_file() and json_file.stat().st_size < 50 * 1024 * 1024:
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, dict) and "annotations" in data and "categories" in data:
                            return True
                except Exception:
                    pass

        # 2. Look for YOLO txt annotations in labels/ folder or beside images
        txt_files = list(dataset_dir.rglob("*.txt"))[:50]
        yolo_match = 0
        for txt in txt_files:
            if txt.name.lower() in ("readme.txt", "license.txt", "classes.txt"):
                continue
            try:
                lines = txt.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
                if lines and all(len(l.split()) >= 5 for l in lines[:5]):
                    yolo_match += 1
            except Exception:
                pass
        return yolo_match >= 2

    def generate(
        self, dataset_id: str, version_id: str, context: Dict[str, Any]
    ) -> List[VisualizationSpecification]:
        specs: List[VisualizationSpecification] = []
        dataset_dir = context.get("dataset_dir")
        if not dataset_dir:
            return specs

        p_dir = Path(dataset_dir)
        # Parse COCO JSON if available
        for json_file in p_dir.rglob("*.json"):
            if json_file.is_file():
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict) and "annotations" in data and "categories" in data:
                        return self._generate_coco_specs(dataset_id, version_id, data, json_file.name)
                except Exception:
                    pass

        # Parse YOLO TXT if available
        yolo_specs = self._generate_yolo_specs(dataset_id, version_id, p_dir)
        if yolo_specs:
            return yolo_specs

        return specs

    def _generate_coco_specs(
        self, dataset_id: str, version_id: str, coco_data: Dict[str, Any], filename: str
    ) -> List[VisualizationSpecification]:
        specs = []
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        categories = {c["id"]: c["name"] for c in coco_data.get("categories", []) if "id" in c and "name" in c}
        annotations = coco_data.get("annotations", [])

        # Count per category
        cat_counts: Dict[str, int] = {}
        img_bbox_counts: Dict[Any, int] = {}

        for ann in annotations:
            cat_id = ann.get("category_id")
            cat_name = categories.get(cat_id, f"Category {cat_id}")
            cat_counts[cat_name] = cat_counts.get(cat_name, 0) + 1

            img_id = ann.get("image_id")
            if img_id is not None:
                img_bbox_counts[img_id] = img_bbox_counts.get(img_id, 0) + 1

        if cat_counts:
            chart_data = [{"class_name": k, "bounding_boxes": v} for k, v in cat_counts.items()]
            specs.append(
                VisualizationSpecification(
                    visualization_id=f"vis-{dataset_id}-{version_id}-ann-class-distribution",
                    dataset_id=dataset_id,
                    dataset_version=version_id,
                    title="Annotation Class Frequency",
                    description=f"Total annotated bounding boxes per object class in '{filename}'.",
                    chart_type=ChartType.BAR,
                    category=VisualizationCategory.ANNOTATIONS,
                    x_axis=AxisSpec(
                        name="class_name",
                        label="Object Class",
                        scale=AxisScale.CATEGORY,
                    ),
                    y_axis=AxisSpec(
                        name="bounding_boxes",
                        label="Bounding Box Count",
                        scale=AxisScale.LINEAR,
                        unit="boxes",
                        min_val=0.0,
                    ),
                    series=[
                        SeriesSpec(
                            name="Bounding Boxes",
                            data_key="bounding_boxes",
                            color="#8B5CF6",
                            unit="boxes",
                        ),
                    ],
                    chart_data=chart_data,
                    metadata={"total_annotations": len(annotations), "total_categories": len(categories)},
                    generated_at=now,
                    source_artifacts={"source_file": filename},
                )
            )

        return specs

    def _generate_yolo_specs(
        self, dataset_id: str, version_id: str, dataset_dir: Path
    ) -> List[VisualizationSpecification]:
        specs = []
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        txt_files = list(dataset_dir.rglob("*.txt"))
        class_counts: Dict[str, int] = {}
        total_boxes = 0

        for txt in txt_files:
            if txt.name.lower() in ("readme.txt", "license.txt", "classes.txt"):
                continue
            try:
                lines = txt.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
                for line in lines:
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        cls_idx = parts[0]
                        class_counts[cls_idx] = class_counts.get(cls_idx, 0) + 1
                        total_boxes += 1
            except Exception:
                pass

        if total_boxes > 0:
            chart_data = [{"class_name": f"Class {k}", "bounding_boxes": v} for k, v in sorted(class_counts.items())]
            specs.append(
                VisualizationSpecification(
                    visualization_id=f"vis-{dataset_id}-{version_id}-ann-yolo-classes",
                    dataset_id=dataset_id,
                    dataset_version=version_id,
                    title="YOLO Annotation Class Distribution",
                    description="Bounding box frequency across indexed object classes from YOLO annotations.",
                    chart_type=ChartType.BAR,
                    category=VisualizationCategory.ANNOTATIONS,
                    x_axis=AxisSpec(
                        name="class_name",
                        label="YOLO Class Index",
                        scale=AxisScale.CATEGORY,
                    ),
                    y_axis=AxisSpec(
                        name="bounding_boxes",
                        label="Bounding Box Count",
                        scale=AxisScale.LINEAR,
                        unit="boxes",
                        min_val=0.0,
                    ),
                    series=[
                        SeriesSpec(
                            name="Bounding Boxes",
                            data_key="bounding_boxes",
                            color="#EC4899",
                            unit="boxes",
                        ),
                    ],
                    chart_data=chart_data,
                    metadata={"total_bounding_boxes": total_boxes},
                    generated_at=now,
                )
            )
        return specs

