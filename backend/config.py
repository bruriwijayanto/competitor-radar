"""Konfigurasi aplikasi — semua nilai sensitif dibaca dari environment variable, tidak ada yang di-hardcode."""
import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    # "mock" (default, tanpa API key) atau "real" (Google Places API + LLM)
    APP_MODE: str = os.getenv("APP_MODE", "mock").lower()

    GOOGLE_MAPS_API_KEY: str = os.getenv("GOOGLE_MAPS_API_KEY", "")

    # Pengaman supaya panggilan Google API (di luar kuota gratis bisa berbayar) tidak lepas
    # kendali. Ini pengaman di level aplikasi — tetap pasang Quota & Budget Alert di Google
    # Cloud Console sebagai pengaman utama (lihat README bagian "Batasi Biaya Google API").
    GOOGLE_API_DAILY_LIMIT: int = int(os.getenv("GOOGLE_API_DAILY_LIMIT", "80"))
    GOOGLE_API_MIN_INTERVAL_SECONDS: float = float(os.getenv("GOOGLE_API_MIN_INTERVAL_SECONDS", "3"))

    # LLM lewat OpenRouter (satu key, akses banyak model/provider sekaligus).
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")

    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    @property
    def is_real_mode_requested(self) -> bool:
        return self.APP_MODE == "real"

    @property
    def has_google_key(self) -> bool:
        return bool(self.GOOGLE_MAPS_API_KEY)

    @property
    def has_openrouter_key(self) -> bool:
        return bool(self.OPENROUTER_API_KEY)


settings = Settings()
