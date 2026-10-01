import os
import sys
import uuid
import shutil
import hashlib
import threading
import subprocess
import urllib.request
import urllib.parse
import json
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, Form, Query, HTTPException, BackgroundTasks, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Kyostrgr Method TikTok Video Optimizer", version="2.2.4")

# Enable CORS for Chrome Extension requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_DIR = "/tmp/kyostrgr_processing"
os.makedirs(TEMP_DIR, exist_ok=True)

SECRET_SALT = "KYOSTRGR_2026_BLACKHOLE"
TG_BOT_TOKEN = "8786032101:AAFkMfKor6pLC17pTm2hNXsCzt543WkQurA"
ADMIN_CHAT_ID = "7089606046"

def is_valid_license(token: str) -> bool:
    if not token:
        return False
    clean = token.replace("Bearer ", "").replace("kyo_", "").strip().upper()
    if clean in ("KYO-VIP-8888-2026", "KYO-48S9-DKIK-Q96L") or clean.startswith("VIP-"):
        return True
    parts = clean.split("-")
    if len(parts) == 4 and parts[0] == "KYO" and len(parts[1]) == 4 and len(parts[2]) == 4 and len(parts[3]) == 4:
        raw = parts[1] + parts[2]
        expected = hashlib.sha256((raw + SECRET_SALT).encode("utf-8")).hexdigest()[:4].upper()
        return parts[3] == expected
    return False

def cleanup_files(*paths):
    for p in paths:
        try:
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            elif os.path.isfile(p):
                os.remove(p)
        except Exception:
            pass

@app.get("/")
def index():
    return {
        "status": "online",
        "service": "Kyostrgr TikTok Optimizer",
        "version": "2.2.4",
        "engine": "FFmpeg Native Server Edition (Hugging Face 16GB)",
        "docs": "/docs"
    }

@app.get("/api/psver")
def psver():
    """Compatibility endpoint for extension health checks"""
    return {
        "ps_version": "v22",
        "server_location": "HuggingFace-France",
        "online": True
    }

@app.post("/api/process")
async def process_direct(
    background_tasks: BackgroundTasks,
    request: Request,
    video: UploadFile = File(...),
    auth_token: str = Query(None),
    auth_userid: str = Query(None)
):
    token = auth_token or request.headers.get("Authorization", "")
    if not is_valid_license(token):
        raise HTTPException(status_code=401, detail="Licence invalide ou expirée. Obtenez votre clé sur @KyostrgrBot")

    job_id = str(uuid.uuid4())
    in_file = os.path.join(TEMP_DIR, f"{job_id}_in_{video.filename}")
    out_file = os.path.join(TEMP_DIR, f"{job_id}_out.mp4")

    # Save uploaded video
    with open(in_file, "wb") as f:
        shutil.copyfileobj(video.file, f)

    # Encode with Kyostrgr TikTok Magic Recipe
    cmd = [
        "ffmpeg", "-y", "-i", in_file,
        "-vf", "scale='if(gt(iw,ih),-2,min(1080,iw))':'if(gt(iw,ih),min(1080,ih),-2)'",
        "-r", "60",
        "-c:v", "libx264",
        "-profile:v", "high",
        "-level", "4.1",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-b:v", "14M",
        "-maxrate", "18M",
        "-bufsize", "28M",
        "-preset", "fast",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        out_file
    ]

    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if res.returncode != 0 or not os.path.exists(out_file):
        cleanup_files(in_file, out_file)
        raise HTTPException(status_code=500, detail="Erreur d'encodage FFmpeg")

    background_tasks.add_task(cleanup_files, in_file, out_file)
    return FileResponse(
        out_file,
        media_type="video/mp4",
        filename="optimized_" + video.filename
    )

# ----------------- CHUNKED UPLOAD SUPPORT (> 20MB) -----------------
@app.post("/api/upload/init")
async def upload_init(request: Request, auth_token: str = Query(None)):
    token = auth_token or request.headers.get("Authorization", "")
    if not is_valid_license(token):
        raise HTTPException(status_code=401, detail="Licence invalide")

    job_id = str(uuid.uuid4())
    job_dir = os.path.join(TEMP_DIR, f"job_{job_id}")
    os.makedirs(job_dir, exist_ok=True)
    return {"job_id": job_id, "job_otu": token}

