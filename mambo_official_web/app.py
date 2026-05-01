import os, sqlite3, shutil
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE = Path(__file__).parent
DB = BASE / 'mambo.db'
UPLOAD_DIR = BASE / 'static' / 'uploads'
BACKUP_DIR = BASE / 'backups'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(exist_ok=True)

app = FastAPI(title='Project Mambo Official Web App')
app.mount('/static', StaticFiles(directory=str(BASE / 'static')), name='static')
templates = Jinja2Templates(directory=str(BASE / 'templates'))

def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with conn() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS repairs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            date TEXT,
            status TEXT DEFAULT 'pending',
            parts TEXT,
            cost REAL DEFAULT 0,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            source TEXT,
            stage TEXT DEFAULT 'warm',
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS docs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_type TEXT NOT NULL,
            filename TEXT,
            original_name TEXT,
            notes TEXT,
            ready INTEGER DEFAULT 0,
            uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS pricing (
            id INTEGER PRIMARY KEY CHECK (id=1),
            asking REAL DEFAULT 0,
            floor REAL DEFAULT 0,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')
        c.execute('INSERT OR IGNORE INTO pricing(id, asking, floor) VALUES (1,0,0)')
init_db()

DOC_TYPES = ['Inspection report','Work log','Parts bills','Before photos','After photos','Test ride note']

@app.get('/', response_class=HTMLResponse)
def index(request: Request):
    with conn() as c:
        repairs = c.execute('SELECT * FROM repairs ORDER BY id DESC').fetchall()
        leads = c.execute('SELECT * FROM leads ORDER BY CASE stage WHEN "hot" THEN 0 WHEN "warm" THEN 1 ELSE 2 END, id DESC').fetchall()
        docs = c.execute('SELECT * FROM docs ORDER BY id DESC').fetchall()
        pricing = c.execute('SELECT * FROM pricing WHERE id=1').fetchone()
    total_cost = sum([r['cost'] or 0 for r in repairs])
    done = len([r for r in repairs if r['status'] == 'done'])
    pct = round((done / len(repairs))*100) if repairs else 0
    hot = len([l for l in leads if l['stage'] == 'hot'])
    ready_docs = len(set([d['doc_type'] for d in docs if d['ready']]))
    status = 'Ready to sell' if pct == 100 and ready_docs >= 6 else ('In service' if pct or ready_docs else 'Intake')
    return templates.TemplateResponse('index.html', dict(
        request=request, repairs=repairs, leads=leads, docs=docs, pricing=pricing,
        total_cost=total_cost, done=done, pct=pct, hot=hot, ready_docs=ready_docs,
        doc_types=DOC_TYPES, status=status
    ))

@app.post('/repairs')
def add_repair(name: str = Form(...), date: str = Form(''), status: str = Form('pending'), parts: str = Form(''), cost: float = Form(0), notes: str = Form('')):
    with conn() as c:
        c.execute('INSERT INTO repairs(name,date,status,parts,cost,notes) VALUES (?,?,?,?,?,?)', (name,date,status,parts,cost,notes))
    return RedirectResponse('/', status_code=303)

@app.post('/repairs/{repair_id}/delete')
def delete_repair(repair_id: int):
    with conn() as c:
        c.execute('DELETE FROM repairs WHERE id=?', (repair_id,))
    return RedirectResponse('/', status_code=303)

@app.post('/leads')
def add_lead(name: str = Form(...), phone: str = Form(''), source: str = Form('WhatsApp'), stage: str = Form('warm'), notes: str = Form('')):
    with conn() as c:
        c.execute('INSERT INTO leads(name,phone,source,stage,notes) VALUES (?,?,?,?,?)', (name,phone,source,stage,notes))
    return RedirectResponse('/#sales', status_code=303)

@app.post('/leads/{lead_id}/delete')
def delete_lead(lead_id: int):
    with conn() as c:
        c.execute('DELETE FROM leads WHERE id=?', (lead_id,))
    return RedirectResponse('/#sales', status_code=303)

@app.post('/pricing')
def update_pricing(asking: float = Form(0), floor: float = Form(0)):
    with conn() as c:
        c.execute('UPDATE pricing SET asking=?, floor=?, updated_at=CURRENT_TIMESTAMP WHERE id=1', (asking, floor))
    return RedirectResponse('/#sales', status_code=303)

@app.post('/docs')
async def upload_doc(doc_type: str = Form(...), notes: str = Form(''), ready: int = Form(1), file: UploadFile = File(...)):
    safe = ''.join(ch for ch in file.filename if ch.isalnum() or ch in '._- ')[:120]
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    fname = f'{stamp}_{safe}'
    dest = UPLOAD_DIR / fname
    with dest.open('wb') as f:
        shutil.copyfileobj(file.file, f)
    with conn() as c:
        c.execute('INSERT INTO docs(doc_type, filename, original_name, notes, ready) VALUES (?,?,?,?,?)', (doc_type, fname, file.filename, notes, ready))
    return RedirectResponse('/#docs', status_code=303)

@app.post('/docs/{doc_id}/delete')
def delete_doc(doc_id: int):
    with conn() as c:
        row = c.execute('SELECT filename FROM docs WHERE id=?', (doc_id,)).fetchone()
        c.execute('DELETE FROM docs WHERE id=?', (doc_id,))
    if row and row['filename']:
        p = UPLOAD_DIR / row['filename']
        if p.exists(): p.unlink()
    return RedirectResponse('/#docs', status_code=303)

@app.get('/report', response_class=HTMLResponse)
def report(request: Request):
    with conn() as c:
        repairs = c.execute('SELECT * FROM repairs ORDER BY id').fetchall()
        leads = c.execute('SELECT * FROM leads ORDER BY id').fetchall()
        docs = c.execute('SELECT * FROM docs ORDER BY id').fetchall()
        pricing = c.execute('SELECT * FROM pricing WHERE id=1').fetchone()
    return templates.TemplateResponse('report.html', dict(request=request, repairs=repairs, leads=leads, docs=docs, pricing=pricing, now=datetime.now()))

@app.get('/backup')
def backup_db():
    if not DB.exists(): raise HTTPException(404, 'Database not found')
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    out = BACKUP_DIR / f'mambo_backup_{stamp}.db'
    shutil.copy(DB, out)
    return FileResponse(out, filename=out.name)
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
