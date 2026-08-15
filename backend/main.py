"""
FastAPI app — menyajikan frontend (StaticFiles) dan endpoint SSE untuk pipeline
analisis kompetitor. Dijalankan satu proses saja: `uvicorn backend.main:app`.
"""
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from .approval_store import approval_store
from .config import settings
from .orchestrator import run_pipeline_sse
from .rate_limiter import GoogleApiGuard
from .schemas import AnalisisRequest, KategoriUsaha, KeputusanHITL

# Guardrail konfigurasi: tolak start kalau key wajib belum diisi (fail fast, pesan jelas)
# daripada aplikasi jalan lalu gagal misterius di tengah pipeline demo.
settings.validasi_atau_gagal()

# Guard kuota Google API dibaca di sini hanya untuk keperluan monitoring (/api/health).
# Penegakannya sendiri terjadi di dalam backend/mcp_server.py — lihat komentar di sana.
# State-nya file-based (bukan in-memory) jadi tetap akurat meski dibaca dari proses lain.
_google_api_guard = GoogleApiGuard(
    daily_limit=settings.GOOGLE_API_DAILY_LIMIT,
    min_interval_seconds=settings.GOOGLE_API_MIN_INTERVAL_SECONDS,
)

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(title="Competitor Radar API")

# Cadangan CORS — tidak wajib karena frontend disajikan dari origin yang sama (StaticFiles),
# tapi tetap disediakan untuk kemudahan pengembangan/testing terpisah.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "google_maps_key_terpasang": settings.has_google_key,
        "openrouter_key_terpasang": settings.has_openrouter_key,
        "google_api_kuota": _google_api_guard.status(),
    }


@app.get("/api/maps-key")
def maps_key():
    """
    Ekspos Google Maps JavaScript API key supaya frontend bisa merender peta
    sungguhan. Key Maps JS memang didesain untuk dipakai di sisi client dan
    dibatasi lewat HTTP referrer restriction di Google Cloud Console — bukan secret
    server seperti key REST lain.
    """
    return {"key": settings.GOOGLE_MAPS_API_KEY or None}


@app.get("/api/analisis/stream")
def analisis_stream(
    lokasi: str = Query(..., min_length=1),
    kategori: KategoriUsaha = Query(...),
    radius_km: float = Query(2.0, ge=1, le=5),
    top_n: int = Query(5),
    nama_usaha: str | None = Query(None),
):
    """Endpoint SSE utama. Dikonsumsi frontend lewat `new EventSource(...)` (butuh GET, bukan POST)."""
    top_n = 10 if top_n >= 10 else 5
    req = AnalisisRequest(
        nama_usaha=nama_usaha or None,
        lokasi=lokasi,
        kategori=kategori,
        radius_km=radius_km,
        top_n=top_n,
    )
    return StreamingResponse(
        run_pipeline_sse(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # jaga-jaga di belakang reverse proxy nginx
        },
    )


@app.post("/api/analisis/{run_id}/keputusan")
def keputusan_hitl(run_id: str, keputusan: KeputusanHITL):
    """
    Endpoint human-in-the-loop: dipanggil frontend saat pengguna menekan tombol
    Setujui/Batalkan pada titik pemeriksaan antara Sentiment Insight Agent dan
    Strategy Agent (lihat "HITL BOUNDARY" di backend/orchestrator.py). Membangunkan
    generator SSE yang sedang menunggu (threading.Event) di backend/approval_store.py.
    """
    ok = approval_store.putuskan(run_id, keputusan)
    if not ok:
        raise HTTPException(status_code=404, detail="run_id tidak ditemukan atau sudah kedaluwarsa/selesai")
    return {"status": "ok"}


# Mount frontend PALING TERAKHIR supaya tidak menimpa route /api/*.
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
