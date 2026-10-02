"""PDF -> SVG / PNG / JPEG converter (local web tool).

Run:  pip install -r requirements.txt && python app.py
Open: http://127.0.0.1:5000
"""
import io
import os
import re
import zipfile

import pymupdf
from flask import Flask, abort, render_template_string, request, send_file
from PIL import Image

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB

MIME = {"svg": "image/svg+xml", "png": "image/png", "jpeg": "image/jpeg"}
EXT = {"svg": "svg", "png": "png", "jpeg": "jpg"}


def parse_pages(spec, count):
    """'1,3,5-7' -> [0, 2, 4, 5, 6] (0-based). Empty -> all pages."""
    if not spec.strip():
        return list(range(count))
    pages = []
    for part in spec.split(","):
        m = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+))?\s*", part)
        if not m:
            raise ValueError(f"Bad page range: '{part.strip()}'")
        a = int(m.group(1))
        b = int(m.group(2) or a)
        if not (1 <= a <= b <= count):
            raise ValueError(f"Page range '{part.strip()}' is outside 1-{count}")
        pages.extend(range(a - 1, b))
    return pages


def render_page(page, fmt, dpi, svg_text_as_path, png_transparent):
    """Return bytes of one page in the requested format."""
    if fmt == "svg":
        # SVG is vector: width/height are in PDF points, i.e. identical page size.
        svg = page.get_svg_image(text_as_path=svg_text_as_path)
        return svg.encode("utf-8")

    pix = page.get_pixmap(
        matrix=pymupdf.Matrix(dpi / 72, dpi / 72),
        alpha=(fmt == "png" and png_transparent),
        annots=True,
    )
    img = Image.frombytes("RGBA" if pix.alpha else "RGB", (pix.width, pix.height), pix.samples)
    buf = io.BytesIO()
    if fmt == "png":
        # DPI metadata keeps the physical size identical to the PDF page.
        img.save(buf, "PNG", dpi=(dpi, dpi), compress_level=6)  # lossless
    else:
        img.save(buf, "JPEG", quality=100, subsampling=0, dpi=(dpi, dpi))
    return buf.getvalue()


@app.get("/")
def index():
    return render_template_string(PAGE)


