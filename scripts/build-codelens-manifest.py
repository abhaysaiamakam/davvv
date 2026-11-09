"""Build a source manifest from a fixed, reviewed allowlist of backend symbols."""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = {
    "eda.class_distribution": ("apps/api/app/services/eda_service.py", "EdaService", "_compute_class_distribution"),
    "eda.dimensions": ("apps/api/app/services/eda_service.py", "EdaService", "_compute_dimension_analysis"),
    "eda.color": ("apps/api/app/services/eda_service.py", "EdaService", "_compute_color_analysis"),
    "eda.tabular.histogram": ("apps/api/app/services/visualizations/tabular_visualizer.py", "TabularVisualizer", "generate", "bin_count = min(10"),
    "quality.assessment": ("apps/api/app/services/data_quality_service.py", "DataQualityService", "assess_dataset"),
    "quality.integrity": ("apps/api/app/services/data_quality_service.py", "DataQualityService", "_evaluate_integrity"),
    "quality.imbalance": ("apps/api/app/services/data_quality_service.py", "DataQualityService", "_evaluate_imbalance"),
    "quality.consistency": ("apps/api/app/services/data_quality_service.py", "DataQualityService", "_evaluate_consistency"),
    "quality.duplicates": ("apps/api/app/services/data_quality_service.py", "DataQualityService", "_evaluate_duplicates"),
    "quality.score": ("apps/api/app/services/data_quality_service.py", "DataQualityService", "_calculate_quality_score", "overall_score = round("),
    "preprocess.imputation": ("apps/api/app/services/preprocessing/tabular_preprocessing.py", "MissingValueImputationOperation", "preview"),
    "preprocess.drop_missing": ("apps/api/app/services/preprocessing/tabular_preprocessing.py", "DropMissingRowsOperation", "preview"),
    "preprocess.duplicates": ("apps/api/app/services/preprocessing/tabular_preprocessing.py", "RemoveDuplicatesOperation", "preview"),
    "preprocess.outliers": ("apps/api/app/services/preprocessing/tabular_preprocessing.py", "OutlierHandlingOperation", "preview"),
    "preprocess.scaling": ("apps/api/app/services/preprocessing/tabular_preprocessing.py", "NumericScalingOperation", "preview"),
    "feature.variance": ("apps/api/app/services/feature_engineering/tabular_feature_operations.py", "VarianceThresholdSelectionOperation", "preview"),
    "feature.transform": ("apps/api/app/services/feature_engineering/tabular_feature_operations.py", "MathematicalTransformOperation", "preview"),
    "feature.correlation": ("apps/api/app/services/feature_engineering/tabular_feature_operations.py", "CorrelationRedundancyOperation", "preview"),
    "feature.pca": ("apps/api/app/services/feature_engineering/tabular_feature_operations.py", "PrincipalComponentAnalysisOperation", "preview"),
    "readiness.assessment": ("apps/api/app/services/readiness_service.py", "ReadinessService", "assess_readiness", "overall_score = int(sum(d.score"),
}
FRONTEND_ALLOWLIST = {
    "renderer.visualization": (
        "apps/web/src/components/ui/visualization-chart.tsx",
        "VisualizationChart",
        "export function VisualizationChart(",
        "\nfunction Fallback(",
    ),
}


def symbol_node(tree: ast.Module, class_name: str, method_name: str) -> ast.AST:
    owners = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name]
    if not owners:
        raise ValueError(f"Allowlisted class not found: {class_name}")
    methods = [node for node in owners[0].body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == method_name]
    if not methods:
        raise ValueError(f"Allowlisted method not found: {class_name}.{method_name}")
    return methods[0]


def build() -> None:
    output: dict[str, dict[str, object]] = {}
    for key, config in ALLOWLIST.items():
        relative_path, class_name, method_name, *anchors = config
        path = ROOT / relative_path
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        node = symbol_node(tree, class_name, method_name)
        function_start = min([node.lineno, *(d.lineno for d in getattr(node, "decorator_list", []))])
        function_end = node.end_lineno or node.lineno
        lines = source.splitlines()
        start = function_start
        if anchors:
            anchor_line = next((i + 1 for i, line in enumerate(lines[function_start - 1 : function_end]) if anchors[0] in line), None)
            if anchor_line is None:
                raise ValueError(f"Allowlisted source anchor not found: {key}")
            start = max(function_start, anchor_line - 14)
        end = min(function_end, start + 99)
        output[key] = {
            "source_file": relative_path,
            "source_symbol": f"{class_name}.{method_name}",
            "line_start": start,
            "line_end": end,
            "function_line_start": function_start,
            "function_line_end": function_end,
            "is_excerpt": start > function_start or end < function_end,
            "code_snippet": "\n".join(lines[start - 1 : end]),
            "language": "python",
        }
    for key, (relative_path, symbol, start_marker, end_marker) in FRONTEND_ALLOWLIST.items():
        path = ROOT / relative_path
        source = path.read_text(encoding="utf-8")
        start_offset = source.find(start_marker)
        end_offset = source.find(end_marker, start_offset + len(start_marker))
        if start_offset < 0 or end_offset < 0:
            raise ValueError(f"Allowlisted frontend symbol not found: {symbol}")
        start = source.count("\n", 0, start_offset) + 1
        end = source.count("\n", 0, end_offset) + 1
        lines = source.splitlines()
        function_start = start
        function_end = end
        output[key] = {
            "source_file": relative_path,
            "source_symbol": symbol,
            "line_start": start,
            "line_end": end,
            "function_line_start": function_start,
            "function_line_end": function_end,
            "is_excerpt": False,
            "code_snippet": "\n".join(lines[start - 1 : end]),
            "language": "typescript",
        }
    target = ROOT / "apps/web/src/lib/codelens-sources.json"
    target.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build()
