import requests
import json

BASE_URL = "http://127.0.0.1:8000"
API_KEY = "Kominfo123"
HEADERS = {"X-API-Key": API_KEY}

total_test = 0
total_pass = 0

def test( nama, kondisi, actual ):
    global total_test, total_pass
    total_test += 1
    status = "PASS" if kondisi else "FAIL"
    if status == "PASS":
        total_pass += 1
    print(f"  [{status}] {nama}")
    if not kondisi:
        print(f"         >> Expected: {kondisi} | Actual: {actual}")

print("=" * 55)
print("  NEGATIVE TESTING - SISTEM DETEKSI WAJAH")
print("=" * 55)

# 1. Akses tanpa API Key
print("\n[1] AUTHENTICATION")
try:
    r = requests.get(f"{BASE_URL}/logs")
    test("Tanpa API key -> 403", r.status_code == 403, r.status_code)
except Exception as e:
    test("Tanpa API key -> 403", False, str(e))

try:
    r = requests.get(f"{BASE_URL}/logs", headers={"X-API-Key": "salah123"})
    test("API key salah -> 403", r.status_code == 403, r.status_code)
except Exception as e:
    test("API key salah -> 403", False, str(e))

# 2. Endpoint gak ada
print("\n[2] ENDPOINT NOT FOUND")
try:
    r = requests.get(f"{BASE_URL}/endpoint_gak_ada", headers=HEADERS)
    test("Endpoint tidak dikenal -> 404", r.status_code == 404, r.status_code)
except Exception as e:
    test("Endpoint tidak dikenal -> 404", False, str(e))

# 3. POST /detect dengan data kosong
print("\n[3] POST /detect - VALIDASI DATA")
try:
    r = requests.post(f"{BASE_URL}/detect", json={}, headers=HEADERS)
    test("Data kosong -> tidak crash", r.status_code in [200, 422], r.status_code)
except Exception as e:
    test("Data kosong -> tidak crash", False, str(e))

try:
    r = requests.post(f"{BASE_URL}/detect", json={"status": ""}, headers=HEADERS)
    test("Status kosong -> tetap diproses", r.status_code == 200, r.status_code)
except Exception as e:
    test("Status kosong -> tetap diproses", False, str(e))

# 4. GET /export/excel
print("\n[4] EXPORT EXCEL")
try:
    r = requests.get(f"{BASE_URL}/export/excel", headers=HEADERS)
    test("Download Excel -> 200", r.status_code == 200, r.status_code)
    test("Content-Type Excel", "spreadsheetml" in r.headers.get("Content-Type", ""), r.headers.get("Content-Type"))
except Exception as e:
    test("Download Excel -> 200", False, str(e))

# 5. GET /reports/today
print("\n[5] REPORTS")
try:
    r = requests.get(f"{BASE_URL}/reports/today", headers=HEADERS)
    if r.status_code == 200:
        data = r.json()
        test("Report today -> sukses", data.get("status") == "success", data)
    else:
        test("Report today -> sukses", False, f"status_code: {r.status_code}")
except Exception as e:
    test("Report today -> sukses", False, str(e))

# 6. GET /clean-logs
print("\n[6] CLEAN LOGS")
try:
    r = requests.get(f"{BASE_URL}/clean-logs", headers=HEADERS)
    if r.status_code == 200:
        data = r.json()
        test("Clean logs -> sukses", data.get("status") == "success", data)
    else:
        test("Clean logs -> sukses", False, f"status_code: {r.status_code}")
except Exception as e:
    test("Clean logs -> sukses", False, str(e))

print("\n" + "=" * 55)
print(f"  HASIL: {total_pass}/{total_test}  PASS")
print("=" * 55)

if total_pass == total_test:
    print("\n  Semua negative test aman bro!")
else:
    print(f"\n  Ada {total_test - total_pass} test gagal, cek lagi bro.")