@app.post("/api/upload/chunk")
async def upload_chunk(
    request: Request,
    job_id: str = Query(...),
    chunk_index: int = Query(...)
):
    job_dir = os.path.join(TEMP_DIR, f"job_{job_id}")
    if not os.path.exists(job_dir):
        raise HTTPException(status_code=404, detail="Session expirée")

    chunk_file = os.path.join(job_dir, f"chunk_{chunk_index:05d}.bin")
    body = await request.body()
    with open(chunk_file, "wb") as f:
        f.write(body)

    return {"status": "ok", "chunk": chunk_index}

@app.post("/api/upload/complete")
async def upload_complete(
    background_tasks: BackgroundTasks,
    job_id: str = Query(...)
):
    job_dir = os.path.join(TEMP_DIR, f"job_{job_id}")
    if not os.path.exists(job_dir):
        raise HTTPException(status_code=404, detail="Job non trouvé")

    in_file = os.path.join(TEMP_DIR, f"{job_id}_merged.mp4")
    out_file = os.path.join(TEMP_DIR, f"{job_id}_done.mp4")

    # Merge chunks
    chunks = sorted([os.path.join(job_dir, f) for f in os.listdir(job_dir) if f.startswith("chunk_")])
    with open(in_file, "wb") as outfile:
        for c in chunks:
            with open(c, "rb") as infile:
                shutil.copyfileobj(infile, outfile)

    # Encode with FFmpeg
    cmd = [
        "ffmpeg", "-y", "-i", in_file,
        "-vf", "scale='if(gt(iw,ih),-2,min(1080,iw))':'if(gt(iw,ih),min(1080,ih),-2)'",
        "-r", "60",
        "-c:v", "libx264",
        "-profile:v", "high",
        "-level", "4.1",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-b:v", "14M",
        "-maxrate", "18M",
        "-bufsize", "28M",
        "-preset", "fast",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        out_file
    ]

    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if res.returncode != 0 or not os.path.exists(out_file):
        cleanup_files(in_file, out_file, job_dir)
        raise HTTPException(status_code=500, detail="Erreur encodage vidéo")

    background_tasks.add_task(cleanup_files, in_file, out_file, job_dir)
    return FileResponse(out_file, media_type="video/mp4", filename="optimized.mp4")

# ----------------- TELEGRAM BOT INTEGRATED RUNNER -----------------
def telegram_bot_worker():
    """Tourne en tâche de fond pour que le bot Telegram reste actif 24h/24 gratuitement"""
    offset = 0
    api_base = f"https://api.telegram.org/bot{TG_BOT_TOKEN}"
    print("[HF-Bot] Bot Telegram initialisé en tâche de fond...")
    while True:
        try:
            url = f"{api_base}/getUpdates?offset={offset}&timeout=25"
            req = urllib.request.Request(url, headers={"User-Agent": "KyostrgrBot/2.0"})
            with urllib.request.urlopen(req, timeout=35) as resp:
                data = json.loads(resp.read().decode())
                if data.get("ok"):
                    for update in data.get("result", []):
                        offset = update["update_id"] + 1
                        msg = update.get("message")
                        if not msg:
                            continue
                        text = msg.get("text", "")
                        chat_id = msg.get("chat", {}).get("id")
                        if text.startswith("/start") or text.startswith("/key"):
                            # Generate key
                            import string, random
                            chars = string.ascii_uppercase + string.digits
                            p1 = "".join(random.choice(chars) for _ in range(4))
                            p2 = "".join(random.choice(chars) for _ in range(4))
                            chk = hashlib.sha256((p1 + p2 + SECRET_SALT).encode("utf-8")).hexdigest()[:4].upper()
                            key = f"KYO-{p1}-{p2}-{chk}"
                            
                            reply = (
                                "⚡ *VOTRE LICENCE KYOSTRGR METHOD*\n"
                                "━━━━━━━━━━━━━━━━━━━━\n"
                                f"🔑 *Clé :* `{key}`\n\n"
                                "🚀 *Activation :* Entrez cette clé dans l'extension Chrome pour débloquer l'encodage 1080p 60 FPS !"
                            )
                            send_url = f"{api_base}/sendMessage"
                            payload = json.dumps({"chat_id": chat_id, "text": reply, "parse_mode": "Markdown"}).encode()
                            s_req = urllib.request.Request(send_url, data=payload, headers={"Content-Type": "application/json"})
                            urllib.request.urlopen(s_req, timeout=10)
        except Exception:
            import time
            time.sleep(3)

# Démarre le bot Telegram en thread d'arrière-plan
threading.Thread(target=telegram_bot_worker, daemon=True).start()
