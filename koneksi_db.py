import os
import cv2
import mysql.connector
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# 1. Koneksi ke Database
db = mysql.connector.connect(
    host=os.getenv("DB_HOST", "localhost"),
    user=os.getenv("DB_USER", "root"),
    password=os.getenv("DB_PASSWORD", ""),
    database=os.getenv("DB_NAME", "security_system")
)
cursor = db.cursor()

# 2. Setup Kamera & Deteksi
cap = cv2.VideoCapture(0)
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

print("Sistem Aktif! Merekam log ke database...")

while True:
    ret, frame = cap.read()
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.3, 5)
    
    for (x, y, w, h) in faces:
        cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
        
        # 3. Log ke Database (Simulasi: Catat tiap ada wajah terdeteksi)
        sql = "INSERT INTO access_logs (status) VALUES (%s)"
        val = ("Wajah Terdeteksi",)
        cursor.execute(sql, val)
        db.commit()
        print("Akses dicatat ke database!")

    cv2.imshow('smart_security_system - Live', frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
db.close()