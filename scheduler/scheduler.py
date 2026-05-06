import os
import json
import logging
import redis
import asyncio
import threading
import psutil
import time
import sqlite3
import uuid
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import List, Optional
from contextlib import closing

# ==========================================
# 1. CONFIGURACIÓN Y TELEMETRÍA MASTER
# ==========================================

def master_telemetry_loop():
    """Hilo para que la Celeron se auto-monitoree cada segundo"""
    while True:
        try:
            stats = {
                "cpu": psutil.cpu_percent(),
                "ram": psutil.virtual_memory().percent,
                "status": "Master Online",
                "last_job": "Orquestando Clúster",
                "time": time.strftime("%H:%M:%S")
            }
            r.lpush("worker_history:MASTER", json.dumps(stats))
            r.ltrim("worker_history:MASTER", 0, 29)
            r.setex("worker_heartbeat:MASTER", 5, json.dumps(stats))
        except Exception as e:
            print(f"⚠️ Error en auto-monitoreo Master: {e}")
        time.sleep(1)

DATASET_PATH = "Ruta de la carpeta dataset"
DB_PATH = "clobster_dataset.db" #Nombre de la base de datos
WEB_PATH = "../web-page/" #Ruta donde están los archivos html

app = FastAPI(title="Clobster OS - Master Node")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#Esto expone la carpeta del dataset bajo la ruta web /media
app.mount("/media", StaticFiles(directory=DATASET_PATH), name="media")

r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

threading.Thread(target=master_telemetry_loop, daemon=True).start()

# ==========================================
# 2. MODELOS Y GESTIÓN DE BASE DE DATOS
# ==========================================

class TaskRequest(BaseModel):
    filename: str
    action: str
    batch_id: Optional[str] = "legacy"
    priority: Optional[str] = "medium"  # Nuevo: high, medium, low
    params: Optional[dict] = None

