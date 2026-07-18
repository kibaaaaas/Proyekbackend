import cv2
import numpy as np
import os
import csv
import time
import requests
from datetime import datetime
from collections import defaultdict

try:
    import winsound
    ADA_SUARA = True
except ImportError:
    ADA_SUARA = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(BASE_DIR, "..", "dataset")
MODEL_DIR = os.path.join(BASE_DIR, "trained_model")
INTRUDER_DIR = os.path.join(BASE_DIR, "..", "intruder_logs")
LOG_DIR = os.path.join(BASE_DIR, "logs")
LAPORAN_DIR = os.path.join(BASE_DIR, "laporan")

MODEL_PATH = os.path.join(MODEL_DIR, "trainer.yml")
LABELS_PATH = os.path.join(DATASET_DIR, "labels.txt")
LOG_CSV_PATH = os.path.join(LOG_DIR, "percobaan_asing.csv")

JUMLAH_SAMPEL = 20

# ATURAN SKOR (dibalik, semakin TINGGI semakin COCOK):
# - Skor 75-100  -> dianggap DIKENALI
# - Skor 0-74    -> dianggap TIDAK DIKENALI
THRESHOLD_SCORE = 50

BATAS_PERCOBAAN = 3
FRAME_PER_PERCOBAAN = 15


def pastikan_folder_ada(path):
    if not os.path.exists(path):
        os.makedirs(path)


def get_face_detector():
    face_cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    detector = cv2.CascadeClassifier(face_cascade_path)
    if detector.empty():
        print("[ERROR] Gagal memuat haarcascade. Cek instalasi opencv-python.")
        return None
    return detector


def bunyikan_alarm():
    if ADA_SUARA:
        try:
            winsound.Beep(1200, 300)
        except Exception:
            pass


