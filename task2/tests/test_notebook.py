import json
import subprocess
import sys
import unittest
from pathlib import Path


class NotebookGenerationTests(unittest.TestCase):
    def test_generated_notebook_embeds_svg_outputs(self):
        root = Path(__file__).resolve().parents[2]
        script = root / "task2" / "scripts" / "build_task2_notebook.py"
        notebook = root / "task2" / "notebooks" / "jinan_guoji_indicators.ipynb"

        subprocess.run([sys.executable, str(script)], cwd=root, check=True)
        data = json.loads(notebook.read_text(encoding="utf-8"))
        svg_outputs = []
        for cell in data["cells"]:
            for output in cell.get("outputs", []):
                if "image/svg+xml" in output.get("data", {}):
                    svg_outputs.append(output["data"]["image/svg+xml"])

        self.assertGreaterEqual(len(svg_outputs), 5)
        self.assertTrue(all("<svg" in output and "</svg>" in output for output in svg_outputs))


if __name__ == "__main__":
    unittest.main()