def init_db():
    """Añadimos la columna 'category' para que los filtros funcionen"""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        with conn:
            # CORRECCIÓN: Aseguramos la existencia de la tabla con la columna category
            conn.execute('''CREATE TABLE IF NOT EXISTS dataset 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                          filename TEXT UNIQUE, 
                          category TEXT, 
                          size_mb REAL, 
                          status TEXT DEFAULT 'ready')''')
            
            conn.execute('''CREATE TABLE IF NOT EXISTS task_history 
                         (job_id TEXT PRIMARY KEY, filename TEXT, action TEXT, 
                          worker TEXT, status TEXT, batch_id TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')

# NUEVO ENDPOINT: Para que el botón "Sincronizar" funcione de verdad
@app.post("/dataset/sync")
async def manual_sync():
    """
    Este es el endpoint que la web llamará. 
    Ejecuta el escaneo físico de carpetas y actualiza SQLite.
    """
    try:
        sync_dataset_to_db() # Llamamos a tu función de escaneo
        return {"status": "success", "message": "Base de datos sincronizada con el disco."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def sync_dataset_to_db():
    """
    Sincronización tipo 'Espejo':
    Borra registros que ya no existen y agrega los nuevos.
    """
    SEARCH_MAP = {
        "videos": ["videos", "VIDEOS", "Videos"],
        "songs": ["songs", "SONGS", "Songs", "music", "MUSIC"],
        "images": ["images", "IMAGES", "Images", "fotos", "FOTOS"]
    }

    print("🔄 Iniciando sincronización de disco con SQLite...")

    with closing(sqlite3.connect(DB_PATH)) as conn:
        with conn:
            for category_key, possible_names in SEARCH_MAP.items():
                target_path = None
                # 1. Localizar la carpeta física
                for name in possible_names:
                    temp_path = os.path.join(DATASET_PATH, "ROW", name)
                    if os.path.exists(temp_path):
                        target_path = temp_path
                        break
                # 2. LIMPIEZA: Si entramos a procesar una categoría,
                # primero vaciamos sus registros viejos en la DB para esta categoría.
                conn.execute("DELETE FROM dataset WHERE category = ?", (category_key,))

                if not target_path:
                    print(f"⚠️ Carpeta de {category_key} vacía o no encontrada. Registros eliminados.")
                    continue

		#ESCANEO: Leemos los archivos físicos
                try:
                    files = [f for f in os.listdir(target_path) if os.path.isfile(os.path.join(target_path, f))]
                except Exception as e:
                    print(f"❌ Error accediendo a {target_path}: {e}")
                    continue

                # 3. ESCANEO Y CARGA: Insertamos lo que hay actualmente en el disco
                files = [f for f in os.listdir(target_path) if os.path.isfile(os.path.join(target_path, f))]
                for f in files:
                    folder_name = os.path.basename(target_path)
                    relative_path = os.path.join(folder_name, f)
                    full_path = os.path.join(target_path, f)
                    try:
                        size = os.path.getsize(full_path) / (1024*1024)
                        conn.execute("""
                            INSERT INTO dataset (filename, category, size_mb, status) 
                            VALUES (?, ?, ?, ?)
                        """, (relative_path, category_key, round(size, 2), 'ready'))
                    except Exception as e:
                        print(f"Error al procesar {f}: {e}")

    print("✅ Sincronización finalizada. El clúster está listo para procesarlos archivos.")

@app.on_event("startup")
async def startup_event():
    init_db()
    sync_dataset_to_db()

@app.post("/callback/complete")
async def complete_task_callback(data: dict):
    job_id = data.get("job_id")
    worker_name = data.get("worker")
    status = data.get("status")

    with closing(sqlite3.connect(DB_PATH)) as conn:
        with conn:
            conn.execute("""
                UPDATE task_history 
                SET status = ?, worker = ?, timestamp = CURRENT_TIMESTAMP 
                WHERE job_id = ?
            """, (status, worker_name, job_id))
    return {"status": "updated"}

# ==========================================
# 3. ENDPOINTS DE NAVEGACIÓN Y PANELES
# ==========================================

@app.get("/")
async def serve_home():
    return FileResponse(os.path.join(WEB_PATH, "index.html"))

@app.get("/dashboard")
async def serve_dashboard():
    return FileResponse(os.path.join(WEB_PATH, "dashboard.html"))

@app.get("/convert/{category}")
async def serve_conversion_page(category: str):
    return FileResponse(os.path.join(WEB_PATH, f"{category}.html"))

@app.get("/dataset/raw/{category}")
async def list_raw_files(category: str):
    """
    IMPORTANTE: Asegúrate de que el frontend llame a ESTA ruta
    con 'videos', 'songs' o 'images' en minúsculas.
    """
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        # Filtramos por la categoría que el sistema guardó (minúsculas)
        cursor.execute("SELECT filename, size_mb FROM dataset WHERE category = ?", (category,))
        rows = cursor.fetchall()
        
    return {"files": [{"name": os.path.basename(r["filename"]), 
                       "path": r["filename"], 
                       "size": f"{r['size_mb']} MB"} for r in rows]}

@app.get("/dataset/out/{category}")
async def list_out_files(category: str):
    """Llena el panel DERECHO escaneando las carpetas de tiempo"""
    target_path = os.path.join(DATASET_PATH, "out", category)
    structure = {}
    if os.path.exists(target_path):
        for batch_dir in os.listdir(target_path):
            batch_path = os.path.join(target_path, batch_dir)
            if os.path.isdir(batch_path):
                structure[batch_dir] = os.listdir(batch_path)
    return {"structure": structure}

@app.get("/system/logs")
async def get_logs():
    log_dir = os.path.join(DATASET_PATH, "logs")
    if not os.path.exists(log_dir):
        return {"logs": []}
    all_logs = []
    # Leemos todos los archivos .json en la carpeta logs
    for file in os.listdir(log_dir):
        if file.endswith(".json"):
            with open(os.path.join(log_dir, file), 'r') as f:
                all_logs.append(json.load(f))
    # Ordenar por fecha (los más nuevos primero)
    all_logs.sort(key=lambda x: x['timestamp'], reverse=True)
    return {"logs": all_logs}

# ==========================================
# 4. PROCESAMIENTO Y STATUS
# ==========================================

@app.post("/enqueue")
async def enqueue_task(request: TaskRequest):
    file_path = os.path.join(DATASET_PATH, "ROW", request.filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"No existe: {file_path}")

    task_id = f"job_{r.incr('job_counter')}"
    task_payload = {
        "id": task_id, "file": file_path, "action": request.action, 
        "batch_id": request.batch_id, "priority": request.priority
    }

    # PLANIFICACIÓN PROFESIONAL: Colas múltiples por prioridad
    # Redis permite que el worker escuche varias listas en orden
    queue_name = f"clobster_jobs_{request.priority}"
    r.lpush(queue_name, json.dumps(task_payload))
    # Registro de estado (Igual que antes)
    r.hset(f"job_status:{task_id}", mapping={
        "status": "queued", "filename": os.path.basename(request.filename),
        "priority": request.priority
    })
    # SQLite para auditoría (Igual que antes)
    with closing(sqlite3.connect(DB_PATH)) as conn:
        with conn:
            conn.execute("INSERT INTO task_history (job_id, filename, action, status, batch_id) VALUES (?,?,?,?,?)",
                         (task_id, os.path.basename(request.filename), request.action, "queued", request.batch_id))
    return {"status": "enqueued", "job_id": task_id, "queue": queue_name}

@app.get("/status")
async def get_status():
    h_keys = r.keys("worker_heartbeat:*")
    workers = {}
    for k in h_keys:
        name = k.split(":")[1]
        data = r.get(k)
        if data:
            current = json.loads(data)
            history_raw = r.lrange(f"worker_history:{name}", 0, 29)
            history = [json.loads(x) for x in history_raw]
            workers[name] = {"current": current, "history": history}

    j_keys = r.keys("job_status:*")
    total = len(j_keys)
    completed = sum(1 for k in j_keys if r.hget(k, "status") == "Completed")
    return {
        "percent": int((completed/total)*100) if total > 0 else 0,
        "completed": completed, "total": total, "workers": workers
    }

@app.websocket("/ws/status")
async def websocket_status(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await get_status()
            await websocket.send_json(data)
            await asyncio.sleep(2)
    except WebSocketDisconnect: pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
