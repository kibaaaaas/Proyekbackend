# API Documentation - Sistem Deteksi Wajah Backend

**Version:** 1.0.0  
**Base URL:** `http://127.0.0.1:8000`  
**Auth:** `X-API-Key: Kominfo123` (wajib di semua endpoint)

---

## Endpoints

### 1. Dashboard HTML
| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| GET | `/` | Tampilkan log hari ini dalam bentuk tabel HTML |

### 2. GET /logs
Ambil 10 log terbaru.
**Response:**
```json
{
  "status": "success",
  "jumlah_data": 10,
  "data": [
    {"id": 1, "status": "Wajah Terdeteksi", "waktu": "2025-07-10 10:30:00"}
  ]
}
```

### 3. POST /detect
Catat deteksi wajah ke database (1x per hari).
**Request:**
```json
{ "status": "Wajah Terdeteksi" }
```
**Response:** `{"status": "success"}`

### 4. POST /train
Latih ulang model face recognition dari dataset.
**Response:** `{"status": "success", "message": "Model berhasil dilatih dengan 1 user!"}`

### 5. GET /export/excel
Download log akses dalam format `.xlsx`.

### 6. GET /reports/today
Total deteksi hari ini.
**Response:**
```json
{"status": "success", "total_deteksi_hari_ini": 5}
```

### 7. GET /clean-logs
Hapus log yang lebih dari 30 hari.
**Response:**
```json
{"status": "success", "dihapus": 3}
```

---

## Cara Pake Header Authorization

**Chrome:** Install ekstensi ModHeader, tambahin `X-API-Key: Kominfo123`  
**Terminal:**
```
curl.exe -H "X-API-Key: Kominfo123" http://127.0.0.1:8000/logs
```
