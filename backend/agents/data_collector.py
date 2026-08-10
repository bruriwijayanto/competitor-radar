"""
Agent 1 — Data Collector.

Tanggung jawab tunggal: mengambil daftar kompetitor + sampel ulasan berdasarkan
lokasi, kategori, radius, dan top-N yang diminta pengguna.

- Mode mock (default, tanpa API key): pakai backend/mock_data.py.
- Mode real: panggil Google Maps Places API (butuh GOOGLE_MAPS_API_KEY).

Output agent ini (DataCollectorOutput) adalah kontrak A2A yang akan dikonsumsi
langsung oleh Agent 2 (Sentiment & Insight) — lihat orchestrator.py.
"""
from agno.agent import Agent

from ..config import settings
from ..mock_data import generate_mock_kompetitor
from ..schemas import AnalisisRequest, DataCollectorOutput


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
        kompetitor = generate_mock_kompetitor(req.lokasi, req.kategori.value, req.top_n)
        total_ulasan = sum(len(k.ulasan) for k in kompetitor)
        return DataCollectorOutput(
            lokasi=req.lokasi,
            kategori=req.kategori.value,
            radius_km=req.radius_km,
            sumber_data="mock",
            kompetitor=kompetitor,
            total_ulasan_terkumpul=total_ulasan,
        )

    def _run_real(self, req: AnalisisRequest) -> DataCollectorOutput:
        """Ambil data kompetitor nyata dari Google Maps Places API (Nearby Search + Place Details)."""
        import httpx

        from ..schemas import KompetitorRaw, UlasanMentah

        api_key = settings.GOOGLE_MAPS_API_KEY
        radius_m = int(req.radius_km * 1000)

        try:
            with httpx.Client(timeout=15.0) as client:
                geocode_resp = client.get(
                    "https://maps.googleapis.com/maps/api/geocode/json",
                    params={"address": req.lokasi, "key": api_key},
                )
                geocode_resp.raise_for_status()
                geo = geocode_resp.json()
                if not geo.get("results"):
                    raise ValueError("Lokasi tidak ditemukan oleh Google Geocoding API")
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
                places = nearby_resp.json().get("results", [])[: req.top_n]

                kompetitor: list[KompetitorRaw] = []
                for place in places:
                    detail_resp = client.get(
                        "https://maps.googleapis.com/maps/api/place/details/json",
                        params={
                            "place_id": place["place_id"],
                            "fields": "name,formatted_address,rating,user_ratings_total,price_level,reviews",
                            "key": api_key,
                        },
                    )
                    detail_resp.raise_for_status()
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

                    kompetitor.append(
                        KompetitorRaw(
                            nama=detail.get("name", place.get("name", "Tanpa nama")),
                            alamat=detail.get("formatted_address", place.get("vicinity", "-")),
                            rating=float(detail.get("rating", 0.0)),
                            jumlah_review=int(detail.get("user_ratings_total", 0)),
                            rentang_harga=rentang_harga,
                            ulasan=ulasan,
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
            )
        except Exception:
            # Fallback aman: jika real API gagal (key salah/kuota/dsb), demo tetap jalan pakai mock.
            return self._run_mock(req)
