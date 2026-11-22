"""Join the page images of a report folder (pages.json order) into one PDF: python scripts/images_to_pdf.py <folder> <output.pdf>"""
import json
import sys
from pathlib import Path

import fitz  # PyMuPDF

folder, target = Path(sys.argv[1]), Path(sys.argv[2])
pages = json.loads((folder / 'pages.json').read_text(encoding='utf-8'))
doc = fitz.open()
for page in pages:
    image = fitz.open(str(folder / page['file']))
    rect = image[0].rect
    pdf_page = doc.new_page(width=rect.width, height=rect.height)
    pdf_page.insert_image(rect, filename=str(folder / page['file']))
    scale = rect.width / fitz.Pixmap(str(folder / page['file'])).width      # the image is 1920 px wide, the page is in points
    for link in page.get('links', []):
        pdf_page.insert_link({'kind': fitz.LINK_URI, 'from': fitz.Rect(*[v * scale for v in link['rect']]), 'uri': link['url']})
doc.set_metadata({'title': 'Match analysis report', 'author': 'Football Coach'})
doc.save(str(target), deflate=True)
print('wrote', target, len(pages), 'pages')
