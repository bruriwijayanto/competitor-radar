"""
Guardrails eksplisit yang ditegakkan SISTEM (bukan sekadar diuraikan lewat instruksi
prompt) — dikumpulkan di satu tempat supaya mudah ditunjuk & dijelaskan saat presentasi.

1. Validasi & pembatasan ruang lingkup input — lihat backend/schemas.py
   (AnalisisRequest: kategori dibatasi Enum whitelist, radius_km & top_n dibatasi
   Field(ge=..., le=...), lokasi & nama_usaha dibersihkan lewat `bersihkan_input_teks`
   di bawah sebelum disimpan di request).
2. Anti prompt-injection pada teks bebas dari pengguna — `bersihkan_input_teks` di
   bawah ini, dipanggil dari schemas.py sebelum `lokasi`/`nama_usaha` disimpan, jadi
   SETIAP agent yang menerima AnalisisRequest otomatis menerima versi yang sudah
   dibersihkan.
3. Guardrail biaya/kuota Google API — ditegakkan di dalam backend/mcp_server.py
   (system boundary tempat panggilan API sungguhan terjadi), lihat backend/rate_limiter.py.
4. Penanganan kegagalan — pipeline TIDAK punya fallback ke data palsu (mode mock sudah
   dihapus). Kalau satu agent gagal (key salah, kuota habis, LLM error, dst), orchestrator
   menghentikan pipeline dan mengirim event SSE `error` yang jelas ke frontend — gagal
   secara terlihat, bukan diam-diam menyajikan hasil yang menyesatkan.
5. Human-in-the-loop sebelum Strategy Agent — lihat backend/approval_store.py &
   boundary HITL di backend/orchestrator.py.
"""
import re

MAKS_PANJANG_LOKASI = 120
MAKS_PANJANG_NAMA_USAHA = 80

# Pola yang sering dipakai untuk mencoba membajak instruksi sistem lewat field bebas
# (lokasi/nama_usaha) yang nanti diselipkan ke prompt LLM di Sentiment & Strategy Agent.
_POLA_MENCURIGAKAN = re.compile(
    r"(ignore (all|previous) instructions|abaikan (semua |)instruksi|system prompt|"
    r"you are now|kamu sekarang adalah|</?system>|</?prompt>)",
    re.IGNORECASE,
)


def bersihkan_input_teks(teks: str | None, maks_panjang: int) -> str | None:
    """Guardrail input: buang karakter kontrol, batasi panjang, dan tandai/redaksi pola
    yang menyerupai upaya prompt-injection sebelum teks bebas dari pengguna diselipkan
    ke prompt LLM manapun. Ditegakkan di level validasi Pydantic (schemas.py), bukan
    cuma diandalkan lewat instruksi agent."""
    if not teks:
        return teks
    bersih = re.sub(r"[\x00-\x1f\x7f]", " ", teks)
    bersih = re.sub(r"\s+", " ", bersih).strip()
    bersih = _POLA_MENCURIGAKAN.sub("[konten dihapus oleh guardrail]", bersih)
    return bersih[:maks_panjang]
