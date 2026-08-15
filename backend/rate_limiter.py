"""
Guardrail biaya Google API (Places/Geocoding) — ditegakkan di dalam backend/mcp_server.py,
persis pada titik panggilan API sungguhan terjadi (system boundary), bukan cuma di
instruksi agent.

State disimpan ke file JSON (bukan cuma in-memory) karena backend/mcp_server.py
dijalankan sebagai proses MCP terpisah yang di-spawn ulang oleh Data Collector Agent
setiap kali pipeline jalan (lihat MCPTools di agents/data_collector.py) — kalau
disimpan in-memory saja, kuota harian akan reset tiap request dan guardrail-nya
percuma. File dikunci lewat fcntl.flock supaya aman dari race condition antar-proses.
"""
import fcntl
import json
import time
from datetime import date
from pathlib import Path

STATE_FILE = Path(__file__).resolve().parent / "data" / "google_api_guard_state.json"


class GoogleApiGuard:
    def __init__(self, daily_limit: int, min_interval_seconds: float) -> None:
        self.daily_limit = daily_limit
        self.min_interval_seconds = min_interval_seconds
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

    def _baca_state(self) -> dict:
        if not STATE_FILE.exists():
            return {"tanggal": str(date.today()), "jumlah_hari_ini": 0, "waktu_terakhir": 0.0}
        try:
            with STATE_FILE.open("r") as f:
                state = json.load(f)
        except (json.JSONDecodeError, OSError):
            state = {}
        if state.get("tanggal") != str(date.today()):
            state = {"tanggal": str(date.today()), "jumlah_hari_ini": 0, "waktu_terakhir": 0.0}
        state.setdefault("jumlah_hari_ini", 0)
        state.setdefault("waktu_terakhir", 0.0)
        return state

    def _dengan_lock(self, fn):
        with STATE_FILE.open("a+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                state = self._baca_state()
                hasil, state_baru = fn(state)
                if state_baru is not None:
                    f.seek(0)
                    f.truncate()
                    json.dump(state_baru, f)
                return hasil
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def status(self) -> dict:
        def _fn(state):
            return (
                {
                    "dipakai_hari_ini": state["jumlah_hari_ini"],
                    "batas_harian": self.daily_limit,
                    "sisa": max(0, self.daily_limit - state["jumlah_hari_ini"]),
                },
                None,
            )

        return self._dengan_lock(_fn)

    def cek_dan_catat(self, perkiraan_panggilan: int) -> tuple[bool, str]:
        """Cek cooldown & kuota harian sekaligus, DAN langsung mencatat kalau lolos —
        supaya pengecekan & pencatatan atomik dalam satu lock (hindari race condition
        antara "cek" dan "pakai"). Return (boleh_jalan, alasan_jika_ditolak)."""

        def _fn(state):
            sekarang = time.time()
            if sekarang - state["waktu_terakhir"] < self.min_interval_seconds:
                return (False, f"cooldown {self.min_interval_seconds:.0f}s belum lewat sejak pencarian sebelumnya"), None
            if state["jumlah_hari_ini"] + perkiraan_panggilan > self.daily_limit:
                return (
                    (False, f"kuota Google API harian tercapai ({state['jumlah_hari_ini']}/{self.daily_limit})"),
                    None,
                )
            state["waktu_terakhir"] = sekarang
            state["jumlah_hari_ini"] += perkiraan_panggilan
            return (True, ""), state

        return self._dengan_lock(_fn)
