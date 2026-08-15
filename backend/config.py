"""Konfigurasi aplikasi — semua nilai sensitif dibaca dari environment variable, tidak ada yang di-hardcode.

Aplikasi ini HANYA berjalan dalam mode nyata: Data Collector memanggil Google Maps
Places API lewat MCP server (backend/mcp_server.py), Sentiment & Strategy Agent
memanggil LLM lewat OpenRouter. Tidak ada mode "mock"/heuristik — kalau key tidak
tersedia, aplikasi menolak start (fail fast) alih-alih diam-diam menyajikan data
palsu. Ini bagian dari guardrail validasi konfigurasi di level sistem.
"""
import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    GOOGLE_MAPS_API_KEY: str = os.getenv("GOOGLE_MAPS_API_KEY", "")

    # Pengaman supaya panggilan Google API (di luar kuota gratis bisa berbayar) tidak lepas
    # kendali. Ditegakkan di dalam backend/mcp_server.py (system boundary tempat panggilan
    # sungguhan terjadi) — lihat backend/rate_limiter.py. Tetap pasang Quota & Budget Alert
    # di Google Cloud Console sebagai pengaman utama (lihat README bagian "Batasi Biaya
    # Google API").
    GOOGLE_API_DAILY_LIMIT: int = int(os.getenv("GOOGLE_API_DAILY_LIMIT", "80"))
    GOOGLE_API_MIN_INTERVAL_SECONDS: float = float(os.getenv("GOOGLE_API_MIN_INTERVAL_SECONDS", "3"))

    # LLM lewat OpenRouter (satu key, akses banyak model/provider sekaligus).
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")

    # Guardrail human-in-the-loop: berapa lama pipeline menunggu keputusan manusia
    # (approve/reject) sebelum Strategy Agent boleh jalan, sebelum otomatis dibatalkan.
    HITL_TIMEOUT_SECONDS: int = int(os.getenv("HITL_TIMEOUT_SECONDS", "300"))

    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    @property
    def has_google_key(self) -> bool:
        return bool(self.GOOGLE_MAPS_API_KEY)

    @property
    def has_openrouter_key(self) -> bool:
        return bool(self.OPENROUTER_API_KEY)

    def validasi_atau_gagal(self) -> None:
        """Guardrail konfigurasi: tolak start kalau key wajib belum diisi, dengan pesan
        yang jelas — daripada aplikasi jalan lalu gagal misterius di tengah pipeline."""
        hilang = []
        if not self.has_google_key:
            hilang.append("GOOGLE_MAPS_API_KEY")
        if not self.has_openrouter_key:
            hilang.append("OPENROUTER_API_KEY")
        if hilang:
            raise RuntimeError(
                "Konfigurasi tidak lengkap — aplikasi ini hanya berjalan dalam mode nyata "
                f"(tanpa mock). Env var berikut wajib diisi di .env: {', '.join(hilang)}. "
                "Lihat .env.example."
            )


settings = Settings()