@app.post("/convert")
def convert():
    files = [f for f in request.files.getlist("pdfs") if f.filename]
    fmt = request.form.get("format", "png")
    if not files or fmt not in MIME:
        abort(400, "Upload at least one PDF and choose SVG, PNG or JPEG.")
    try:
        dpi = max(36, min(1200, int(request.form.get("dpi", 300))))
    except ValueError:
        abort(400, "DPI must be a number.")
    text_as_path = request.form.get("text_as_path") == "on"
    transparent = request.form.get("transparent") == "on"
    page_spec = request.form.get("pages", "")

    outputs = []  # (filename, bytes)
    for f in files:
        stem = os.path.splitext(os.path.basename(f.filename))[0] or "document"
        try:
            doc = pymupdf.open(stream=f.read(), filetype="pdf")
            pages = parse_pages(page_spec, doc.page_count)
        except ValueError as e:
            abort(400, f"{f.filename}: {e}")
        except Exception:
            abort(400, f"{f.filename}: not a readable PDF.")
        if doc.needs_pass:
            abort(400, f"{f.filename}: PDF is password protected.")
        for p in pages:
            data = render_page(doc[p], fmt, dpi, text_as_path, transparent)
            outputs.append((f"{stem}_page{p + 1:03d}.{EXT[fmt]}", data))
        doc.close()

    if len(outputs) == 1:
        name, data = outputs[0]
        return send_file(io.BytesIO(data), mimetype=MIME[fmt], as_attachment=True, download_name=name)

    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_STORED) as z:
        for name, data in outputs:
            z.writestr(name, data)
    zbuf.seek(0)
    return send_file(zbuf, mimetype="application/zip", as_attachment=True,
                     download_name=f"converted_{EXT[fmt]}.zip")


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PDF Image Converter</title>
<style>
 body{font-family:system-ui,sans-serif;background:#f4f6f8;margin:0;color:#1d2733}
 main{max-width:640px;margin:40px auto;background:#fff;padding:28px;border-radius:12px;box-shadow:0 2px 12px #0001}
 h1{margin-top:0;font-size:1.5rem}
 #drop{border:2px dashed #8aa;border-radius:10px;padding:32px;text-align:center;cursor:pointer;color:#456}
 #drop.over{background:#e8f3ff;border-color:#2a7ae2}
 label{display:block;margin:16px 0 4px;font-weight:600}
 select,input[type=number],input[type=text]{width:100%;padding:8px;border:1px solid #bbc;border-radius:6px;box-sizing:border-box}
 .opt{font-weight:400;display:flex;gap:8px;align-items:center;margin:8px 0}
 .opt input{width:auto}
 button{margin-top:22px;width:100%;padding:12px;font-size:1rem;background:#2a7ae2;color:#fff;border:0;border-radius:8px;cursor:pointer}
 button:disabled{opacity:.6}
 #files{margin:10px 0 0;padding-left:18px;font-size:.9rem}
 #msg{margin-top:14px;font-size:.95rem}
 .err{color:#c0392b}.hint{font-size:.82rem;color:#667;margin-top:4px}
</style></head><body><main>
<h1>PDF &rarr; SVG / PNG / JPEG</h1>
<form id="f">
 <div id="drop">Drop PDF files here or click to choose<input id="pdfs" name="pdfs" type="file" accept="application/pdf,.pdf" multiple hidden></div>
 <ul id="files"></ul>

 <label for="format">Convert to</label>
 <select id="format" name="format">
  <option value="png">PNG (lossless)</option>
  <option value="jpeg">JPEG (max quality, no chroma subsampling)</option>
  <option value="svg">SVG (vector, infinitely scalable)</option>
 </select>

 <div id="rast">
  <label for="dpi">Resolution (DPI)</label>
  <input id="dpi" name="dpi" type="number" min="36" max="1200" value="300" list="dpis">
  <datalist id="dpis"><option value="72"><option value="150"><option value="300"><option value="600"></datalist>
  <div class="hint">72 DPI = 1 pixel per PDF point (the PDF's nominal size). Higher DPI keeps the same physical page size
  (stored in the image metadata) with more detail.</div>
  <label class="opt" id="trow"><input type="checkbox" name="transparent"> Transparent background (PNG only)</label>
 </div>
 <label class="opt" id="srow" hidden><input type="checkbox" name="text_as_path" checked> Convert text to outlines (exact look, fonts not needed)</label>

 <label for="pages">Pages (optional)</label>
 <input id="pages" name="pages" type="text" placeholder="all pages, or e.g. 1,3,5-7">
 <button id="go" type="submit">Convert &amp; download</button>
 <div id="msg"></div>
</form></main>
<script>
const $=id=>document.getElementById(id), drop=$('drop'), inp=$('pdfs');
function list(){$('files').innerHTML=[...inp.files].map(f=>'<li>'+f.name.replace(/</g,'&lt;')+'</li>').join('')}
drop.onclick=()=>inp.click(); inp.onchange=list;
drop.ondragover=e=>{e.preventDefault();drop.classList.add('over')};
drop.ondragleave=()=>drop.classList.remove('over');
drop.ondrop=e=>{e.preventDefault();drop.classList.remove('over');inp.files=e.dataTransfer.files;list()};
function sync(){const v=$('format').value;$('rast').hidden=v==='svg';$('srow').hidden=v!=='svg';$('trow').hidden=v!=='png'}
$('format').onchange=sync; sync();
$('f').onsubmit=async e=>{
 e.preventDefault(); const msg=$('msg'); msg.className='';
 if(!inp.files.length){msg.className='err';msg.textContent='Please choose a PDF first.';return}
 $('go').disabled=true; msg.textContent='Converting…';
 try{
  const r=await fetch('/convert',{method:'POST',body:new FormData($('f'))});
  if(!r.ok){throw new Error((await r.text()).replace(/<[^>]*>/g,' ').trim().slice(0,200))}
  const cd=r.headers.get('Content-Disposition')||'', m=/filename\\*?=(?:UTF-8'')?"?([^";]+)/.exec(cd);
  const a=document.createElement('a'); a.href=URL.createObjectURL(await r.blob());
  a.download=m?decodeURIComponent(m[1]):'converted'; a.click(); msg.textContent='Done ✔ download started.';
 }catch(err){msg.className='err';msg.textContent=err.message}
 $('go').disabled=false;
};
</script></body></html>"""

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
