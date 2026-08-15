"""
Human-in-the-loop — titik pemeriksaan wajib antara Agent 2 (Sentiment & Insight) dan
Agent 3 (Strategy).

Kenapa di sini: Agent 3 mengubah data mentah jadi REKOMENDASI BISNIS yang mungkin
langsung dipakai pemilik usaha untuk mengambil keputusan (ubah harga, ubah layanan,
dst). Kalau data kompetitor/insight di baliknya salah atau tidak relevan (mis. lokasi
salah geocode, kategori keliru menangkap bisnis lain), Strategy Agent tetap akan
menyusun rekomendasi yang PERCAYA DIRI meski keliru — dan tanpa titik pemeriksaan,
kekeliruan itu langsung sampai ke pengguna sebagai "saran AI". Guardrail ini juga
mencegah pipeline diam-diam membakar kuota LLM lebih lanjut atas data yang sudah
kelihatan tidak masuk akal.

Implementasi: pipeline (orchestrator.py, generator SINKRON yang jalan di threadpool
terpisah — lihat komentar di sana) dijeda dengan `threading.Event` sampai keputusan
manusia masuk lewat endpoint POST /api/analisis/{run_id}/keputusan, atau sampai timeout
tercapai (auto-batal — guardrail tambahan supaya proses tidak menggantung selamanya).
"""
import threading
import uuid
from typing import Optional

from .schemas import KeputusanHITL


class ApprovalStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, dict] = {}

    def buat(self) -> str:
        run_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._entries[run_id] = {"event": threading.Event(), "keputusan": None}
        return run_id

    def putuskan(self, run_id: str, keputusan: KeputusanHITL) -> bool:
        with self._lock:
            entry = self._entries.get(run_id)
            if entry is None:
                return False
            entry["keputusan"] = keputusan
        entry["event"].set()
        return True

    def tunggu(self, run_id: str, timeout: float) -> Optional[KeputusanHITL]:
        """Blokir sampai ada keputusan atau timeout. Return None kalau timeout
        (dianggap sebagai penolakan otomatis oleh guardrail)."""
        with self._lock:
            entry = self._entries.get(run_id)
        if entry is None:
            return None
        selesai = entry["event"].wait(timeout)
        with self._lock:
            self._entries.pop(run_id, None)
        return entry["keputusan"] if selesai else None


approval_store = ApprovalStore()
