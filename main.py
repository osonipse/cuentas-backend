"""
cuentas-backend · MVP
=====================
Backend local que conecta la app Cuentas con Enablebanking (sandbox/producción).
Corre en tu máquina. Ningún dato sale a internet salvo las llamadas a Enablebanking.

Uso:
  pip install -r requirements.txt
  python main.py

Luego abre: http://localhost:8000
"""

import os, json, time, uuid, hashlib, base64, httpx
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# ════════════════════════════════════════
#  CONFIG
# ════════════════════════════════════════
PORT          = int(os.getenv("PORT", 8000))
APP_NAME      = os.getenv("APP_NAME", "Cuentas")
EB_APP_ID     = os.getenv("EB_APP_ID", "")       # Tu Application ID de Enablebanking
EB_KEY_PATH   = os.getenv("EB_KEY_PATH", "")     # Ruta a tu private key .pem
EB_SANDBOX    = os.getenv("EB_SANDBOX", "true").lower() == "true"
REDIRECT_URL  = os.getenv("REDIRECT_URL", f"http://localhost:{PORT}/callback")
FRONTEND_URL  = os.getenv("FRONTEND_URL", "")    # Si tienes la app en otra URL

EB_BASE       = "https://api.enablebanking.com"
DATA_FILE     = Path("data.json")

# ════════════════════════════════════════
#  ESTADO LOCAL (JSON en disco)
# ════════════════════════════════════════
def load_data() -> dict:
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text())
        except:
            pass
    return {"sessions": {}, "transactions": [], "accounts": []}

def save_data(d: dict):
    DATA_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2, default=str))

state = load_data()

# ════════════════════════════════════════
#  JWT PARA ENABLEBANKING
#  Enablebanking usa JWT firmado con tu private key
# ════════════════════════════════════════
def make_eb_jwt() -> str:
    """Genera el JWT de autenticación para Enablebanking."""
    if not EB_APP_ID or not EB_KEY_PATH:
        raise HTTPException(500, "EB_APP_ID y EB_KEY_PATH no configurados. Ver .env.example")
    
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    import time

    header  = {"alg": "RS256", "typ": "JWT", "kid": EB_APP_ID}
    payload = {
        "iss": EB_APP_ID,
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }

    def b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    h = b64url(json.dumps(header).encode())
    p = b64url(json.dumps(payload).encode())
    msg = f"{h}.{p}".encode()

    key_data = Path(EB_KEY_PATH).read_bytes()
    private_key = serialization.load_pem_private_key(key_data, password=None)
    sig = private_key.sign(msg, padding.PKCS1v15(), hashes.SHA256())

    return f"{h}.{p}.{b64url(sig)}"

async def eb_get(path: str, params: dict = None) -> dict:
    jwt = make_eb_jwt()
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{EB_BASE}{path}", params=params,
                        headers={"Authorization": f"Bearer {jwt}"}, timeout=20)
        if not r.is_success:
            raise HTTPException(r.status_code, f"Enablebanking error: {r.text}")
        return r.json()

async def eb_post(path: str, body: dict) -> dict:
    jwt = make_eb_jwt()
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{EB_BASE}{path}", json=body,
                         headers={"Authorization": f"Bearer {jwt}",
                                  "Content-Type": "application/json"}, timeout=20)
        if not r.is_success:
            raise HTTPException(r.status_code, f"Enablebanking error: {r.text}")
        return r.json()

# ════════════════════════════════════════
#  APP
# ════════════════════════════════════════
app = FastAPI(title="Cuentas Backend", version="0.1.0")

app.add_middleware(CORSMiddleware,
    allow_origins=["*"],   # En producción limitar al dominio de la app
    allow_methods=["*"],
    allow_headers=["*"])


# ── DEBUG ──
@app.get("/debug")
async def debug():
    return {"REDIRECT_URL": REDIRECT_URL, "EB_SANDBOX": EB_SANDBOX, "EB_APP_ID": EB_APP_ID[:8]+"..."}

