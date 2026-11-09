import importlib.util
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree

from PIL import Image

SCRIPT = Path(__file__).resolve().parents[1] / "apps" / "web" / "public" / "phase1-image-analysis.py"
SPEC = importlib.util.spec_from_file_location("phase1_image_analysis", SCRIPT)
assert SPEC and SPEC.loader
analysis = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analysis)


def png_bytes(color: tuple[int, int, int]) -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 12), color).save(output, format="PNG")
    return output.getvalue()


def class_distribution_fixture(records: list[dict[str, object]]) -> list[dict[str, str]]:
    """Make tiny measured chart rows from inventory paths for the SVG writer test."""
    pairs = sorted({(str(record["class_path"]), str(record["top_level_folder"])) for record in records})
    return [{"class_path": label, "top_level_folder": root} for label, root in pairs]


class Phase1ImageAnalysisTests(unittest.TestCase):
    def test_inventory_duplicate_groups_and_pca_use_observed_hierarchy(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive_path = Path(temporary) / "dataset.zip"
            duplicate = png_bytes((180, 30, 20))
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("Rice/Healthy/one.png", duplicate)
                archive.writestr("Rice/Healthy/two.png", duplicate)
                archive.writestr("Maize/Healthy/three.png", png_bytes((20, 80, 180)))
                archive.writestr("notes.txt", "not an image")

            with zipfile.ZipFile(archive_path) as archive:
                records, errors = analysis.image_inventory(archive)
                duplicate_groups = analysis.exact_duplicate_groups(archive, records)
                pca_rows, pca = analysis.color_histogram_features(archive, records)

            self.assertEqual(len(records), 3)
            self.assertEqual(errors, [])
            self.assertEqual({row["class_path"] for row in records}, {"Rice/Healthy", "Maize/Healthy"})
            self.assertEqual(len(duplicate_groups), 1)
            self.assertEqual(len(duplicate_groups[0]["files"]), 2)
            self.assertEqual(len(pca_rows), 3)
            self.assertEqual(pca["image_count"], 3)
            self.assertEqual(len(pca["explained_variance_ratio"]), 2)
            self.assertEqual(pca_rows[0]["class_path"], "Rice/Healthy")
            class_chart = Path(temporary) / "classes.svg"
            pca_chart = Path(temporary) / "pca.svg"
            analysis.write_class_distribution_svg(class_chart, [
                {"class_path": row["class_path"], "top_level_folder": row["top_level_folder"], "image_count": 1, "percentage_of_all_images": 33.3333}
                for row in class_distribution_fixture(records)
            ])
            analysis.write_pca_svg(pca_chart, pca_rows, pca)
            self.assertEqual(ElementTree.parse(class_chart).getroot().tag, "{http://www.w3.org/2000/svg}svg")
            self.assertEqual(ElementTree.parse(pca_chart).getroot().tag, "{http://www.w3.org/2000/svg}svg")

    def test_raw_and_commented_python_variants_are_valid(self):
        source = SCRIPT.read_text(encoding="utf-8")
        raw = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
        compile(source, str(SCRIPT), "exec")
        compile(raw, str(SCRIPT), "exec")

    def test_unreadable_supported_image_remains_in_inventory_as_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive_path = Path(temporary) / "dataset.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("Maize/Disease/Broken/broken.jpg", b"not an image")
            with zipfile.ZipFile(archive_path) as archive:
                records, errors = analysis.image_inventory(archive)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["status"], "unreadable")
            self.assertEqual(errors[0]["relative_path"], "Maize/Disease/Broken/broken.jpg")


if __name__ == "__main__":
    unittest.main()
