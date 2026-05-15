import os
from reportlab.pdfgen import canvas

def create_pdf(filename, text_lines):
    c = canvas.Canvas(filename)
    y = 800
    for line in text_lines:
        c.drawString(100, y, line)
        y -= 20
    c.save()

# All tokens must be in BOTH files for the current test assertion to pass
all_tokens = [
    "Lina Park", "Omar Haddad", "Priya Sen", "Mateo Rossi",
    "Northbridge Energy Cooperative", "Meridian Port Authority",
    "Helios Logistics Ltd", "Harbor Grid Upgrade Hearing",
    "CHILD_OF", "MARRIED_TO", "WORKED_AT", "MEMBER_OF", "TOOK_PLACE_IN", "INVOLVED_IN"
]

factsheet_text = ["Factsheet Content:"] + all_tokens
analyst_note_text = ["Analyst Note Content:"] + all_tokens

if __name__ == "__main__":
    create_pdf("examples/data/power_atlas_factsheet.pdf", factsheet_text)
    create_pdf("examples/data/power_atlas_analyst_note.pdf", analyst_note_text)