# ── SYNC BRIDGE ──
@app.get("/sync-bridge", response_class=HTMLResponse)
async def serve_bridge():
    return HTMLResponse("""<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8"><title>Cuentas Sync</title>
<style>
body{font-family:sans-serif;background:#0a0b10;color:#e8e9ec;display:flex;align-items:center;
justify-content:center;height:100vh;margin:0;flex-direction:column;gap:20px}
h1{color:#b8ff5a;font-size:24px}
button{background:#b8ff5a;color:#0a0b10;border:none;border-radius:10px;
padding:14px 32px;font-size:16px;font-weight:800;cursor:pointer}
#st{font-size:14px;color:#7880a8}
.ok{color:#b8ff5a!important}.err{color:#ff5f7a!important}
</style></head><body>
<h1>Cuentas · Importar transacciones</h1>
<p id="st">Conectando con el backend...</p>
<button onclick="doImport()">Importar ahora</button>
<script>
async function doImport(){
  const s=document.getElementById('st');
  s.textContent='Descargando...';
  try{
    const r=await fetch('/transactions?limit=1000');
    const data=await r.json();
    const txs=data.transactions||[];
    const KEY='finanza_v2';
    let state={user:{name:'',claudeKey:''},txs:[],invs:[],budgets:{},imports:[]};
    try{const d=localStorage.getItem(KEY);if(d)state={...state,...JSON.parse(d)};}catch(e){}
    let n=0,dup=0;
    txs.forEach(t=>{
      const exists=state.txs.find(x=>
        x.date===t.date &&
        Math.abs(x.amount-t.amount)<0.01 &&
        (x.desc||'').toLowerCase()===(t.desc||'').toLowerCase()
      );
      if(exists){dup++;return;}
      state.txs.push({
        id:Date.now().toString(36)+Math.random().toString(36).slice(2,5),
        date:t.date,desc:t.desc,amount:t.amount,
        cat:t.cat||'Otros',acc:t.acc||'Banco',src:'sync'
      });
      n++;
    });
    localStorage.setItem(KEY,JSON.stringify(state));
    s.className='ok';
    s.textContent=n+' transacciones importadas'+(dup?' · '+dup+' ya existian':'');
    setTimeout(()=>window.location.href='/app',2000);
  }catch(e){s.className='err';s.textContent='Error: '+e.message;}
}
fetch('/status')
  .then(r=>r.json())
  .then(d=>{
    document.getElementById('st').textContent=d.transactions+' transacciones disponibles';
    document.getElementById('st').className='ok';
  })
  .catch(()=>{});
</script></body></html>""")

# ── APP ──
@app.get("/app", response_class=HTMLResponse)
async def serve_app():
    candidates = [
        Path("../finanza2.html"),
        Path("../../finanza2.html"),
        Path("finanza2.html"),
    ]
    parent = Path("..").resolve()
    found = list(parent.glob("**/finanza2.html"))
    candidates += found
    for p in candidates:
        if p.exists():
            content = p.read_text(encoding='utf-8')
            content = content.replace(
                "const SYNC_PORT = new URLSearchParams(window.location.search).get('sync_port') || 7432;",
                f"const SYNC_PORT = {PORT};"
            )
            return HTMLResponse(content)
    return HTMLResponse("<h1>finanza2.html no encontrado</h1><p>Coloca finanza2.html en la carpeta ProyectoFintonic</p>")


# ── RAÍZ: instrucciones ──
@app.get("/", response_class=HTMLResponse)
async def root():
    configured = bool(EB_APP_ID and EB_KEY_PATH)
    env = "🟡 SANDBOX" if EB_SANDBOX else "🟢 PRODUCCIÓN"
    status_color = "#22c55e" if configured else "#ef4444"
    status_text  = "✓ Configurado" if configured else "✗ Faltan EB_APP_ID y EB_KEY_PATH en .env"
    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><title>Cuentas Backend</title>
