"""review.html: one card per photo, editable fields, status, Adjust crop (picker.page_parts)
and a "Download review.csv" button. Edits are kept in the browser until downloaded; the reader then
runs `cards sheet-import <batch> <file>`. Image links are relative to the batch folder, so the page
works when the card folder moves.
"""
from __future__ import annotations

import html
import json
import os
import time
from pathlib import Path
from urllib.parse import quote

from . import picker, schema

STAMP_FILE = "batch.json"
STATUS_CHOICES = (schema.PENDING, schema.APPROVED, schema.REJECTED)

SHEET_SCRIPT = """
const COLS=__COLS__, FIELDS=__FIELDS__, ROWS=__ROWS__, KEY=__KEY__;
// Saved edits carry the values the page showed when they were made (base). A field the reader
// changed keeps their value; every other field takes the page's, so a later cards command shows.
let saved={}; try{saved=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){}
const edits=saved.rows||{}, base=saved.base||{};
const csv=v=>/[",\\n]/.test(v)?'"'+v.replace(/"/g,'""')+'"':v;
function collect(){return ROWS.map((r,i)=>{const o={...r};
 document.querySelectorAll('[data-i="'+i+'"][data-f]').forEach(el=>o[el.dataset.f]=el.value);return o})}
function store(){const o={},b={};collect().forEach((r,i)=>{o[r.photo]=r;b[r.photo]=ROWS[i]});
 try{localStorage.setItem(KEY,JSON.stringify({rows:o,base:b}))}catch(e){}}
document.querySelectorAll('[data-i][data-f]').forEach(el=>{
 const p=ROWS[el.dataset.i].photo, f=el.dataset.f, s=edits[p], b=base[p];
 if(s&&s[f]!==undefined&&!el.readOnly&&(!b||s[f]!==b[f])) el.value=s[f];
 el.addEventListener('input',()=>{store();tone(el.dataset.i)})});
function tone(i){const c=document.getElementById('c'+i), st=document.querySelector('[data-i="'+i+'"][data-f="status"]').value;
 c.className='c '+st}
ROWS.forEach((_,i)=>tone(i));
document.getElementById('dl').onclick=()=>{
 const rows=collect(), text=[COLS.join(',')].concat(rows.map(r=>COLS.map(c=>csv(r[c]||'')).join(','))).join('\\n')+'\\n';
 const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type:'text/csv'}));
 a.download='review.csv';a.click()};
"""

STYLE = (
    "body{font:14px sans-serif;margin:16px}.g{display:grid;gap:12px;"
    "grid-template-columns:repeat(auto-fill,minmax(300px,1fr))}"
    ".c{border:3px solid #c93;padding:8px}.c.approved{border-color:#4a4}"
    ".c.rejected{border-color:#c33;opacity:.6}.c.recorded{border-color:#68a}"
    "img{width:100%}label{display:flex;justify-content:space-between;gap:8px;margin-top:3px;font-size:12px}"
    "input,select{width:62%;font:inherit}input[readonly]{background:#eee}"
    "#bar{position:sticky;top:0;background:#fff;padding:6px 0;margin-bottom:8px}"
)


def stamp(batch: Path) -> str:
    """The batch's creation time, kept in batch.json. A batch made again under the same name gets
    a new one, so the browser does not show the old batch's unsaved edits."""
    path = batch / STAMP_FILE
    try:
        return str(json.loads(path.read_text(encoding="utf-8"))["created"])
    except (OSError, ValueError, KeyError):
        pass
    created = str(time.time_ns())
    batch.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"created": created}) + "\n", encoding="utf-8")
    return created


def image_src(batch: Path, stored: str) -> str:
    """The picture's link, relative to the batch folder."""
    if not stored:
        return ""
    target = Path(stored) if Path(stored).is_absolute() else batch.parent.parent / stored
    return quote(Path(os.path.relpath(target, batch)).as_posix())


def pickable(batch: Path) -> set[str]:
    try:
        return set(json.loads((batch / "picker.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return set()


def write_page(batch: Path, rows: list[dict]) -> Path:
    """Write batch/review.html for rows and return its path."""
    batch = Path(batch)
    path = batch / "review.html"
    picker_css, picker_html, picker_script = picker.page_parts(batch)
    pick = pickable(batch)
    cells = []
    for i, r in enumerate(rows):
        recorded = r["status"] == schema.RECORDED
        flags = r["flags"].replace(";", " · ") or "ok"
        src = image_src(batch, r["image"])
        img = f'<img class=orig src="{html.escape(src)}">' if src else ""
        crop = (f'<input type=hidden data-i="{i}" data-f="crop" value="{html.escape(r.get("crop", ""))}">'
                f'<span class=crop-set></span>')
        if r["photo"] in pick and not recorded:
            crop += f'<br><button class=adj data-i="{i}">Adjust crop</button>'
        ro = " readonly" if recorded else ""
        inputs = "".join(
            f'<label>{key.replace("_", " ")}<input data-i="{i}" data-f="{key}" '
            f'value="{html.escape(r[key])}"{ro}></label>'
            for key in schema.EDIT_FIELDS)
        if recorded:
            status = (f'<label>status<input data-i="{i}" data-f="status" value="recorded" readonly></label>')
        else:
            opts = "".join(f'<option{" selected" if r["status"] == v else ""}>{v}</option>'
                           for v in STATUS_CHOICES)
            status = f'<label>status<select data-i="{i}" data-f="status">{opts}</select></label>'
        cells.append(
            f'<div id="c{i}" class="c {html.escape(r["status"])}">{img}'
            f'<b>{html.escape(r["photo"])}</b> ({html.escape(r["kind"])}) &rarr; '
            f'{html.escape(r["roster_id"] or "?")} blur {html.escape(r["blur"])}'
            f'<br><i>{html.escape(flags)}</i>{crop}{status}{inputs}</div>')
    key = f"cards-{batch.name}-{stamp(batch)}"
    script = (SHEET_SCRIPT.replace("__COLS__", json.dumps(schema.REVIEW_COLUMNS))
              .replace("__FIELDS__", json.dumps(schema.EDIT_FIELDS))
              .replace("__ROWS__", json.dumps(rows).replace("</", "<\\/"))
              .replace("__KEY__", json.dumps(key).replace("</", "<\\/"))) + picker_script
    name = html.escape(batch.name)
    path.write_text(
        "<!doctype html><meta charset=utf-8><title>Card review</title><style>" + STYLE + picker_css + "</style>"
        + picker_html + "<div id=bar><button id=dl>Download review.csv</button> "
        "Edits are kept in this browser. Download, then run "
        f"<code>cards sheet-import {name} ~/Downloads/review.csv</code>.</div>"
        "<div class=g>" + "".join(cells) + f"</div><script>{script}</script>",
        encoding="utf-8")
    return path
