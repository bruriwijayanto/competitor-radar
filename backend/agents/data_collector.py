"""
Agent 1 — Data Collector.

Tanggung jawab tunggal: mengambil daftar kompetitor + sampel ulasan berdasarkan
lokasi, kategori, radius, dan top-N yang diminta pengguna.

- Mode mock (default, tanpa API key): pakai backend/mock_data.py.
- Mode real: panggil Google Maps Places API (butuh GOOGLE_MAPS_API_KEY). Dibatasi
  backend/rate_limiter.py (cooldown antar-request + kuota harian) supaya biaya tidak
  lepas kendali; kalau limit tercapai, otomatis fallback ke mock (lihat sumber_data
  pada output untuk tahu alasannya).

Output agent ini (DataCollectorOutput) adalah kontrak A2A yang akan dikonsumsi
langsung oleh Agent 2 (Sentiment & Insight) — lihat orchestrator.py.
"""
import logging

from agno.agent import Agent

from ..config import settings
from ..mock_data import generate_mock_kompetitor
from ..rate_limiter import google_api_guard
from ..schemas import AnalisisRequest, DataCollectorOutput

logger = logging.getLogger(__name__)


def _ringkas_error_google(exc: Exception) -> str:
    """Ekstrak pesan error Google API yang ringkas & bisa dibaca dari berbagai tipe exception."""
    import httpx

    if isinstance(exc, httpx.HTTPStatusError):
        try:
            body = exc.response.json()
            status = body.get("status") or body.get("error", {}).get("status")
            pesan = body.get("error_message") or body.get("error", {}).get("message")
            if status or pesan:
                return f"{status or exc.response.status_code}: {pesan or 'lihat log server'}"
        except Exception:
            pass
        return f"HTTP {exc.response.status_code}"
    return f"{type(exc).__name__}: {exc}"


