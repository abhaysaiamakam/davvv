"""Security and traceability checks for the allowlisted CodeLens source manifest."""
import json
import runpy
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = runpy.run_path(str(ROOT / "scripts/build-codelens-manifest.py"))


class CodeLensManifestTests(unittest.TestCase):
    def test_manifest_contains_only_allowlisted_service_symbols(self):
        manifest = json.loads((ROOT / "apps/web/src/lib/codelens-sources.json").read_text())
        allowed = CONFIG["ALLOWLIST"]
        frontend = CONFIG["FRONTEND_ALLOWLIST"]
        self.assertEqual(set(manifest), set(allowed) | set(frontend))
        for key, item in manifest.items():
            with self.subTest(key=key):
                permitted = allowed[key][0] if key in allowed else frontend[key][0]
                self.assertEqual(item["source_file"], permitted)
                self.assertTrue(item["source_file"].startswith(("apps/api/app/services/", "apps/web/src/components/ui/", "apps/web/src/app/explorer/")))
                self.assertNotIn("..", item["source_file"].split("/"))
                self.assertFalse(Path(item["source_file"]).is_absolute())

    def test_snippets_match_real_source_lines(self):
        manifest = json.loads((ROOT / "apps/web/src/lib/codelens-sources.json").read_text())
        allowed = CONFIG["ALLOWLIST"]
        frontend = CONFIG["FRONTEND_ALLOWLIST"]
        for key, item in manifest.items():
            with self.subTest(key=key):
                source = (ROOT / item["source_file"]).read_text().splitlines()
                exact = "\n".join(source[item["line_start"] - 1 : item["line_end"]])
                self.assertEqual(item["code_snippet"], exact)
                self.assertLessEqual(item["line_end"] - item["line_start"] + 1, 100)
                self.assertEqual(item["is_excerpt"], item["line_start"] > item["function_line_start"] or item["line_end"] < item["function_line_end"])
                if key in allowed:
                    _, class_name, method_name, *_ = allowed[key]
                    self.assertEqual(item["source_symbol"], f"{class_name}.{method_name}")
                    self.assertEqual(item["language"], "python")
                    tree = __import__("ast").parse("\n".join(source))
                    owner = next(node for node in tree.body if isinstance(node, __import__("ast").ClassDef) and node.name == class_name)
                    method = next(node for node in owner.body if isinstance(node, (__import__("ast").FunctionDef, __import__("ast").AsyncFunctionDef)) and node.name == method_name)
                    expected_start = min([method.lineno, *(decorator.lineno for decorator in method.decorator_list)])
                    self.assertEqual(item["function_line_start"], expected_start)
                    self.assertEqual(item["function_line_end"], method.end_lineno)
                else:
                    _, symbol, *_ = frontend[key]
                    self.assertEqual(item["source_symbol"], symbol)
                    self.assertEqual(item["language"], "typescript")


if __name__ == "__main__":
    unittest.main()
