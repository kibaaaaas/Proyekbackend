import cv2
import requests
import os
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(BASE_DIR, "..", "dataset")
os.makedirs(DATASET_DIR, exist_ok=True)

# Setup Kamera dan Detektor
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
cap = cv2.VideoCapture(0)

print("CCTV Aktif. Tekan 'q' untuk keluar.")

# Variabel untuk mengatur jeda simpan foto (dalam detik)
last_saved_time = time.time()
save_interval = 3  # Foto akan disimpan setiap 3 detik agar tidak spam

while True:
    ret, frame = cap.read()
    if not ret: break
    
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.3, 5)

    for (x, y, w, h) in faces:
        # Gambar kotak hijau
        cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
        
        # Logika simpan foto (dengan jeda 3 detik)
        if time.time() - last_saved_time > save_interval:
            face_only = frame[y:y+h, x:x+w]
            timestamp = int(time.time())
            img_name = os.path.join(DATASET_DIR, f"user.1.{timestamp}.jpg")
            cv2.imwrite(img_name, face_only)
            print(f"Foto tersimpan: {img_name}")
            last_saved_time = time.time()
            try:
                requests.post("http://127.0.0.1:8000/detect", json={"status": "Wajah Terdeteksi", "snapshot_path": f"dataset/user.1.{timestamp}.jpg"}, headers={"X-API-Key": "Kominfo123"})
            except:
                pass

    cv2.imshow('CCTV', frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()