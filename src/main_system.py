import os
import cv2
import mysql.connector
import numpy as np
import datetime
import logging
from fastapi import FastAPI, HTTPException, Request, Security, Depends
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi.security.api_key import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from openpyxl import Workbook
from io import BytesIO
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

logging.basicConfig(
    filename='system_error.log',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

HARI_RETENSI_LOG = 30

API_KEY = os.getenv("API_KEY", "Kominfo123")
API_KEY_NAME = "X-API-Key"

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Forbidden: API Key tidak valid")

DATASET_DIR = os.path.join(os.path.dirname(__file__), "..", "dataset")
INTRUDER_DIR = os.path.join(os.path.dirname(__file__), "..", "intruder_logs")
os.makedirs(DATASET_DIR, exist_ok=True)
os.makedirs(INTRUDER_DIR, exist_ok=True)

app = FastAPI(
    title="Sistem Deteksi Wajah Backend",
    description="API untuk sistem absensi dan monitoring kehadiran otomatis",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def ngrok_skip_warning(request: Request, call_next):
    response = await call_next(request)
    response.headers["ngrok-skip-browser-warning"] = "true"
    return response

app.mount("/dataset", StaticFiles(directory=DATASET_DIR), name="dataset")
app.mount("/intruder", StaticFiles(directory=INTRUDER_DIR), name="intruder")

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "smart_security_db")
    )

def clean_old_logs():
    try:
        batas_waktu = datetime.datetime.now() - datetime.timedelta(days=HARI_RETENSI_LOG)
        db = get_db_connection()
        cursor = db.cursor()
        query = "DELETE FROM access_logs WHERE waktu < %s"
        cursor.execute(query, (batas_waktu,))
        db.commit()
        hapus = cursor.rowcount
        cursor.close()
        db.close()
        logging.info(f"Bersihkan log: {hapus} data lama (> {HARI_RETENSI_LOG} hari) dihapus")
        return {"status": "success", "dihapus": hapus}
    except Exception as e:
        logging.exception("Gagal bersihkan database")
        raise HTTPException(status_code=500, detail="Gagal bersihkan log")

@app.delete("/logs")
async def delete_all_logs(_: str = Depends(verify_api_key)):
    try:
        db = get_db_connection()
        cursor = db.cursor()
        cursor.execute("DELETE FROM access_logs")
        db.commit()
        hapus = cursor.rowcount
        cursor.close()
        db.close()
        return {"status": "success", "message": f"{hapus} log dihapus"}
    except Exception as e:
        logging.exception("Error delete all logs")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/logs/{log_id}")
async def delete_log(log_id: int, _: str = Depends(verify_api_key)):
    try:
        db = get_db_connection()
        cursor = db.cursor()
        cursor.execute("DELETE FROM access_logs WHERE id = %s", (log_id,))
        db.commit()
        hapus = cursor.rowcount
        cursor.close()
        db.close()
        if hapus == 0:
            raise HTTPException(status_code=404, detail="Log tidak ditemukan")
        return {"status": "success", "message": f"Log ID {log_id} dihapus"}
    except HTTPException:
        raise
    except Exception as e:
        logging.exception("Error delete log")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/users")
