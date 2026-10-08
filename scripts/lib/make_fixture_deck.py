#!/usr/bin/env python3
"""make_fixture_deck.py — deterministic .pptx fixtures for tests.

  golden   <out.pptx>   3-slide fully-editable deck (native text boxes only;
                        measured editable_ratio == 1.0). Committed as a stable
                        fixture so structural-validation/editability behavior is
                        pinned against a known PPTX, not only generated decks.
  degraded <out.pptx>   3-slide deck whose slides are dominated by pictures
                        (1 text box + 4 pictures each => measured ratio 0.2).
                        Used to prove the hard editability gate is computed from
                        the reopened deck, not from a render-log claim.

No timestamps / randomness => byte-stable output for the same python-pptx version.
"""
import base64
import sys
from io import BytesIO

from pptx import Presentation
from pptx.util import Inches, Pt

# 1x1 transparent PNG (non-editable "significant" object for the degraded deck).
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def golden(path):
    prs = Presentation()
    blank = prs.slide_layouts[6]
    for i, role in enumerate(["Cover", "Content", "Summary"], 1):
        s = prs.slides.add_slide(blank)
        tb = s.shapes.add_textbox(Inches(0.6), Inches(0.4), Inches(9.0), Inches(1.2))
        tb.text_frame.text = f"{role} slide {i}"
        tb.text_frame.paragraphs[0].runs[0].font.size = Pt(32)
        bb = s.shapes.add_textbox(Inches(0.6), Inches(1.8), Inches(9.0), Inches(4.0))
        bb.text_frame.text = f"Editable body for {role.lower()} slide {i}."
        bb.text_frame.paragraphs[0].runs[0].font.size = Pt(18)
    prs.save(path)


def degraded(path):
    prs = Presentation()
    blank = prs.slide_layouts[6]
    for i in range(1, 4):
        s = prs.slides.add_slide(blank)
        tb = s.shapes.add_textbox(Inches(0.6), Inches(0.3), Inches(9.0), Inches(1.0))
        tb.text_frame.text = f"Title {i}"
        for j in range(4):  # 4 pictures => 1 editable / 5 significant => ratio 0.2
            s.shapes.add_picture(BytesIO(_PNG), Inches(0.6 + 2 * j), Inches(2.0), Inches(1.5), Inches(1.5))
    prs.save(path)


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("golden", "degraded"):
        print("usage: make_fixture_deck.py {golden|degraded} <out.pptx>", file=sys.stderr)
        sys.exit(1)
    {"golden": golden, "degraded": degraded}[sys.argv[1]](sys.argv[2])
