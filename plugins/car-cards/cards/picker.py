"""The crop picker on review.html: a levelled view per photo, a box the reader drags, and the re-cut.

Ported from the source pipeline's crop_picker.py. The page's *Adjust crop* button shows the photo in
a frame the shape of the card picture, so what you see is what the card shows. Drag to move, scroll or
use the slider to zoom, and turn the angle slider to straighten. *Use this crop* keeps the box in the
row's ``crop`` column; *Copy command* gives ``cards crop <batch> <photo> <X,Y,W,H[,ANGLE]>``.

Box numbers are pixels on the picker's view of the photo: the levelled photo for a car (as the
automatic crop sees it), the photo as taken for a locomotive. ANGLE is degrees counter-clockwise,
added on top. A car is re-cut from that view and sharpened for print; a locomotive goes through
loco.clean, so its print copy is removed. The OCR is not re-read.

Batch files: picker.json ({photo: {"kind", "view", "scale", "auto_box", "w", "h"}}) and
picker/<stem>.<kind>.jpg. ``view`` is the preview's path in the batch, ``scale`` is full width over
preview width, ``w``/``h`` the full view size and ``auto_box`` the automatic box on that full size.
The page script expects the review page to define ROWS (each row with photo, kind, crop), a
``[data-i][data-f="crop"]`` field and a ``#c<i>`` cell per row, and an ``.adj`` button per row.
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from . import image as img_mod
from .config import Config
from .loco import REF_WIDTH, clean
from .paths import Paths

VIEW_DIR = "picker"  # inside the batch folder
DATA_FILE = "picker.json"
VIEW_WIDTH = 1600  # the page needs a preview, not the full photo; box numbers stay full size


def parse_box(text: str) -> tuple[int, int, int, int, float]:
    """"X,Y,W,H[,ANGLE]" -> (x, y, w, h, angle). Refuses boxes under 50 x 50."""
    parts = [p for p in text.replace(" ", "").split(",") if p]
    if len(parts) not in (4, 5):
        raise SystemExit(f"Crop must be X,Y,W,H or X,Y,W,H,ANGLE, not {text!r}")
    try:
        x, y, w, h = (int(round(float(p))) for p in parts[:4])
        angle = float(parts[4]) if len(parts) == 5 else 0.0
    except ValueError:
        raise SystemExit(f"Crop must be numbers: {text!r}") from None
    if w < 50 or h < 50:
        raise SystemExit(f"Crop {text!r} is too small (at least 50 x 50 pixels).")
    return x, y, w, h, angle


def format_box(box: tuple) -> str:
    """(x, y, w, h[, angle]) -> "X,Y,W,H[,ANGLE]"; an angle under 0.05 degrees is left out."""
    x, y, w, h = box[:4]
    angle = box[4] if len(box) > 4 else 0.0
    text = f"{round(x)},{round(y)},{round(w)},{round(h)}"
    return text + (f",{angle:g}" if abs(angle) >= 0.05 else "")


def read_data(batch: Path) -> dict:
    path = batch / DATA_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def write_data(batch: Path, data: dict) -> None:
    (batch / DATA_FILE).write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def source_png(row: dict, paths: Paths) -> Path:
    return paths.converted / f"{Path(row['photo']).stem}.png"


def _view(row: dict, paths: Paths):
    """The image the picker shows and the box is measured on, and the automatic box on it."""
    with Image.open(source_png(row, paths)) as im:
        im.load()
        if row.get("kind") == "loco":
            return im.copy(), [round(v) for v in img_mod._loose_box(im.size)]
        plan = img_mod.plan_crop(im)
    return plan["leveled"], [round(v) for v in plan["box"]]


def prepare(batch: Path, rows: list[dict], paths: Paths, cfg: Config, force: bool = False) -> None:
    """Write the picker views and picker.json for every row with an image. Keeps existing views
    unless force or the row's kind changed."""
    data = read_data(batch)
    for r in rows:
        if not r.get("image"):
            continue  # processing failed: nothing to crop from
        have = data.get(r["photo"])
        if have and have.get("kind") == r["kind"] and not force and (batch / have["view"]).is_file():
            continue
        if not source_png(r, paths).is_file():
            continue
        view, auto = _view(r, paths)
        out = batch / VIEW_DIR / f"{Path(r['photo']).stem}.{r['kind']}.jpg"
        out.parent.mkdir(parents=True, exist_ok=True)
        small = view.convert("RGB")
        small.thumbnail((VIEW_WIDTH, VIEW_WIDTH * 4))
        small.save(out, quality=85)
        data[r["photo"]] = {"kind": r["kind"], "view": f"{VIEW_DIR}/{out.name}",
                            "scale": round(view.size[0] / small.size[0], 4),
                            "w": view.size[0], "h": view.size[1], "auto_box": auto}
    write_data(batch, data)