class DataCollectorAgent:
    name = "Data Collector Agent"

    def __init__(self) -> None:
        # Agent Agno murni informatif (identitas & instruksi) untuk kebutuhan mode `real`
        # yang nanti bisa dipakai memanggil tool pencarian tempat via LLM. Untuk mode
        # mock kita tidak memanggil LLM sama sekali agar tetap 100% jalan tanpa API key.
        self.agent = Agent(
            name=self.name,
            instructions=[
                "Kamu adalah agent pengumpul data kompetitor bisnis lokal.",
                "Kembalikan daftar kompetitor beserta rating, jumlah review, rentang harga, dan sampel ulasan.",
            ],
        )

    def run(self, req: AnalisisRequest) -> DataCollectorOutput:
        if settings.is_real_mode_requested and settings.has_google_key:
            return self._run_real(req)
        return self._run_mock(req)

    def _run_mock(self, req: AnalisisRequest) -> DataCollectorOutput:
        kompetitor, pusat_lat, pusat_lng = generate_mock_kompetitor(
            req.lokasi, req.kategori.value, req.top_n, req.radius_km
        )
        total_ulasan = sum(len(k.ulasan) for k in kompetitor)
        return DataCollectorOutput(
            lokasi=req.lokasi,
            kategori=req.kategori.value,
            radius_km=req.radius_km,
            sumber_data="mock",
            kompetitor=kompetitor,
            total_ulasan_terkumpul=total_ulasan,
            pusat_lat=pusat_lat,
            pusat_lng=pusat_lng,
        )

    def _run_real(self, req: AnalisisRequest) -> DataCollectorOutput:
        """Ambil data kompetitor nyata dari Google Maps Places API (Nearby Search + Place Details)."""
        import httpx

        from ..schemas import KompetitorRaw, UlasanMentah

        # --- Pengaman biaya: cooldown & kuota harian (lihat backend/rate_limiter.py) ---
        if not google_api_guard.cek_cooldown():
            hasil = self._run_mock(req)
            jeda = settings.GOOGLE_API_MIN_INTERVAL_SECONDS
            hasil.sumber_data = f"mock (cooldown {jeda:.0f}s belum lewat sejak request Google API terakhir)"
            return hasil

        # Perkiraan panggilan: 1 geocode + 1 nearby search + top_n place details.
        perkiraan_panggilan = 2 + req.top_n
        if not google_api_guard.cek_kuota(perkiraan_panggilan):
            status = google_api_guard.status()
            hasil = self._run_mock(req)
            hasil.sumber_data = (
                f"mock (kuota Google API harian tercapai: {status['dipakai_hari_ini']}/{status['batas_harian']})"
            )
            return hasil
        # --------------------------------------------------------------------------------

        api_key = settings.GOOGLE_MAPS_API_KEY
        radius_m = int(req.radius_km * 1000)

        try:
            with httpx.Client(timeout=15.0) as client:
                geocode_resp = client.get(
                    "https://maps.googleapis.com/maps/api/geocode/json",
                    params={"address": req.lokasi, "key": api_key},
                )
                geocode_resp.raise_for_status()
                google_api_guard.catat_panggilan()
                geo = geocode_resp.json()
                # Google Geocoding/Places API sering balas HTTP 200 walau gagal — status &
                # pesan errornya ada di body JSON, bukan di status code, jadi raise_for_status()
                # saja tidak cukup untuk mendeteksi key salah/API belum aktif/billing, dll.
                if geo.get("status") not in ("OK",):
                    raise ValueError(
                        f"Geocoding API: {geo.get('status')} — {geo.get('error_message', 'lihat dokumentasi Google')}"
                    )
                loc = geo["results"][0]["geometry"]["location"]

                nearby_resp = client.get(
                    "https://maps.googleapis.com/maps/api/place/nearbysearch/json",
                    params={
                        "location": f"{loc['lat']},{loc['lng']}",
                        "radius": radius_m,
                        "keyword": req.kategori.value,
                        "key": api_key,
                    },
                )
                nearby_resp.raise_for_status()
                google_api_guard.catat_panggilan()
                nearby_json = nearby_resp.json()
                if nearby_json.get("status") not in ("OK", "ZERO_RESULTS"):
                    raise ValueError(
                        f"Places Nearby Search: {nearby_json.get('status')} — "
                        f"{nearby_json.get('error_message', 'lihat dokumentasi Google')}"
                    )
                places = nearby_json.get("results", [])[: req.top_n]

                kompetitor: list[KompetitorRaw] = []
                for place in places:
                    detail_resp = client.get(
                        "https://maps.googleapis.com/maps/api/place/details/json",
                        params={
                            "place_id": place["place_id"],
                            "fields": "name,formatted_address,rating,user_ratings_total,price_level,reviews,geometry",
                            "key": api_key,
                        },
                    )
                    detail_resp.raise_for_status()
                    google_api_guard.catat_panggilan()
                    detail = detail_resp.json().get("result", {})

                    price_level = detail.get("price_level")
                    rentang_harga = {
                        0: "Sangat murah",
                        1: "Rp10.000 - Rp30.000",
                        2: "Rp30.000 - Rp75.000",
                        3: "Rp75.000 - Rp200.000",
                        4: "Rp200.000+",
                    }.get(price_level, "Tidak diketahui")

                    ulasan = [
                        UlasanMentah(
                            teks=r.get("text", ""),
                            rating=int(r.get("rating", 3)),
                            penulis=r.get("author_name"),
                        )
                        for r in detail.get("reviews", [])[:5]
                        if r.get("text")
                    ]

                    detail_loc = detail.get("geometry", {}).get("location", {})

                    kompetitor.append(
                        KompetitorRaw(
                            nama=detail.get("name", place.get("name", "Tanpa nama")),
                            alamat=detail.get("formatted_address", place.get("vicinity", "-")),
                            rating=float(detail.get("rating", 0.0)),
                            jumlah_review=int(detail.get("user_ratings_total", 0)),
                            rentang_harga=rentang_harga,
                            ulasan=ulasan,
                            lat=detail_loc.get("lat"),
                            lng=detail_loc.get("lng"),
                            place_id=place.get("place_id"),
                        )
                    )

            if not kompetitor:
                raise ValueError("Tidak ada kompetitor ditemukan dari Google Places API")

            total_ulasan = sum(len(k.ulasan) for k in kompetitor)
            return DataCollectorOutput(
                lokasi=req.lokasi,
                kategori=req.kategori.value,
                radius_km=req.radius_km,
                sumber_data="google_places",
                kompetitor=kompetitor,
                total_ulasan_terkumpul=total_ulasan,
                pusat_lat=loc.get("lat"),
                pusat_lng=loc.get("lng"),
            )
        except Exception as exc:
            # Fallback aman: jika real API gagal (key salah/API belum aktif/billing/dsb), demo tetap
            # jalan pakai mock. Alasannya dicatat ke log server DAN diselipkan ke sumber_data supaya
            # langsung kelihatan di panel log UI — tidak silent, biar gampang didiagnosis.
            alasan = _ringkas_error_google(exc)
            logger.warning("Google Places API gagal, fallback ke mock: %s", alasan)
            hasil = self._run_mock(req)
            hasil.sumber_data = f"mock (Google API gagal: {alasan})"
            return hasil
