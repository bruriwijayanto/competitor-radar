# CLAUDE.md — Competitor Radar

Dokumen ini memberi konteks arsitektur & konvensi proyek untuk siapa pun (manusia atau AI) yang bekerja di repo ini selanjutnya.

## Tujuan Proyek

**Competitor Radar** adalah aplikasi demo akademik (UTS mata kuliah *AI Innovation & Entrepreneurship*) yang mensimulasikan sistem intelijen kompetitor bisnis lokal berbasis **multi-agent AI**. Fokus utama: memperlihatkan **alur kerja agent yang jelas dan bisa dijelaskan** (siapa mengerjakan apa, data apa yang dioper ke siapa) serta **UI monitoring yang hidup/menarik**, bukan skala produksi atau akurasi data riil.

## Arsitektur Ringkas

```
[Browser: index.html + app.js]
        │  1. POST form analisis (buka koneksi SSE via EventSource GET /api/analisis/stream)
        ▼
[FastAPI backend (main.py)]
        │  2. Orchestrator (Agno) menjalankan pipeline berurutan
        ▼
┌───────────────────────────────────────────────────────────────┐
│  Agent 1: Data Collector  →  Agent 2: Sentiment & Insight  →  │
│  Agent 3: Strategy                                             │
└───────────────────────────────────────────────────────────────┘
        │  3. Tiap transisi antar-agent memicu event SSE `handoff`
        │     berisi preview payload JSON (pola ala Agent-to-Agent/A2A)
        ▼
[Browser: panel monitoring live + panel hasil akhir]
```

- **Backend**: Python + FastAPI + [Agno](https://github.com/agno-agi/agno) sebagai framework agent/orchestrator.
- **Frontend**: HTML + CSS + jQuery murni (tanpa build step, tanpa framework JS). Disajikan langsung oleh FastAPI via `StaticFiles` agar satu origin.
- **Transport real-time**: Server-Sent Events (SSE) satu arah backend → frontend, dikonsumsi via `EventSource` di `app.js`.
- **Skema data antar-agent**: didefinisikan terpusat di `backend/schemas.py` dengan Pydantic. Setiap agent punya *input model* dan *output model* yang eksplisit — ini yang membuat pola "A2A" (Agent-to-Agent handoff) terlihat jelas: output Agent N adalah input Agent N+1, divalidasi oleh Pydantic di setiap batas.

## Mode Operasi

Aplikasi punya dua mode, dipilih lewat env var `APP_MODE` (default: `mock`):

- **`mock` (default, tanpa API key apa pun)**: Data Collector mengembalikan data kompetitor & ulasan sintetis tapi realistis (deterministik per request berdasarkan input lokasi/kategori). Sentiment & Strategy agent memakai logika rule-based/heuristik (keyword matching Bahasa Indonesia) — bukan LLM — sehingga seluruh pipeline berjalan tanpa key apa pun.
- **`real`**: Data Collector memanggil Google Maps Places API (butuh `GOOGLE_MAPS_API_KEY`). Sentiment & Strategy agent memakai Agno `Agent` yang dibungkus LLM lewat **OpenRouter** (`agno.models.openrouter.OpenRouter`, butuh `OPENROUTER_API_KEY`) dengan `output_schema` Pydantic supaya hasilnya terstruktur. Jika mode `real` diminta tapi key tidak lengkap, backend otomatis fallback ke heuristik mock untuk bagian yang key-nya tidak tersedia (agar demo tidak pernah gagal total) dan mencatat warning di log SSE.

Tidak ada API key yang di-hardcode di mana pun. Semua dibaca dari environment variable (lihat `.env.example`).

## Struktur Folder

```
backend/
  main.py              # FastAPI app, mount StaticFiles frontend, endpoint SSE
  config.py             # baca env var (APP_MODE, API keys, dsb)
  schemas.py             # SEMUA model Pydantic (request + payload antar-agent)
  orchestrator.py        # Agno: jalankan 3 agent berurutan, emit event SSE
  mock_data.py            # generator data mock realistis (kompetitor + ulasan)
  agents/
    __init__.py
    data_collector.py     # Agent 1: kumpulkan kompetitor + ulasan mentah
    sentiment_insight.py  # Agent 2: klasifikasi sentimen + ekstraksi tema
    strategy.py            # Agent 3: gap analysis + rekomendasi strategis
frontend/
  index.html              # struktur UI (form, panel monitoring, panel hasil)
  style.css                # styling flat design modern
  app.js                    # logic jQuery + EventSource SSE + Chart.js
CLAUDE.md
README.md
.env.example
requirements.txt
```

## Konvensi

- **Satu agent = satu file = satu tanggung jawab.** Jangan gabungkan logika agent lain ke dalam satu file.
- **Semua payload antar-agent divalidasi Pydantic** di `schemas.py` — jangan lempar dict mentah antar-agent tanpa model.
- **Titik handoff antar-agent HARUS diberi komentar eksplisit** menandai "A2A boundary" — baik di `orchestrator.py` (backend) maupun di `app.js` (saat merender event `handoff` di frontend) — karena ini poin penting yang akan dijelaskan saat presentasi.
- **Semua teks yang tampil di UI dan output laporan berbahasa Indonesia.** Nama variabel/kode tetap boleh bahasa Inggris.
- **Event SSE** menggunakan format `event: <tipe>\ndata: <json>\n\n`. Tipe event: `start`, `progress`, `handoff`, `done` (per agent), `complete` (hasil akhir), `error`.
- **Tidak ada build step di frontend.** File `index.html`, `style.css`, `app.js` dipakai langsung tanpa bundler/transpiler.
- **Jangan hardcode API key** di kode maupun contoh — selalu lewat env var, dengan `.env.example` sebagai dokumentasi nama variabel.
- Backend disajikan dari satu proses (`uvicorn backend.main:app`) yang juga men-serve frontend — cukup satu perintah untuk menjalankan seluruh aplikasi.
