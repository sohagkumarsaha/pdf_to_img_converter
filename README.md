# PDF Image Converter

Local web tool: upload PDFs, pick SVG, PNG or JPEG, download the result.


Go to cmd terminal and paste the following code: 

git clone https://github.com/sohagkumarsaha/pdf_to_img_converter.git
cd pdf_to_img_converter
python -m pip install -r requirements.txt
python app.py


pip install -r requirements.txt
python app.py        # open http://127.0.0.1:5000


- **Size**: SVG keeps the PDF page size exactly (vector, no quality loss). PNG/JPEG at 72 DPI are 1 px per PDF point; higher DPI adds detail and stores the DPI so the physical size stays the same.
- **Quality**: PNG is lossless; JPEG uses quality 100 with no chroma subsampling.
- Multiple PDFs / pages are returned as a ZIP; a page range (e.g. `1,3,5-7`) is optional.