async def get_users(_: str = Depends(verify_api_key)):
    labels_path = os.path.join(os.path.dirname(__file__), "..", "dataset", "labels.txt")
    users = []
    if os.path.exists(labels_path):
        with open(labels_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(",")
                users.append({
                    "id": int(parts[0]),
                    "name": parts[1],
                    "role": parts[2] if len(parts) > 2 else "Kominfo"
                })
    return {"status": "success", "data": users}

@app.get("/clean-logs")
async def bersihkan_log(_: str = Depends(verify_api_key)):
    return clean_old_logs()

@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    html_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()
@app.get("/logs")
async def get_logs(limit: int = 10, start_date: str = "", end_date: str = "", search: str = "", _: str = Depends(verify_api_key)):
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        query = "SELECT * FROM access_logs WHERE 1=1"
        params = []
        if start_date:
            query += " AND DATE(waktu) >= %s"
            params.append(start_date)
        if end_date:
            query += " AND DATE(waktu) <= %s"
            params.append(end_date)
        if search:
            query += " AND status LIKE %s"
            params.append(f"%{search}%")
        query += " ORDER BY id DESC"
        if limit > 0:
            query += " LIMIT %s"
            params.append(limit)
        cursor.execute(query, tuple(params))
        records = cursor.fetchall()
        cursor.close()
        db.close()

        for record in records:
            record['waktu'] = str(record['waktu'])

        return {"status": "success", "jumlah_data": len(records), "data": records}
    except Exception as e:
        logging.exception("Error di /logs")
        return {"status": "error", "message": str(e)}

@app.post("/detect")
async def detect_wajah(data: dict, _: str = Depends(verify_api_key)):
    status = data.get("status", "").strip()
    if not status:
        raise HTTPException(status_code=400, detail="Field 'status' wajib diisi")
    db = get_db_connection()
    cursor = db.cursor()
    
    snapshot_path = data.get("snapshot_path", "")
    sql = "INSERT INTO access_logs (status, snapshot_path, waktu) VALUES (%s, %s, %s)"
    val = (status, snapshot_path, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    cursor.execute(sql, val)
    db.commit()
    
    cursor.close()
    db.close()
    return {"status": "success"}

@app.post("/train")
async def train_model(_: str = Depends(verify_api_key)):
    dataset_path = "dataset" # Sesuaikan dengan lokasi folder lu
    model_dir = "trained_model"
    
    if not os.path.exists(dataset_path):
        raise HTTPException(status_code=404, detail="Folder dataset tidak ditemukan!")

    face_samples = []
    ids = []
    
    # Ambil semua file di folder, abaikan yang bukan file gambar (kayak labels.txt)
    image_paths = [os.path.join(dataset_path, f) for f in os.listdir(dataset_path) if f.startswith("user.")]
    
    detector = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

    for image_path in image_paths:
        try:
            # Mengambil ID dari nama file (contoh: user.1.0)
            parts = os.path.split(image_path)[-1].split(".")
            user_id = int(parts[1])
            
            img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
            if img is None: continue # Skip kalau gagal baca
            
            faces = detector.detectMultiScale(img)
            for (x, y, w, h) in faces:
                face_samples.append(img[y:y + h, x:x + w])
                ids.append(user_id)
        except Exception as e:
            print(f"Gagal proses {image_path}: {e}")
            continue

    if not face_samples:
        return {"status": "error", "message": "Tidak ada data wajah untuk dilatih"}

    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.train(face_samples, np.array(ids))
    recognizer.write(os.path.join(model_dir, "trainer.yml"))

    return {"status": "success", "message": f"Model berhasil dilatih dengan {len(set(ids))} user!"}

@app.get("/export/excel")
async def export_excel(_: str = Depends(verify_api_key)):
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT * FROM access_logs ORDER BY waktu DESC")
        logs = cursor.fetchall()
        cursor.close()
        db.close()

        wb = Workbook()
        ws = wb.active
        ws.title = "Access Logs"
        ws.append(["ID", "Status", "Waktu"])

        for log in logs:
            ws.append([log["id"], log["status"], str(log["waktu"])])

        output = BytesIO()
        wb.save(output)
        output.seek(0)

        filename = f"access_logs_{datetime.date.today()}.xlsx"
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        logging.exception("Error di /export/excel")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/reports/today")
def get_today_report(_: str = Depends(verify_api_key)):
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        
        # Query buat ngitung deteksi khusus hari ini
        query = "SELECT COUNT(*) as total_hari_ini FROM access_logs WHERE DATE(waktu) = CURDATE()"
        cursor.execute(query)
        result = cursor.fetchone()
        
        cursor.close()
        db.close()
        
        return {
            "status": "success",
            "total_deteksi_hari_ini": result['total_hari_ini']
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}