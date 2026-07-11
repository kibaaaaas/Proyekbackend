import os
import cv2
import mysql.connector
import numpy as np
import datetime
import logging
from fastapi import FastAPI, HTTPException, Request, Security, Depends
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.security.api_key import APIKeyHeader
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

app = FastAPI(
    title="Sistem Deteksi Wajah Backend",
    description="API untuk sistem absensi dan monitoring kehadiran otomatis",
    version="1.0.0",
    dependencies=[Depends(verify_api_key)]
)

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

@app.get("/clean-logs")
async def bersihkan_log():
    return clean_old_logs()

@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM access_logs WHERE DATE(waktu) = CURDATE() ORDER BY waktu DESC")
    logs = cursor.fetchall()
    cursor.close()
    db.close()

    rows = ""
    for log in logs:
        rows += f"<tr><td>{log['id']}</td><td>{log['status']}</td><td>{str(log['waktu'])}</td></tr>"
    
    return f"""
    <html>
    <body>
        <h1>Laporan Kehadiran Hari Ini</h1>
        <table border="1" style="width:100%; border-collapse: collapse;">
            <tr><th>ID</th><th>Status</th><th>Waktu</th></tr>
            {rows}
        </table>
    </body>
    </html>
    """
@app.get("/logs")
async def get_logs():
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT * FROM access_logs ORDER BY id DESC LIMIT 10")
        records = cursor.fetchall()
        cursor.close()
        db.close()

        # Konversi waktu ke string supaya aman di JSON
        for record in records:
            record['waktu'] = str(record['waktu'])

        return {"status": "success", "jumlah_data": len(records), "data": records}
    except Exception as e:
        logging.exception("Error di /logs")
        return {"status": "error", "message": str(e)}

@app.post("/detect")
async def detect_wajah(data: dict):
    db = get_db_connection()
    cursor = db.cursor()
    
    # CEK APAKAH HARI INI SUDAH ADA LOG
    # Kita cek berdasarkan tanggal (CURDATE)
    query_cek = "SELECT id FROM access_logs WHERE DATE(waktu) = CURDATE() LIMIT 1"
    cursor.execute(query_cek)
    sudah_ada = cursor.fetchone()
    
    # Cuma simpan kalau hari ini belum ada log sama sekali
    if not sudah_ada:
        sql = "INSERT INTO access_logs (status, waktu) VALUES (%s, %s)"
        # Menggunakan format waktu sekarang
        val = (data['status'], datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        cursor.execute(sql, val)
        db.commit()
    
    cursor.close()
    db.close()
    return {"status": "success"}

@app.post("/train")
async def train_model():
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
async def export_excel():
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
def get_today_report():
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