def cut(row: dict, box_text: str, paths: Paths):
    """The new card picture for a box on the row's view (not saved)."""
    x, y, w, h, angle = parse_box(box_text)
    with Image.open(source_png(row, paths)) as im:
        if row["kind"] == "loco":
            photo = im.convert("RGB")
        else:
            photo, _ = img_mod._level_image(im.convert("RGB"))
    if angle:  # about the centre, same size: the picker turns the image the same way
        photo = photo.rotate(angle, resample=Image.BICUBIC, fillcolor=img_mod._backdrop_color(photo))
    out = img_mod._crop_at_fixed_size(photo, x + w / 2, y + h / 2, w, h)
    if row["kind"] == "loco":
        out = clean(out, (0, 0, REF_WIDTH, round(h * REF_WIDTH / w)))
    return out


def apply(batch: Path, row: dict, box_text: str, paths: Paths, cfg: Config) -> None:
    """Re-cut row's picture from its photo with the box; update row["image"], row["blur"], row["crop"].
    A car gets new final and print copies; a loco goes through loco.clean and loses its print copy.
    The OCR is not re-read."""
    stem = Path(row["photo"]).stem
    out = cut(row, box_text, paths)
    final = paths.final / f"{stem}.png"
    final.parent.mkdir(parents=True, exist_ok=True)
    out.save(final)
    printed = paths.print_copies / f"{stem}.png"
    if row["kind"] == "loco":
        printed.unlink(missing_ok=True)  # a stale freight-style copy would win over the new picture
    else:
        printed.parent.mkdir(parents=True, exist_ok=True)
        img_mod.sharpen_for_print(out).save(printed)
    row["image"] = paths.rel(final)
    row["blur"] = f"{img_mod.blur_score(final):.0f}"
    row["crop"] = box_text


PICKER_CSS = """
#pk{position:fixed;inset:0;background:rgba(0,0,0,.75);display:none;z-index:9;overflow:auto}
#pk.on{display:block}#pk .box{background:#fff;max-width:1100px;margin:24px auto;padding:12px 16px;border-radius:8px}
#pk .frame{position:relative;overflow:hidden;border:1px solid #999;background:#777;cursor:grab;touch-action:none;
 user-select:none;margin:8px auto}#pk .frame.drag{cursor:grabbing}
#pk .frame img,.pv img{position:absolute;left:0;top:0;max-width:none;pointer-events:none}
#pk .ctl{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;margin:8px 0}
#pk .ctl label{display:flex;gap:6px;align-items:center;margin:0;font-size:13px}
#pk .ctl input[type=range]{width:180px}#pk .ctl input[type=number]{width:5em}
#pk pre{background:#f3f3f1;padding:6px 8px;white-space:pre-wrap;margin:6px 0}
.pv{position:relative;overflow:hidden;width:100%;background:#777}
.adj{margin:4px 0}.crop-set{display:block;color:#1d5fa8;font-size:12px}
"""

