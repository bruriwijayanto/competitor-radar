# Competitor Radar

Sistem intelijen kompetitor bisnis lokal berbasis **multi-agent AI**. Proyek demo akademik untuk UTS mata kuliah *AI Innovation & Entrepreneurship* — fokus pada kejelasan alur kerja agent (pola Agent-to-Agent) dan UI monitoring real-time, bukan skala produksi.

Pengguna memasukkan lokasi & kategori usaha → tiga agent berjalan berurutan (Data Collector → Sentiment & Insight → Strategy) → hasil berupa peta kompetitif, analisis sentimen, gap analysis, dan rekomendasi strategis.

## Cara Menjalankan

Butuh Python **3.10+**. Tidak butuh API key apa pun untuk mode default (mock).

```bash
# 1) Buat virtual environment & install dependency (sekali saja)
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2) Jalankan — SATU perintah ini menjalankan backend sekaligus men-serve frontend
uvicorn backend.main:app --reload
```

Buka **http://127.0.0.1:8000** di browser. Selesai — form input, panel monitoring, dan panel hasil semua ada di satu halaman itu.

Opsional: salin `.env.example` ke `.env` untuk mengatur mode/API key (lihat bagian [Mode Real](#mode-real-opsional) di bawah).

## Arsitektur Singkat

```
Browser (index.html + app.js)
   │  EventSource GET /api/analisis/stream?...
   ▼
FastAPI (backend/main.py)
   │  StreamingResponse (SSE) dari orchestrator.py
   ▼
Orchestrator (Agno) — jalankan berurutan:
   Agent 1: Data Collector  →  Agent 2: Sentiment & Insight  →  Agent 3: Strategy
   (output Agent N divalidasi Pydantic, jadi input Agent N+1 — pola ala A2A)
```

- **Backend**: FastAPI + [Agno](https://github.com/agno-agi/agno) (framework agent). Setiap agent = satu file di `backend/agents/`. Kontrak data antar-agent didefinisikan terpusat di `backend/schemas.py` dengan Pydantic.
- **Realtime**: Server-Sent Events (SSE) satu arah backend → frontend. Tipe event: `start`, `progress`, `handoff` (berisi preview payload JSON yang dioper antar-agent), `done` (per agent), `complete` (laporan akhir), `error`.
- **Frontend**: HTML + CSS + jQuery murni, tanpa build step. Disajikan langsung oleh FastAPI (`StaticFiles`) dari origin yang sama — tidak ada masalah CORS, meski `CORSMiddleware` tetap dipasang sebagai cadangan.
- **Dua mode operasi** (env var `APP_MODE`, default `mock`):
  - `mock` — data kompetitor & ulasan sintetis realistis, sentimen & strategi dari heuristik rule-based. **Berjalan penuh tanpa API key.**
  - `real` — Data Collector memanggil Google Maps Places API; Sentiment & Strategy Agent memanggil LLM lewat **OpenRouter** (via Agno `Agent`). Jika key tidak lengkap/gagal, otomatis fallback ke mock supaya demo tidak pernah gagal total.
- **Peta sebaran kompetitor**: setiap kompetitor (mock maupun real) punya koordinat lat/lng. Jika `GOOGLE_MAPS_API_KEY` diset (independen dari `APP_MODE`), frontend merender **Google Map sungguhan** dengan marker berwarna sesuai rating. Jika tidak, frontend otomatis memakai **Leaflet.js + OpenStreetMap** — peta geografis nyata (jalan, gedung, marker presisi) yang sepenuhnya gratis tanpa API key maupun billing.

Detail lebih lengkap (konvensi kode, struktur folder) ada di `CLAUDE.md`.

## Mode Real (opsional)

Isi `.env` (lihat `.env.example`):

```
APP_MODE=real
GOOGLE_MAPS_API_KEY=isi_key_anda
OPENROUTER_API_KEY=isi_key_anda
OPENROUTER_MODEL=openai/gpt-4o-mini
```

Dapatkan `OPENROUTER_API_KEY` di [openrouter.ai/keys](https://openrouter.ai/keys). Satu key OpenRouter bisa dipakai ganti-ganti model/provider (OpenAI, Anthropic, Google, bahkan model gratis) cukup dengan mengubah `OPENROUTER_MODEL`.

Tidak ada key yang di-hardcode di kode — semua dibaca dari environment variable.

## Struktur Folder

```
backend/
  main.py                # FastAPI app, mount StaticFiles, endpoint SSE
  config.py               # baca environment variable
  schemas.py                # semua model Pydantic (request + kontrak antar-agent)
  orchestrator.py            # jalankan 3 agent berurutan, emit event SSE
  mock_data.py                 # generator data mock realistis
  agents/
    data_collector.py           # Agent 1
    sentiment_insight.py         # Agent 2
    strategy.py                   # Agent 3
frontend/
  index.html                      # struktur UI
  style.css                        # styling flat design
  app.js                            # jQuery + EventSource SSE + Chart.js
CLAUDE.md
requirements.txt
.env.example
```

## Asumsi yang Diambil

Karena ini demo akademik, beberapa keputusan teknis diambil sendiri tanpa konfirmasi lebih lanjut:

1. **Python 3.10** dipakai (bukan 3.9 bawaan sistem) karena kompatibilitas dengan library `agno` versi terbaru. Dipin lewat `.python-version` (pyenv).
2. **Klasifikasi sentimen mode mock** memakai heuristik rating per-ulasan (rating ≥4 → positif, =3 → netral, ≤2 → negatif) dikombinasikan dengan keyword matching Bahasa Indonesia untuk ekstraksi tema — bukan NLP/LLM sungguhan, karena mode mock harus jalan tanpa API key sama sekali.
3. **Data mock deterministik**: nama kompetitor, rating, dan ulasan digenerate dengan seed dari kombinasi lokasi+kategori, supaya input yang sama menghasilkan tampilan yang konsisten saat demo berulang, tapi tetap bervariasi antar lokasi/kategori berbeda.
4. **Jumlah kompetitor** dibatasi ke pilihan **5 atau 10** sesuai spesifikasi UI (segmented control); nilai lain yang dikirim langsung ke API akan dibulatkan ke opsi terdekat.
5. **Radius pencarian** dibatasi 1–5 km sesuai spesifikasi slider.
6. **Mode real** menggunakan Google Places **Nearby Search + Place Details** (butuh Geocoding untuk mengubah nama lokasi jadi koordinat) dan **OpenRouter** sebagai provider LLM via Agno `OpenRouter` model — dipilih karena satu API key bisa mengakses banyak model/provider berbeda (termasuk model gratis), praktis untuk demo. Provider lain bisa ditambahkan dengan mengganti `agno.models.openrouter.OpenRouter` di `sentiment_insight.py`/`strategy.py`.
7. **Fallback otomatis ke mock** diterapkan di setiap agent bila mode `real` diminta tapi API key kosong/tidak valid/panggilan gagal — supaya sesi demo langsung di depan kelas tidak pernah gagal total karena masalah jaringan/quota.
8. **Tanpa database/persistensi** — setiap analisis bersifat stateless, hasil hanya ada di memori selama request SSE berlangsung. Sesuai kebutuhan demo, bukan aplikasi produksi.
9. **Tanpa autentikasi** — aplikasi diasumsikan dijalankan lokal untuk keperluan presentasi/demo, bukan diekspos ke publik.
10. Delay kecil (~0.5 detik) disisipkan antar-event SSE di `orchestrator.py` supaya panel monitoring terasa "hidup" saat presentasi, mengingat proses mock sebenarnya berjalan hampir instan.
11. **Koordinat kompetitor pada mode mock bersifat sintetis** — dihasilkan di sekitar titik pusat kota (dicocokkan dari nama lokasi ke daftar kota besar Indonesia, atau titik acak deterministik di Pulau Jawa jika tidak dikenali), bukan hasil geocoding sungguhan. Cukup realistis untuk keperluan visualisasi demo.
12. **Google Maps JavaScript API key di-reuse dari `GOOGLE_MAPS_API_KEY`** yang sama dipakai untuk Places API, dan diekspos ke frontend lewat endpoint `/api/maps-key`. Ini sesuai praktik umum Google — Maps JS key memang didesain dipakai di sisi client (dibatasi lewat HTTP referrer restriction di Google Cloud Console), berbeda dari key REST/server yang harus dirahasiakan. Fitur peta ini aktif independen dari `APP_MODE`: kalau key tersedia, kompetitor mock pun akan tampil di atas Google Map sungguhan.

## Menguji Cepat via curl

```bash
curl -s http://127.0.0.1:8000/api/health

curl -N "http://127.0.0.1:8000/api/analisis/stream?lokasi=Dago,%20Bandung&kategori=coffee%20shop&radius_km=2&top_n=5"
```
