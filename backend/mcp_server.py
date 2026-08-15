"""
MCP Server — Competitor Radar Places Tool.

Mengekspos SATU kemampuan lewat Model Context Protocol (MCP): mencari kompetitor
bisnis lokal (nama, rating, rentang harga, sampel ulasan, koordinat) di sekitar
sebuah lokasi, via Google Maps Places API (Geocoding -> Nearby Search -> Place
Details).

Ini konteks yang TIDAK dimiliki panggilan LLM biasa — model bahasa tidak tahu apa
pun soal bisnis riil di sekitar "Dago, Bandung" hari ini; tool inilah yang memberi
agent akses ke data dunia nyata yang terkini.

Dijalankan sebagai proses subprocess terpisah (stdio transport) yang di-spawn oleh
Data Collector Agent lewat agno.tools.mcp.MCPTools (lihat backend/agents/data_collector.py).
Pemisahan proses ini murni MCP: agent tidak memanggil Google API secara langsung,
melainkan lewat server MCP independen yang bisa dites, dijalankan, dan diganti
sendiri lepas dari kode agent.

Guardrail biaya (kuota harian & cooldown antar-panggilan, lihat backend/rate_limiter.py)
ditegakkan DI DALAM tool ini -- persis di titik panggilan API sungguhan terjadi --
supaya tidak bisa dilewati hanya dengan mengganti instruksi/prompt agent.
"""
import os

import httpx
from mcp.server.fastmcp import FastMCP

from .rate_limiter import GoogleApiGuard

mcp = FastMCP("competitor-radar-places")

_guard = GoogleApiGuard(
    daily_limit=int(os.environ.get("GOOGLE_API_DAILY_LIMIT", "80")),
    min_interval_seconds=float(os.environ.get("GOOGLE_API_MIN_INTERVAL_SECONDS", "3")),
)

_RENTANG_HARGA_BY_LEVEL = {
    0: "Sangat murah",
    1: "Rp10.000 - Rp30.000",
    2: "Rp30.000 - Rp75.000",
    3: "Rp75.000 - Rp200.000",
    4: "Rp200.000+",
}


def _ringkas_error_google(exc: Exception) -> str:
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


@mcp.tool()
def cari_kompetitor(lokasi: str, kategori: str, radius_km: float = 2.0, top_n: int = 5) -> dict:
    """Cari kompetitor bisnis lokal di sekitar sebuah lokasi lewat Google Maps Places API.

    Args:
        lokasi: Area/alamat yang jadi pusat pencarian, mis. "Dago, Bandung".
        kategori: Jenis usaha yang dicari, mis. "coffee shop", "salon", "bengkel".
        radius_km: Radius pencarian dalam kilometer (disarankan 1-5).
        top_n: Jumlah kompetitor teratas yang detailnya diambil (disarankan 5-10).

    Returns:
        Dict berisi `kompetitor` (list nama, alamat, rating, jumlah_review,
        rentang_harga, sampel ulasan, koordinat, place_id), `pusat_lat`/`pusat_lng`
        titik pencarian, dan `total_ulasan_terkumpul`. Kalau `kompetitor` kosong,
        coba panggil ulang dengan `radius_km` lebih besar sebelum menyerah.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        raise RuntimeError("GOOGLE_MAPS_API_KEY tidak tersedia untuk MCP server ini.")

    top_n = max(1, min(int(top_n), 10))
    radius_km = max(1.0, min(float(radius_km), 5.0))

    # --- Guardrail biaya: kuota harian & cooldown, ditegakkan di sini ---------------
    perkiraan_panggilan = 2 + top_n  # 1 geocode + 1 nearby search + top_n place details
    boleh, alasan = _guard.cek_dan_catat(perkiraan_panggilan)
    if not boleh:
        raise RuntimeError(f"Guardrail biaya Google API aktif: {alasan}. Coba lagi nanti.")
    # ---------------------------------------------------------------------------------

    radius_m = int(radius_km * 1000)

    with httpx.Client(timeout=15.0) as client:
        geocode_resp = client.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"address": lokasi, "key": api_key},
        )
        geocode_resp.raise_for_status()
        geo = geocode_resp.json()
        if geo.get("status") != "OK":
            raise ValueError(
                f"Geocoding API: {geo.get('status')} — {geo.get('error_message', 'lihat dokumentasi Google')}"
            )
        loc = geo["results"][0]["geometry"]["location"]

        nearby_resp = client.get(
            "https://maps.googleapis.com/maps/api/place/nearbysearch/json",
            params={
                "location": f"{loc['lat']},{loc['lng']}",
                "radius": radius_m,
                "keyword": kategori,
                "key": api_key,
            },
        )
        nearby_resp.raise_for_status()
        nearby_json = nearby_resp.json()
        if nearby_json.get("status") not in ("OK", "ZERO_RESULTS"):
            raise ValueError(
                f"Places Nearby Search: {nearby_json.get('status')} — "
                f"{nearby_json.get('error_message', 'lihat dokumentasi Google')}"
            )
        places = nearby_json.get("results", [])[:top_n]

        kompetitor = []
        for place in places:
            try:
                detail_resp = client.get(
                    "https://maps.googleapis.com/maps/api/place/details/json",
                    params={
                        "place_id": place["place_id"],
                        "fields": "name,formatted_address,rating,user_ratings_total,price_level,reviews,geometry",
                        "key": api_key,
                    },
                )
                detail_resp.raise_for_status()
                detail = detail_resp.json().get("result", {})
            except Exception as exc:
                raise ValueError(f"Places Details gagal untuk '{place.get('name')}': {_ringkas_error_google(exc)}") from exc

            ulasan = [
                {"teks": r.get("text", ""), "rating": int(r.get("rating", 3)), "penulis": r.get("author_name")}
                for r in detail.get("reviews", [])[:5]
                if r.get("text")
            ]
            detail_loc = detail.get("geometry", {}).get("location", {})

            kompetitor.append(
                {
                    "nama": detail.get("name", place.get("name", "Tanpa nama")),
                    "alamat": detail.get("formatted_address", place.get("vicinity", "-")),
                    "rating": float(detail.get("rating", 0.0)),
                    "jumlah_review": int(detail.get("user_ratings_total", 0)),
                    "rentang_harga": _RENTANG_HARGA_BY_LEVEL.get(detail.get("price_level"), "Tidak diketahui"),
                    "ulasan": ulasan,
                    "lat": detail_loc.get("lat"),
                    "lng": detail_loc.get("lng"),
                    "place_id": place.get("place_id"),
                }
            )

    return {
        "sumber_data": "google_places",
        "kompetitor": kompetitor,
        "total_ulasan_terkumpul": sum(len(k["ulasan"]) for k in kompetitor),
        "pusat_lat": loc.get("lat"),
        "pusat_lng": loc.get("lng"),
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