PICKER_SCRIPT = r"""
const PICK=%(pick)s, BATCH=%(batch)s;
const pk=document.getElementById('pk'), fr=document.getElementById('pkf'), im=document.getElementById('pki');
const zoom=document.getElementById('pkz'), ang=document.getElementById('pka'), shp=document.getElementById('pks');
const out=document.getElementById('pko');
let cur=null, cx=0, cy=0, cw=1, ar=1, an=0, drag=null;
function parse(t){const p=(t||'').split(',').map(Number);return p.length>=4&&p.every(v=>!isNaN(v))?p:null}
function fmt(){return [cx,cy,cw,cw/ar].map(Math.round).join(',')+(Math.abs(an)>=0.05?','+(+an.toFixed(1)):'')}
function place(img,box,W,H,P){  // draw the box of photo P into a W x H frame
 const s=W/box[2], a=box[4]||0;
 img.style.width=P.w*s+'px';img.style.height=P.h*s+'px';
 img.style.left=-box[0]*s+'px';img.style.top=-box[1]*s+'px';
 img.style.transformOrigin=(P.w*s/2)+'px '+(P.h*s/2)+'px';
 img.style.transform='rotate('+(-a)+'deg)'}
function maxW(){return Math.min(cur.P.w*1.2, cur.P.h*1.2*ar)}
function size(){const avail=Math.min(pk.clientWidth-64,1060), H=Math.min(avail/ar, window.innerHeight*0.6);
 fr.style.width=H*ar+'px';fr.style.height=H+'px';return [H*ar,H]}
function render(){
 cw=Math.max(150,Math.min(cw,maxW()));
 cx=Math.max(-cw/2,Math.min(cx,cur.P.w-cw/2));const ch=cw/ar;cy=Math.max(-ch/2,Math.min(cy,cur.P.h-ch/2));
 const [W,H]=size();place(im,[cx,cy,cw,ch,an],W,H,cur.P);
 zoom.value=Math.round((1-(cw-150)/(maxW()-150))*1000);
 out.textContent='crop '+fmt()+'   ('+Math.round(cw)+' x '+Math.round(ch)+' px, shape '+ar.toFixed(2)+':1)\n'+
  'cards crop '+BATCH+' '+cur.photo+' '+fmt()}
function pickOf(i){const P=PICK[ROWS[i].photo]; return P&&P.kind===ROWS[i].kind?P:null}
function openPicker(i){const P=pickOf(i); if(!P) return;
 const set=parse(document.querySelector('[data-i="'+i+'"][data-f="crop"]').value)||P.auto;
 cur={i,P,photo:ROWS[i].photo};[cx,cy,cw]=set;ar=set[2]/set[3];an=set[4]||0;
 im.src=P.src;shp.value=ar.toFixed(2);ang.value=an;document.getElementById('pkt').textContent=ROWS[i].photo+' ('+P.kind+')';
 pk.classList.add('on');render()}
function preview(i){const P=pickOf(i), c=document.getElementById('c'+i); if(!P||!c) return;
 const v=document.querySelector('[data-i="'+i+'"][data-f="crop"]'), box=parse(v.value);
 let pv=c.querySelector('.pv'), orig=c.querySelector('img.orig'), note=c.querySelector('.crop-set');
 const done=box&&v.value===(ROWS[i].crop||'');  // already cut: the card image is the real thing
 if(!box||done){if(pv)pv.remove();if(orig)orig.style.display='';note.textContent=done?'crop '+v.value:'';return}
 if(!pv){pv=document.createElement('div');pv.className='pv';pv.innerHTML='<img>';c.insertBefore(pv,c.firstChild)}
 if(orig)orig.style.display='none';
 const W=pv.clientWidth||300,H=W*box[3]/box[2];pv.style.height=H+'px';const img=pv.querySelector('img');img.src=P.src;
 place(img,box,W,H,P);note.textContent='new crop '+v.value+' (applied by cards sheet-import)'}
fr.addEventListener('pointerdown',e=>{drag={x:e.clientX,y:e.clientY,cx,cy};fr.setPointerCapture(e.pointerId);fr.classList.add('drag')});
fr.addEventListener('pointermove',e=>{if(!drag)return;const s=fr.clientWidth/cw;
 // the box is measured on the turned photo, so a move on screen is a move of the box
 const dx=(e.clientX-drag.x)/s, dy=(e.clientY-drag.y)/s;
 cx=drag.cx-dx;cy=drag.cy-dy;render()});
const end=()=>{drag=null;fr.classList.remove('drag')};fr.addEventListener('pointerup',end);fr.addEventListener('pointercancel',end);
function zoomAt(f,px,py){const s=fr.clientWidth/cw, ox=cx+px/s, oy=cy+py/s;
 cw=Math.max(150,Math.min(maxW(),cw*f));const ns=fr.clientWidth/cw;cx=ox-px/ns;cy=oy-py/ns;render()}
fr.addEventListener('wheel',e=>{e.preventDefault();const r=fr.getBoundingClientRect();
 zoomAt(e.deltaY>0?1.06:1/1.06,e.clientX-r.left,e.clientY-r.top)},{passive:false});
zoom.addEventListener('input',()=>{const W=fr.clientWidth,H=fr.clientHeight,t=zoom.value/1000;
 zoomAt((maxW()-t*(maxW()-150))/cw,W/2,H/2)});
ang.addEventListener('input',()=>{an=+ang.value;render()});
shp.addEventListener('change',()=>{const v=+shp.value;if(v>0.3&&v<10){const ch=cw/ar,my=cy+ch/2;ar=v;cy=my-cw/ar/2;render()}});
document.getElementById('pkr').onclick=()=>{const a=cur.P.auto;[cx,cy,cw]=a;ar=a[2]/a[3];an=0;ang.value=0;shp.value=ar.toFixed(2);render()};
document.getElementById('pkc').onclick=()=>{if(navigator.clipboard)navigator.clipboard.writeText('cards crop '+BATCH+' '+cur.photo+' '+fmt()).catch(()=>{})};
document.getElementById('pku').onclick=()=>{const v=document.querySelector('[data-i="'+cur.i+'"][data-f="crop"]');
 v.value=fmt();v.dispatchEvent(new Event('input'));preview(cur.i);pk.classList.remove('on')};
document.getElementById('pkx').onclick=()=>pk.classList.remove('on');
document.getElementById('pkn').onclick=()=>{const v=document.querySelector('[data-i="'+cur.i+'"][data-f="crop"]');
 v.value='';v.dispatchEvent(new Event('input'));preview(cur.i);pk.classList.remove('on')};
document.addEventListener('keydown',e=>{if(e.key==='Escape')pk.classList.remove('on')});
window.addEventListener('resize',()=>{if(pk.classList.contains('on'))render()});
document.querySelectorAll('.adj').forEach(b=>b.onclick=()=>openPicker(+b.dataset.i));
ROWS.forEach((_,i)=>preview(i));
"""

