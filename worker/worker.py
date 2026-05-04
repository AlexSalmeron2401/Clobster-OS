import os
import json
import redis
import time
import subprocess
import socket
import platform
import sys
import psutil
import requests 

# ==============================================================================
# 1. CONFIGURACIÓN
# ==============================================================================
MASTER_IP = "IP NODO MASTER"
REDIS_PORT = "PUERTO POR DEFECTO"
TIMEOUT_RECONEXION = 120
WORKER_NAME = socket.gethostname()

SO_ACTUAL = platform.system()
BASE_PATH = "Z:/" if SO_ACTUAL == "Windows" else "/mnt/dataset/"
DIR_ACTUAL = os.path.dirname(os.path.abspath(__file__))

def conectar_con_espera(ip, port, limite_segundos=TIMEOUT_RECONEXION):
    inicio_espera = time.time()
    while True:
        try:
            r_client = redis.Redis(host=ip, port=port, db=0, decode_responses=True, socket_connect_timeout=5)
            r_client.ping()
            print(f"✅ [{WORKER_NAME}] Conexión exitosa al Master.")
            return r_client
        except (redis.ConnectionError, redis.TimeoutError):
            transcurrido = time.time() - inicio_espera
            if transcurrido >= limite_segundos:
                print(f"\n👋 Master offline. Cerrando {WORKER_NAME}.")
                sys.exit(0)
            print(f"⏳ Buscando Master... ({int(limite_segundos - transcurrido)}s restantes)", end="\r")
            time.sleep(2)

# ==============================================================================
# 2. BUCLE PRINCIPAL
# ==============================================================================

r = conectar_con_espera(MASTER_IP, REDIS_PORT)

current_process = None
active_task_data = None
start_time = 0

print(f"🚀 {WORKER_NAME} operando en modo Multimedia (Video/Audio)...")

while True:
    try:
        # --- A. TELEMETRÍA Y RASTRO ---
        status_label = "Processing" if current_process else "Idle"
        telemetria = {
            "cpu": psutil.cpu_percent(),
            "ram": psutil.virtual_memory().percent,
            "status": status_label,
            "last_job": active_task_data['filename'] if active_task_data else "None",
            "time": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        r.setex(f"worker_heartbeat:{WORKER_NAME}", 10, json.dumps(telemetria))
        r.lpush(f"worker_history:{WORKER_NAME}", json.dumps(telemetria))
        r.ltrim(f"worker_history:{WORKER_NAME}", 0, 29)

        # --- B. MONITOREO DE TAREA ---
        if current_process:
            poll = current_process.poll()
            if poll is not None:
                success = (poll == 0)
                duracion = round(time.time() - start_time, 2)
                status_final = "Completed" if success else "Failed"
                
                r.hset(f"job_status:{active_task_data['id']}", mapping={
                    "status": status_final,
                    "worker": WORKER_NAME,
                    "duration_sec": duracion
                })
                
                try:
                    log_entry = {
                        "job_id": active_task_data['id'],
                        "filename": active_task_data['filename'],
                        "worker": WORKER_NAME,
                        "duration_sec": duracion,
                        "status": status_final,
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "cpu_at_end": psutil.cpu_percent(),
                        "action": active_task_data.get('action', task['action'])
                    }

                    # Carpeta de logs en el almacenamiento compartido
                    log_dir = os.path.join(BASE_PATH, "logs")
                    if not os.path.exists(log_dir):
                        os.makedirs(log_dir, exist_ok=True)

                    log_path = os.path.join(log_dir, f"log_{active_task_data['id']}.json")
                    with open(log_path, 'w') as f:
                        json.dump(log_entry, f, indent=4)
                    
                    print(f"📄 Log de auditoría guardado en: {log_path}")

                    requests.post(f"http://{MASTER_IP}:8000/callback/complete", json={
                        "job_id": active_task_data['id'],
                        "worker": WORKER_NAME,
                        "status": status_final
                    }, timeout=5)
                except Exception as log_error:
                    print(f"⚠️ Error al escribir el log físico: {log_error}")

                print(f"✅ Tarea {active_task_data['id']} finalizada.")
                current_process = None
                active_task_data = None

        # --- C. CAPTURA DE TRABAJO INTELIGENTE (Balanceo de Carga) ---
        if not current_process:
            # REQUISITO PROFESIONAL: Check de disponibilidad real de recursos
            cpu_disponible = psutil.cpu_percent(interval=0.1)
            job_pack = r.brpop("clobster_jobs", timeout=1)

            if cpu_disponible < 85: # Umbral de seguridad para no saturar el nodo
                # BRPOP acepta una LISTA de colas. Redis entregará el primer item 
                # de la primera lista que tenga algo. Esto es PRIORIZACIÓN REAL.
                job_pack = r.brpop([
                    "clobster_jobs_high", 
                    "clobster_jobs_medium", 
                    "clobster_jobs_low"
                ], timeout=2)
            
            if job_pack:
                cola_origen, message = job_pack
                task = json.loads(message)
                action = task['action']
                
                # Inteligencia de Selección de Motor y Categoría
                if action.startswith("audio_"):
                    engine_script = "songs_engine.py"
                    category_out = "songs"
                    extensiones = {
                        "audio_flac": ".flac", "audio_aac": ".aac", "audio_m4a": ".m4a",
                        "audio_ogg": ".ogg", "audio_opus": ".opus", "audio_aiff": ".aiff",
                        "audio_hires_sim": ".flac", "audio_amr": ".amr"
                    }
                    ext = extensiones.get(action, ".mp3")
                
                elif action.startswith("img_"):
                    engine_script = "image_engine.py"
                    category_out = "images"
                    # Mapeo de extensiones (Convertimos todo a JPG por simplicidad, o WebP)
                    ext = ".jpg"

                elif action.startswith("video_"):
                    engine_script = "video_engine.py"
                    category_out = "videos"
                    ext = ".mp4"

                input_file = task['file'].replace("/opt/proyecto-so/dataset/", BASE_PATH)
                out_dir = os.path.join(BASE_PATH, "out", category_out, task.get('batch_id', 'legacy'))
                os.makedirs(out_dir, exist_ok=True)
                
                output_file = os.path.join(out_dir, f"out_{os.path.splitext(os.path.basename(input_file))[0]}{ext}")
                ruta_motor_abs = os.path.join(DIR_ACTUAL, engine_script)

                print(f"🎬 {WORKER_NAME} -> Ejecutando {action}")

                current_process = subprocess.Popen([
                    sys.executable, ruta_motor_abs, 
                    input_file, output_file, action
                ])
                
                active_task_data = {"id": task['id'], "filename": os.path.basename(input_file)}
                start_time = time.time()
                r.hset(f"job_status:{task['id']}", "status", f"Processing on {WORKER_NAME}")
            
            else:
                # El nodo está muy ocupado, esperamos para no "ahogarlo"
                if time.time() % 10 == 0: # Log cada 10 seg para no saturar consola
                    print(f"⚠️ Nodo saturado ({cpu_disponible}% CPU). Esperando liberación de recursos...")

        time.sleep(1)

    except Exception as e:
        print(f"❌ Error: {e}")
        time.sleep(5)