<style>body{{font-family:monospace;background:#0f0f0f;color:#e5e7eb;padding:40px;max-width:700px;margin:0 auto}}
h1{{color:#c8f060;font-size:28px}}h2{{color:#94a3b8;font-size:14px;font-weight:400;margin-top:-10px}}
.card{{background:#1a1a1a;border:1px solid #2a2a2a;border-radius:12px;padding:24px;margin:20px 0}}
.ok{{color:#22c55e}}.err{{color:#ef4444}}.warn{{color:#fbbf24}}
a{{color:#60a5fa;text-decoration:none}}
code{{background:#111;padding:2px 8px;border-radius:4px;font-size:13px}}
table{{width:100%;border-collapse:collapse}}td{{padding:8px 12px;border-bottom:1px solid #2a2a2a;font-size:13px}}
td:first-child{{color:#94a3b8;width:160px}}</style>
</head><body>
<h1>⚡ Cuentas Backend</h1>
<h2>MVP · Open Banking via Enablebanking</h2>

<div class="card">
<table>
<tr><td>Estado</td><td style="color:{status_color}">{status_text}</td></tr>
<tr><td>Entorno</td><td>{env}</td></tr>
<tr><td>App ID</td><td>{EB_APP_ID or '<em style="color:#666">no configurado</em>'}</td></tr>
<tr><td>Redirect URL</td><td><code>{REDIRECT_URL}</code></td></tr>
<tr><td>Transacciones</td><td>{len(state["transactions"])} guardadas</td></tr>
<tr><td>Sesiones</td><td>{len(state["sessions"])} activas</td></tr>
</table>
</div>

<div class="card">
<p style="color:#94a3b8;margin-bottom:16px;font-size:13px">Endpoints principales:</p>
<table>
<tr><td>GET /banks</td><td>Lista de bancos disponibles por país</td></tr>
<tr><td>GET /connect?bank=BBVA&country=ES</td><td>Inicia conexión con un banco</td></tr>
<tr><td>GET /callback</td><td>Callback OAuth (automático)</td></tr>
<tr><td>GET /transactions</td><td>Todas las transacciones guardadas</td></tr>
<tr><td>GET /accounts</td><td>Cuentas conectadas</td></tr>
<tr><td>POST /sync</td><td>Resync de todas las sesiones activas</td></tr>
<tr><td>GET /status</td><td>Estado del servidor (JSON)</td></tr>
</table>
</div>

{'<div class="card"><p class="err">⚠ Configura tu .env antes de continuar.</p><p style="font-size:13px;color:#94a3b8;margin-top:8px">Copia <code>.env.example</code> a <code>.env</code> y añade tu Application ID y ruta a la private key de Enablebanking.</p></div>' if not configured else '<div class="card"><p class="ok">✓ Listo. Ve a <a href="/banks?country=ES">/banks?country=ES</a> para ver los bancos disponibles.</p></div>'}
</body></html>"""

# ── STATUS JSON ──
@app.get("/status")
async def status():
    return {
        "ok": True,
        "configured": bool(EB_APP_ID and EB_KEY_PATH),
        "sandbox": EB_SANDBOX,
        "transactions": len(state["transactions"]),
        "sessions": len(state["sessions"]),
        "accounts": len(state["accounts"]),
    }

# ── LISTA DE BANCOS ──
@app.get("/banks")
async def get_banks(country: str = Query("ES", description="ISO 3166 country code")):
    """Lista todos los bancos disponibles en un país vía Enablebanking."""
    data = await eb_get("/aspsps", {"country": country})
    banks = []
    for b in data.get("aspsps", []):
        banks.append({
            "name":     b.get("name"),
            "country":  b.get("country"),
            "bic":      b.get("bic"),
            "logo":     b.get("logo"),
            "sandbox":  b.get("sandbox_enabled", False),
        })
    return {"banks": banks, "total": len(banks), "country": country}

# ── INICIAR CONEXIÓN CON BANCO ──
@app.get("/connect")
async def connect_bank(
    bank: str    = Query(...,  description="Nombre del banco, ej: BBVA"),
    country: str = Query("ES", description="Código país ISO")
):
    """
    Genera la URL de autenticación para que el usuario autorice acceso a su banco.
    Redirige automáticamente al banco.
    """
    session_state = str(uuid.uuid4())

    body = {
        "access": {"balances": True, "transactions": True,
                   "valid_until": (datetime.utcnow() + timedelta(days=90)).isoformat() + "Z"},
        "aspsp": {"name": bank, "country": country},
        "psu_type": "personal",
        "redirect_url": REDIRECT_URL,
        "state": session_state,
    }

    if EB_SANDBOX:
        body["aspsp"]["name"] = bank  # En sandbox usa el nombre tal cual

    data = await eb_post("/auth", body)
    auth_url = data.get("url")
    auth_id  = data.get("authorization_id")

    if not auth_url:
        raise HTTPException(500, "Enablebanking no devolvió URL de autenticación")

    # Guardar estado pendiente
    state["sessions"][session_state] = {
        "authorization_id": auth_id,
        "bank": bank,
        "country": country,
        "created": datetime.utcnow().isoformat(),
        "session_id": None,
        "accounts": [],
        "status": "pending",
    }
    save_data(state)

    return RedirectResponse(auth_url)

# ── CALLBACK OAUTH ──
@app.get("/callback")
async def oauth_callback(
    code:  Optional[str] = Query(None),
    state_param: str     = Query(None, alias="state"),
    error: Optional[str] = Query(None)
):
    """Enablebanking redirige aquí tras la autenticación del usuario."""
    if error:
        return HTMLResponse(f"""<html><body style="font-family:monospace;background:#0f0f0f;color:#ef4444;padding:40px">
        <h2>❌ Autorización cancelada o rechazada</h2>
        <p>{error}</p>
        <p><a href="/" style="color:#60a5fa">← Volver</a></p></body></html>""")

    session_info = state["sessions"].get(state_param)
    if not session_info:
        raise HTTPException(400, "Estado de sesión no reconocido")

    # Confirmar sesión con Enablebanking
    sess_data = await eb_post("/sessions", {"code": code, "redirect_url": REDIRECT_URL})
    session_id = sess_data.get("session_id")
    accounts   = sess_data.get("accounts", [])

    session_info["session_id"] = session_id
    session_info["accounts"]   = accounts
    session_info["status"]     = "active"
    session_info["connected"]  = datetime.utcnow().isoformat()

    # Guardar cuentas
    bank = session_info["bank"]
    for acc in accounts:
        acc_id = acc.get("uid")
        if not any(a.get("uid") == acc_id for a in state["accounts"]):
            state["accounts"].append({
                "uid":        acc_id,
                "bank":       bank,
                "iban":       acc.get("account_id", {}).get("iban", ""),
                "name":       acc.get("name", bank),
                "currency":   acc.get("currency", "EUR"),
                "session_id": session_id,
            })

    save_data(state)

    # Importar transacciones inmediatamente
    tx_count = await _fetch_transactions(session_id, accounts, bank)

    frontend = FRONTEND_URL or "/"
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8"><title>Conectado</title>
<style>body{{font-family:monospace;background:#0f0f0f;color:#e5e7eb;padding:40px;text-align:center}}
h2{{color:#c8f060}}p{{color:#94a3b8}}a{{color:#60a5fa}}</style>
</head><body>
<h2>✅ {bank} conectado correctamente</h2>
<p>Se han importado <strong style="color:#c8f060">{tx_count} transacciones</strong></p>
<p style="margin-top:24px">
  <a href="{frontend}?sync_port={PORT}">← Volver a Cuentas</a> &nbsp;|&nbsp;
  <a href="/transactions">Ver transacciones JSON</a>
</p>
<script>
  // Si la app está abierta en otra pestaña, notificarla
  if(window.opener) {{
    window.opener.postMessage({{type:'SYNC_COMPLETE',count:{tx_count}}}, '*');
    setTimeout(()=>window.close(), 2000);
  }}
</script>
</body></html>""")

# ── FETCH TRANSACTIONS (interno) ──
async def _fetch_transactions(session_id: str, accounts: list, bank: str) -> int:
    """Descarga transacciones de todas las cuentas de una sesión."""
    jwt = make_eb_jwt()
    count = 0
    date_from = (datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%d")

    async with httpx.AsyncClient() as c:
        for acc in accounts:
            acc_uid  = acc.get("uid")
            acc_iban = acc.get("account_id", {}).get("iban", "")
            try:
                params = {"date_from": date_from}
                r = await c.get(
                    f"{EB_BASE}/accounts/{acc_uid}/transactions",
                    params=params,
                    headers={"Authorization": f"Bearer {jwt}"},
                    timeout=30
                )
                if not r.is_success:
                    continue

                txs = r.json().get("transactions", [])
                for tx in txs:
                    tx_id = tx.get("entry_reference") or str(uuid.uuid4())
                    # Deduplicar
                    if any(t.get("id") == tx_id for t in state["transactions"]):
                        continue

                    # Normalizar importe
                    amt_data = tx.get("transaction_amount", {})
                    amount   = float(amt_data.get("amount", 0))
                    if tx.get("credit_debit_indicator") == "DBIT":
                        amount = -abs(amount)
                    else:
                        amount = abs(amount)

                    desc = (tx.get("remittance_information") or [""])[0]
                    if not desc:
                        desc = (tx.get("creditor") or {}).get("name", "") or \
                               (tx.get("debtor")   or {}).get("name", "") or \
                               "Movimiento bancario"

                    date = tx.get("booking_date") or tx.get("value_date") or \
                           datetime.utcnow().strftime("%Y-%m-%d")

                    state["transactions"].append({
                        "id":     tx_id,
                        "date":   date,
                        "desc":   desc,
                        "amount": amount,
                        "cat":    guess_category(desc, amount),
                        "acc":    bank,
                        "iban":   acc_iban,
                        "src":    "enablebanking",
                    })
                    count += 1

            except Exception as e:
                print(f"Error fetching {acc_uid}: {e}")

    if count > 0:
        save_data(state)
    return count

# ── TRANSACCIONES ──
@app.get("/transactions")
async def get_transactions(
    limit:  int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    bank:   Optional[str] = Query(None),
    since:  Optional[str] = Query(None, description="Fecha ISO YYYY-MM-DD")
):
    txs = state["transactions"]
    if bank:
        txs = [t for t in txs if t.get("acc", "").lower() == bank.lower()]
    if since:
        txs = [t for t in txs if t.get("date", "") >= since]
    txs = sorted(txs, key=lambda t: t.get("date",""), reverse=True)
    return {
        "transactions": txs[offset:offset+limit],
        "total": len(txs),
        "offset": offset,
        "limit": limit,
    }

# ── CUENTAS ──
@app.get("/accounts")
async def get_accounts():
    return {"accounts": state["accounts"], "total": len(state["accounts"])}

# ── SYNC ──
@app.post("/sync")
async def sync_all():
    """Resync de todas las sesiones activas."""
    total = 0
    for sess_state, info in state["sessions"].items():
        if info.get("status") != "active" or not info.get("session_id"):
            continue
        try:
            n = await _fetch_transactions(
                info["session_id"], info["accounts"], info["bank"]
            )
            total += n
        except Exception as e:
            print(f"Sync error {info['bank']}: {e}")
    return {"synced": total, "message": f"{total} nuevas transacciones importadas"}

# ── BORRAR DATOS ──
@app.delete("/data")
async def clear_data():
    global state
    state = {"sessions": {}, "transactions": [], "accounts": []}
    save_data(state)
    return {"ok": True, "message": "Datos borrados"}

# ════════════════════════════════════════
#  CATEGORIZACIÓN
# ════════════════════════════════════════
def guess_category(desc: str, amount: float) -> str:
    if amount > 0:
        return "Ingresos"
    d = desc.lower()
    if any(x in d for x in ["mercadona","carrefour","lidl","aldi","dia ","eroski","consum","alcampo","supermercado","froiz"]):
        return "Alimentación"
    if any(x in d for x in ["alquiler","hipoteca","comunidad","ibi","arrendamiento"]):
        return "Vivienda"
    if any(x in d for x in ["repsol","bp ","cepsa","gasolina","renfe","metro ","taxi","uber","cabify","peaje","parking","autopista"]):
        return "Transporte"
    if any(x in d for x in ["netflix","spotify","amazon prime","hbo","disney","apple ","google play","suscripci","dazn"]):
        return "Suscripciones"
    if any(x in d for x in ["restaurante","bar ","cafeteria","mcdonalds","burger","pizza","tapas","mesón"]):
        return "Restaurantes"
    if any(x in d for x in ["farmacia","medico","clínica","clinica","hospital","dentista","optica"]):
        return "Salud"
    if any(x in d for x in ["nomina","nómina","salario","sueldo"]):
        return "Ingresos"
    if any(x in d for x in ["degiro","etoro","myinvestor","broker","fondos","bolsa"]):
        return "Inversiones"
    return "Otros"

# ════════════════════════════════════════
#  ARRANQUE
# ════════════════════════════════════════
if __name__ == "__main__":
    import uvicorn
    print(f"""
╔══════════════════════════════════════════════╗
║   Cuentas Backend · MVP                      ║
║   http://localhost:{PORT}                       ║
╚══════════════════════════════════════════════╝

  EB_APP_ID   : {EB_APP_ID or '⚠ NO CONFIGURADO'}
  EB_KEY_PATH : {EB_KEY_PATH or '⚠ NO CONFIGURADO'}
  Entorno     : {'SANDBOX' if EB_SANDBOX else 'PRODUCCIÓN'}
  Datos       : {DATA_FILE.absolute()}
""")
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)
# force redeploy