PICKER_HTML = """
<div id=pk><div class=box><b id=pkt></b>
<p style="margin:4px 0">Drag the photo to move it, scroll or use the zoom slider to zoom, and turn the angle
slider to straighten. The frame is the shape of the card image, so what you see is what the card
shows. Change the shape (width&nbsp;:&nbsp;height) for a taller or wider image.</p>
<div class=frame id=pkf><img id=pki alt=""></div>
<div class=ctl><label>Zoom <input type=range id=pkz min=0 max=1000></label>
<label>Angle <input type=range id=pka min=-8 max=8 step=0.1 value=0></label>
<label>Shape <input type=number id=pks step=0.05 min=0.5 max=8></label>
<button id=pkr>Automatic crop</button><button id=pkc>Copy command</button>
<button id=pkn>Clear new crop</button><button id=pku><b>Use this crop</b></button><button id=pkx>Close</button></div>
<pre id=pko></pre></div></div>
"""

def page_parts(batch: Path) -> tuple[str, str, str]:
    """(css, html, script) the review page embeds for Adjust crop; three '' when picker.json is absent."""
    data = read_data(batch)
    pick = {photo: {"kind": d["kind"], "src": f"{VIEW_DIR}/{Path(d['view']).name}", "w": d["w"], "h": d["h"],
                    "auto": d["auto_box"]}
            for photo, d in data.items() if (batch / d["view"]).is_file()}
    if not pick:
        return "", "", ""
    script = PICKER_SCRIPT % {"pick": json.dumps(pick).replace("</", "<\\/"),
                              "batch": json.dumps(batch.name)}
    return PICKER_CSS, PICKER_HTML, script
