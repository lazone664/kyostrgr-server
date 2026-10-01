import os
import sys
import uuid
import shutil
import hashlib
import subprocess
from fastapi import FastAPI, UploadFile, File, Query, HTTPException, BackgroundTasks, Request
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Kyostrgr Method TikTok Video Optimizer", version="2.2.4")

# Autorise les requêtes directes depuis l'extension Chrome
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

def is_valid_license(token: str) -> bool:
    if not token:
        return True
    clean = token.replace("Bearer ", "").replace("kyo_", "").strip().upper()
    if clean in ("KYO-VIP-8888-2026", "KYO-48S9-DKIK-Q96L", "USER") or clean.startswith("VIP-"):
        return True
    parts = clean.split("-")
    if len(parts) == 4 and parts[0] == "KYO" and len(parts[1]) == 4 and len(parts[2]) == 4 and len(parts[3]) == 4:
        raw = parts[1] + parts[2]
        expected = hashlib.sha256((raw + SECRET_SALT).encode("utf-8")).hexdigest()[:4].upper()
        return parts[3] == expected
    return True

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
        "engine": "FFmpeg Native 1080p 60FPS High@L4.1",
        "docs": "/docs"
    }

@app.get("/api/psver")
def psver():
    return {
        "ps_version": "v22",
        "server_location": "Render-Frankfurt",
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
    print(f"[*] Traitement vidéo reçu : {video.filename}", flush=True)

    job_id = str(uuid.uuid4())
    in_file = os.path.join(TEMP_DIR, f"{job_id}_in_{video.filename}")
    out_file = os.path.join(TEMP_DIR, f"{job_id}_out.mp4")

    # Enregistrement du fichier uploadé
    with open(in_file, "wb") as f:
        shutil.copyfileobj(video.file, f)

    file_size_mb = os.path.getsize(in_file) / (1024 * 1024)
    print(f"[*] Fichier reçu ({file_size_mb:.2f} MB)", flush=True)

    # Recette Magique TikTok : 1080p + 60 FPS + H.264 High@L4.1 + yuv420p + faststart
    cmd = [
        "ffmpeg", "-y", "-i", in_file,
        "-threads", "2",
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
        "-preset", "superfast",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        out_file
    ]

    print(f"[*] Exécution FFmpeg...", flush=True)
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if res.returncode != 0 or not os.path.exists(out_file):
        err_msg = res.stderr.decode("utf-8", errors="ignore")[-500:]
        print(f"[X] Erreur FFmpeg: {err_msg}", flush=True)
        cleanup_files(in_file, out_file)
        raise HTTPException(status_code=500, detail=f"Erreur encodage: {err_msg}")

    out_size_mb = os.path.getsize(out_file) / (1024 * 1024)
    print(f"[+] SUCCÈS ! Vidéo 1080p 60 FPS prête : {out_size_mb:.2f} MB", flush=True)

    background_tasks.add_task(cleanup_files, in_file, out_file)
    return FileResponse(
        out_file,
        media_type="video/mp4",
        filename="optimized_" + video.filename
    )

# ----------------- SUPPORT UPLOADS PAR CHUNKS (> 20MB) -----------------
@app.post("/api/upload/init")
async def upload_init(request: Request, auth_token: str = Query(None)):
    job_id = str(uuid.uuid4())
    job_dir = os.path.join(TEMP_DIR, f"job_{job_id}")
    os.makedirs(job_dir, exist_ok=True)
    return {"job_id": job_id, "job_otu": auth_token or "active"}

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

    # Fusion des morceaux
    chunks = sorted([os.path.join(job_dir, f) for f in os.listdir(job_dir) if f.startswith("chunk_")])
    with open(in_file, "wb") as outfile:
        for c in chunks:
            with open(c, "rb") as infile:
                shutil.copyfileobj(infile, outfile)

    # Encodage FFmpeg 1080p 60 FPS
    cmd = [
        "ffmpeg", "-y", "-i", in_file,
        "-threads", "2",
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
        "-preset", "superfast",
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
