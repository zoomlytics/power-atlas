import unittest
from pathlib import Path

try:
    from pypdf import PdfReader
except ModuleNotFoundError:  # pypdf is an optional test dependency
    PdfReader = None


class SyntheticExamplePdfTests(unittest.TestCase):
    def test_synthetic_pdfs_exist_and_share_entities(self):
        if PdfReader is None:
            self.skipTest("pypdf is not installed; skipping PDF content checks")
        data_dir = Path(__file__).resolve().parents[1] / "examples" / "data"
        factsheet = data_dir / "power_atlas_factsheet.pdf"
        analyst_note = data_dir / "power_atlas_analyst_note.pdf"

        self.assertTrue(factsheet.exists())
        self.assertTrue(analyst_note.exists())

        factsheet_text = "\n".join((page.extract_text() or "") for page in PdfReader(str(factsheet)).pages)
        analyst_note_text = "\n".join((page.extract_text() or "") for page in PdfReader(str(analyst_note)).pages)

        for token in [
            "Lina Park",
            "Omar Haddad",
            "Priya Sen",
            "Mateo Rossi",
            "Northbridge Energy Cooperative",
            "Meridian Port Authority",
            "Helios Logistics Ltd",
            "Harbor Grid Upgrade Hearing",
            "CHILD_OF",
            "MARRIED_TO",
            "WORKED_AT",
            "MEMBER_OF",
            "TOOK_PLACE_IN",
            "INVOLVED_IN",
        ]:
            self.assertIn(token, factsheet_text)
            self.assertIn(token, analyst_note_text)


if __name__ == "__main__":
    unittest.main()
