"""
FastAPI app — menyajikan frontend (StaticFiles) dan endpoint SSE untuk pipeline
analisis kompetitor. Dijalankan satu proses saja: `uvicorn backend.main:app`.
"""
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .orchestrator import run_pipeline_sse
from .schemas import AnalisisRequest, KategoriUsaha

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
        "mode": settings.APP_MODE,
        "google_maps_key_terpasang": settings.has_google_key,
        "openai_key_terpasang": settings.has_openai_key,
    }


@app.get("/api/maps-key")
def maps_key():
    """
    Ekspos Google Maps JavaScript API key (jika diset) supaya frontend bisa merender
    peta sungguhan. Key Maps JS memang didesain untuk dipakai di sisi client dan
    dibatasi lewat HTTP referrer restriction di Google Cloud Console — bukan secret
    server seperti key REST lain. Jika key tidak diset, frontend otomatis memakai
    visualisasi radar buatan sendiri (tidak butuh API key apa pun).
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


# Mount frontend PALING TERAKHIR supaya tidak menimpa route /api/*.
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