def catat_log_percobaan(nama_file_foto):
    pastikan_folder_ada(LOG_DIR)
    file_baru = not os.path.exists(LOG_CSV_PATH)

    with open(LOG_CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if file_baru:
            writer.writerow(["timestamp", "file_foto"])
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        writer.writerow([timestamp, nama_file_foto])


def log_ke_csv(id_orang, status_deteksi, waktu_deteksi):
    file_name = 'laporan_kehadiran.csv'
    file_exists = os.path.isfile(file_name)

    with open(file_name, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['ID', 'Status', 'Waktu'])
        writer.writerow([id_orang, status_deteksi, waktu_deteksi])


def capture_faces():
    pastikan_folder_ada(DATASET_DIR)
    face_detector = get_face_detector()
    if face_detector is None:
        return

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[ERROR] Tidak bisa mengakses kamera. Pastikan tidak dipakai aplikasi lain.")
        return

    # Auto-increment ID dari labels.txt
    next_id = 1
    if os.path.exists(LABELS_PATH):
        with open(LABELS_PATH, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    parts = line.split(",")
                    if parts[0].isdigit():
                        next_id = max(next_id, int(parts[0]) + 1)
    user_id = str(next_id)
    print(f"[INFO] ID otomatis: {user_id}")
    user_name = input("Masukkan nama user (contoh: budi): ").strip()

    if not user_id.isdigit():
        print("[ERROR] ID user harus berupa angka.")
        cap.release()
        return

    print("\nPilih role user:")
    print("1. Kominfo")
    print("2. Magang")
    print("3. Satpam")
    print("4. Bukan Kominfo")
    pilihan_role = input("Pilih (1/2/3/4): ").strip()
    if pilihan_role == "1":
        role = "Kominfo"
    elif pilihan_role == "2":
        role = "Magang"
    elif pilihan_role == "3":
        role = "Satpam"
    else:
        role = "Bukan Kominfo"

    with open(LABELS_PATH, "a") as f:
        f.write(f"{user_id},{user_name},{role}\n")

    print("\n[INFO] Mengambil sampel wajah. GERAKKAN sedikit kepala ke kiri/kanan/atas/bawah")
    print("[INFO] biar variasi datanya banyak dan model makin akurat.")
    print("[INFO] Tekan 'q' kapan saja untuk berhenti lebih awal.\n")

    jumlah_diambil = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[ERROR] Gagal membaca frame dari kamera.")
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_detector.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5)

        for (x, y, w, h) in faces:
            jumlah_diambil += 1
            wajah_crop = gray[y:y + h, x:x + w]
            filename = os.path.join(DATASET_DIR, f"user.{user_id}.{jumlah_diambil}.jpg")
            cv2.imwrite(filename, wajah_crop)

            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(frame, f"Sampel: {jumlah_diambil}/{JUMLAH_SAMPEL}",
                        (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        cv2.imshow("Ambil Sampel Wajah - Tekan 'q' untuk berhenti", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
        if jumlah_diambil >= JUMLAH_SAMPEL:
            break

    print(f"\n[SELESAI] {jumlah_diambil} sampel wajah disimpan untuk '{user_name}' (ID: {user_id}).")
    cap.release()
    cv2.destroyAllWindows()


def train_model():
    if not os.path.exists(DATASET_DIR):
        print("[ERROR] Folder dataset/ belum ada. Pilih menu 1 dulu untuk ambil sampel wajah.")
        return

    pastikan_folder_ada(MODEL_DIR)
    face_detector = get_face_detector()
    if face_detector is None:
        return

    image_paths = [
        os.path.join(DATASET_DIR, f)
        for f in os.listdir(DATASET_DIR)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ]

    face_samples = []
    ids = []

    for image_path in image_paths:
        filename = os.path.basename(image_path)
        try:
            user_id = int(filename.split(".")[1])
        except (IndexError, ValueError):
            continue

        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue

        faces = face_detector.detectMultiScale(img)
        if len(faces) > 0:
            (x, y, w, h) = faces[0]
            face_samples.append(img[y:y + h, x:x + w])
        else:
            face_samples.append(img)
        ids.append(user_id)

    if len(face_samples) == 0:
        print("[ERROR] Tidak ada data wajah ditemukan. Pilih menu 1 dulu.")
        return

    print(f"[INFO] Melatih model dari {len(face_samples)} sampel wajah, {len(set(ids))} orang...")

    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.train(face_samples, np.array(ids))
    recognizer.write(MODEL_PATH)

    print(f"[SELESAI] Model berhasil dilatih dan disimpan di '{MODEL_PATH}'")


def load_labels():
    labels = {}
    if os.path.exists(LABELS_PATH):
        with open(LABELS_PATH, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(",")
                user_id = int(parts[0])
                name = parts[1]
                role = parts[2] if len(parts) > 2 else "Kominfo"
                labels[user_id] = {"name": name, "role": role}
    return labels


def run_access_control():
    if not os.path.exists(MODEL_PATH):
        print("[ERROR] Model belum ada. Pilih menu 2 dulu untuk melatih model.")
        return

    labels = load_labels()
    if not labels:
        print("[ERROR] Data user kosong. Pilih menu 1 dulu untuk daftar wajah.")
        return

    pastikan_folder_ada(INTRUDER_DIR)

    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.read(MODEL_PATH)

    face_detector = get_face_detector()
    if face_detector is None:
        return

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[ERROR] Tidak bisa mengakses kamera.")
        return

    print("[INFO] Sistem akses berjalan. Tekan 'q' untuk keluar.")
    print(f"[INFO] Threshold skor saat ini: {THRESHOLD_SCORE} (skor >= ini = dikenali)\n")

    unknown_streak_frames = 0
    percobaan_counter = 0
    sudah_disimpan = False
    peringatan_tampil_sampai = 0
    last_csv_log_time = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[ERROR] Gagal membaca frame dari kamera.")
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_detector.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5)

        ada_wajah_asing_di_frame_ini = False

        for (x, y, w, h) in faces:
            wajah_crop = gray[y:y + h, x:x + w]
            user_id, raw_confidence = recognizer.predict(wajah_crop)

            skor = 100 - raw_confidence
            skor = max(0, min(100, skor))

            print(f"DEBUG -> user_id={user_id}, raw_confidence={raw_confidence:.1f}, skor={skor:.1f}, threshold={THRESHOLD_SCORE}")

            snapshot_file = ""

            if skor >= THRESHOLD_SCORE and user_id in labels:
                user_info = labels[user_id]
                nama = user_info["name"]
                role = user_info["role"]
                label_status = f"{role} - {nama}"
                status = "AKSES DITERIMA"
                warna = (0, 200, 0)

                unknown_streak_frames = 0
                percobaan_counter = 0
                sudah_disimpan = False

                if time.time() - last_csv_log_time >= 1:
                    nama_snapshot = f"dataset/user.{user_id}.{int(time.time())}.jpg"
                    cv2.imwrite(os.path.join(DATASET_DIR, f"user.{user_id}.{int(time.time())}.jpg"), frame)
                    snapshot_file = nama_snapshot
            else:
                nama = "Tidak dikenali"
                role = ""
                label_status = "Tidak dikenali"
                status = "AKSES DITOLAK"
                warna = (0, 0, 255)
                ada_wajah_asing_di_frame_ini = True

                unknown_streak_frames += 1
                if unknown_streak_frames % FRAME_PER_PERCOBAAN == 0:
                    percobaan_counter += 1
                    print(f"[PERINGATAN] Percobaan akses tidak dikenal ke-{percobaan_counter}")

                if percobaan_counter >= BATAS_PERCOBAAN and not sudah_disimpan:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    nama_file = os.path.join(INTRUDER_DIR, f"intruder_{timestamp}.jpg")
                    cv2.imwrite(nama_file, frame)
                    catat_log_percobaan(nama_file)

                    print("=" * 55)
                    print("[PERINGATAN KERAS] TERDETEKSI PERCOBAAN AKSES PAKSA!")
                    print(f"[PERINGATAN KERAS] Wajah disimpan di: {nama_file}")
                    print("=" * 55)

                    bunyikan_alarm()
                    sudah_disimpan = True
                    peringatan_tampil_sampai = time.time() + 4

            waktu_sekarang = time.time()
            if waktu_sekarang - last_csv_log_time >= 1:
                log_ke_csv(user_id, status, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                try:
                    payload = {"status": label_status}
                    if snapshot_file:
                        payload["snapshot_path"] = snapshot_file
                    requests.post("http://127.0.0.1:8000/detect", json=payload, headers={"X-API-Key": "Kominfo123"}, timeout=1)
                except:
                    pass
                last_csv_log_time = waktu_sekarang

            teks_info = f"{nama} | skor:{skor:.0f}"

            cv2.rectangle(frame, (x, y), (x + w, y + h), warna, 2)
            cv2.putText(frame, teks_info, (x, y - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, warna, 2)
            cv2.putText(frame, status, (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.7, warna, 2)

        if not ada_wajah_asing_di_frame_ini:
            unknown_streak_frames = 0

        if time.time() < peringatan_tampil_sampai:
            cv2.rectangle(frame, (0, 0), (frame.shape[1], 40), (0, 0, 255), -1)
            cv2.putText(frame, "PERINGATAN: PERCOBAAN AKSES PAKSA TERDETEKSI!",
                        (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

        cv2.imshow("Sistem Akses Face Recognition - Tekan 'q' keluar", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


def tampilkan_laporan_bulanan():
    if not os.path.exists(LOG_CSV_PATH):
        print("[INFO] Belum ada data percobaan akses paksa yang tercatat.")
        return

    data_per_bulan = defaultdict(list)

    with open(LOG_CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            timestamp_str = row["timestamp"]
            file_foto = row["file_foto"]
            dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            kunci_bulan = dt.strftime("%Y-%m")
            data_per_bulan[kunci_bulan].append((timestamp_str, file_foto))

    if not data_per_bulan:
        print("[INFO] Belum ada data percobaan akses paksa yang tercatat.")
        return

    nama_bulan_indo = {
        "01": "Januari", "02": "Februari", "03": "Maret", "04": "April",
        "05": "Mei", "06": "Juni", "07": "Juli", "08": "Agustus",
        "09": "September", "10": "Oktober", "11": "November", "12": "Desember",
    }

    pastikan_folder_ada(LAPORAN_DIR)
    baris_laporan = []
    baris_laporan.append("=" * 55)
    baris_laporan.append("LAPORAN BULANAN - PERCOBAAN AKSES TIDAK DIKENALI")
    baris_laporan.append("=" * 55)
    baris_laporan.append(f"Dicetak pada: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    baris_laporan.append("")

    print("\n" + "\n".join(baris_laporan))

    for kunci_bulan in sorted(data_per_bulan.keys()):
        tahun, bulan = kunci_bulan.split("-")
        nama_bulan = nama_bulan_indo.get(bulan, bulan)
        kejadian = sorted(data_per_bulan[kunci_bulan], key=lambda x: x[0])

        header = f"Bulan: {nama_bulan} {tahun}  |  Total percobaan: {len(kejadian)}"
        garis = "-" * len(header)

        print(header)
        print(garis)
        baris_laporan.append(header)
        baris_laporan.append(garis)

        for i, (waktu, file_foto) in enumerate(kejadian, start=1):
            baris = f"  {i}. {waktu}  ->  {file_foto}"
            print(baris)
            baris_laporan.append(baris)

        print()
        baris_laporan.append("")

    total_keseluruhan = sum(len(v) for v in data_per_bulan.values())
    ringkasan = f"TOTAL KESELURUHAN PERCOBAAN: {total_keseluruhan}"
    print(ringkasan)
    baris_laporan.append(ringkasan)

    nama_file_laporan = os.path.join(
        LAPORAN_DIR, f"laporan_bulanan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    )
    with open(nama_file_laporan, "w", encoding="utf-8") as f:
        f.write("\n".join(baris_laporan))

    print(f"\n[INFO] Laporan juga disimpan sebagai file: {nama_file_laporan}")


def main():
    while True:
        print("\n============================================")
        print(" PROJEK FACE RECOGNITION - AKSES KONTROL")
        print("============================================")
        print("1. Daftarkan wajah baru (ambil sampel dari kamera)")
        print("2. Latih model (setelah daftar wajah)")
        print("3. Jalankan simulasi akses (kamera real-time)")
        print("4. Lihat laporan bulanan (percobaan akses tidak dikenali)")
        print("0. Keluar")
        pilihan = input("Pilih menu (0/1/2/3/4): ").strip()

        if pilihan == "1":
            capture_faces()
        elif pilihan == "2":
            train_model()
        elif pilihan == "3":
            run_access_control()
        elif pilihan == "4":
            tampilkan_laporan_bulanan()
        elif pilihan == "0":
            print("Sampai jumpa!")
            break
        else:
            print("[INFO] Pilihan tidak valid, coba lagi.")


if __name__ == "__main__":
    main()