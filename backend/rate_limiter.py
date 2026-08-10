"""
Pengaman pemakaian Google API (Places/Geocoding) di level aplikasi — supaya bug,
klik berulang, atau demo yang lupa dimatikan tidak bikin tagihan membengkak tanpa
disadari. In-memory, reset per hari server berjalan — cukup untuk skala demo satu
proses (bukan pengganti Quota/Budget Alert di Google Cloud Console, lihat README).
"""
import threading
import time
from datetime import date

from .config import settings


class GoogleApiGuard:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tanggal = date.today()
        self._jumlah_panggilan_hari_ini = 0
        self._waktu_request_terakhir = 0.0

    def _reset_jika_hari_baru(self) -> None:
        if date.today() != self._tanggal:
            self._tanggal = date.today()
            self._jumlah_panggilan_hari_ini = 0

    def status(self) -> dict:
        with self._lock:
            self._reset_jika_hari_baru()
            return {
                "dipakai_hari_ini": self._jumlah_panggilan_hari_ini,
                "batas_harian": settings.GOOGLE_API_DAILY_LIMIT,
                "sisa": max(0, settings.GOOGLE_API_DAILY_LIMIT - self._jumlah_panggilan_hari_ini),
            }

    def cek_kuota(self, perkiraan_panggilan: int) -> bool:
        """True kalau perkiraan jumlah panggilan masih muat di sisa kuota harian."""
        with self._lock:
            self._reset_jika_hari_baru()
            return self._jumlah_panggilan_hari_ini + perkiraan_panggilan <= settings.GOOGLE_API_DAILY_LIMIT

    def cek_cooldown(self) -> bool:
        """True kalau sudah lewat jeda minimum sejak request real-mode terakhir (mencegah spam klik)."""
        with self._lock:
            sekarang = time.monotonic()
            if sekarang - self._waktu_request_terakhir < settings.GOOGLE_API_MIN_INTERVAL_SECONDS:
                return False
            self._waktu_request_terakhir = sekarang
            return True

    def catat_panggilan(self, jumlah: int = 1) -> None:
        with self._lock:
            self._reset_jika_hari_baru()
            self._jumlah_panggilan_hari_ini += jumlah


google_api_guard = GoogleApiGuard()
