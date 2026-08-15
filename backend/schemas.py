"""
Skema Pydantic terpusat untuk Competitor Radar.

Semua payload yang mengalir antar-agent (pola ala Agent-to-Agent / A2A) didefinisikan
di sini. Aturan proyek: output Agent N divalidasi sebagai AgentNOutput, lalu dipakai
langsung sebagai (bagian dari) AgentN+1Input pada agent berikutnya. Ini membuat
"kontrak data" antar-agent eksplisit dan mudah dijelaskan saat presentasi.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from .guardrails import MAKS_PANJANG_LOKASI, MAKS_PANJANG_NAMA_USAHA, bersihkan_input_teks


# ---------------------------------------------------------------------------
# Request dari frontend
# ---------------------------------------------------------------------------

class KategoriUsaha(str, Enum):
    coffee_shop = "coffee shop"
    restoran = "restoran"
    salon = "salon"
    bengkel = "bengkel"
    klinik = "klinik"
    laundry = "laundry"
    apotek = "apotek"
    minimarket = "minimarket"
    gym = "gym"
    toko_fashion = "toko fashion"
    software_developer = "software developer"


class AnalisisRequest(BaseModel):
    nama_usaha: Optional[str] = Field(None, description="Nama usaha pengguna (opsional)")
    lokasi: str = Field(..., min_length=1, description="Lokasi/area yang dianalisis, mis. 'Dago, Bandung'")
    kategori: KategoriUsaha = Field(..., description="Kategori usaha yang dianalisis")
    radius_km: float = Field(2.0, ge=1, le=5, description="Radius pencarian kompetitor (km)")
    top_n: int = Field(5, ge=1, le=10, description="Jumlah kompetitor teratas yang dianalisis (5 atau 10)")

    # --- Guardrail input: bersihkan teks bebas sebelum diselipkan ke prompt LLM
    # manapun di sepanjang pipeline (lihat backend/guardrails.py). ---
    @field_validator("lokasi")
    @classmethod
    def _bersihkan_lokasi(cls, v: str) -> str:
        bersih = bersihkan_input_teks(v, MAKS_PANJANG_LOKASI)
        if not bersih:
            raise ValueError("lokasi tidak boleh kosong setelah dibersihkan")
        return bersih

    @field_validator("nama_usaha")
    @classmethod
    def _bersihkan_nama_usaha(cls, v: Optional[str]) -> Optional[str]:
        return bersihkan_input_teks(v, MAKS_PANJANG_NAMA_USAHA)


# ---------------------------------------------------------------------------
# Agent 1 — Data Collector
# ---------------------------------------------------------------------------

class UlasanMentah(BaseModel):
    teks: str
    rating: int = Field(..., ge=1, le=5)
    penulis: Optional[str] = None


class KompetitorRaw(BaseModel):
    nama: str
    alamat: str
    rating: float = Field(..., ge=0, le=5)
    jumlah_review: int
    rentang_harga: str = Field(..., description="mis. 'Rp15.000 - Rp35.000'")
    ulasan: List[UlasanMentah] = Field(default_factory=list)
    lat: Optional[float] = Field(None, description="Koordinat lintang dari Google Places")
    lng: Optional[float] = Field(None, description="Koordinat bujur dari Google Places")
    place_id: Optional[str] = Field(None, description="Google Place ID")


class DataCollectorOutput(BaseModel):
    """Output Agent 1 -> menjadi input Agent 2 (batas A2A #1)."""
    lokasi: str
    kategori: str
    radius_km: float
    sumber_data: str = Field(..., description="Selalu 'google_places' — lihat backend/mcp_server.py")
    kompetitor: List[KompetitorRaw]
    total_ulasan_terkumpul: int
    pusat_lat: Optional[float] = Field(None, description="Koordinat lintang titik pusat pencarian")
    pusat_lng: Optional[float] = Field(None, description="Koordinat bujur titik pusat pencarian")


# ---------------------------------------------------------------------------
# Agent 2 — Sentiment & Insight
# ---------------------------------------------------------------------------

class SentimenLabel(str, Enum):
    positif = "positif"
    negatif = "negatif"
    netral = "netral"


class TemaUlasan(str, Enum):
    harga = "harga"
    pelayanan = "pelayanan"
    kebersihan = "kebersihan"
    lokasi_parkir = "lokasi/parkir"
    kualitas_produk = "kualitas produk"


class UlasanTerklasifikasi(BaseModel):
    teks: str
    sentimen: SentimenLabel
    tema: List[TemaUlasan] = Field(default_factory=list)


class InsightKompetitor(BaseModel):
    nama: str
    rating: float
    jumlah_review: int
    rentang_harga: str
    jumlah_ulasan_dianalisis: int
    persentase_positif: float
    persentase_negatif: float
    persentase_netral: float
    tema_pujian: List[TemaUlasan] = Field(default_factory=list, description="Tema yang paling sering dipuji")
    tema_keluhan: List[TemaUlasan] = Field(default_factory=list, description="Tema yang paling sering dikeluhkan")
    kekuatan: List[str] = Field(default_factory=list)
    kelemahan: List[str] = Field(default_factory=list)
    ulasan_terklasifikasi: List[UlasanTerklasifikasi] = Field(default_factory=list)


class InsightOutput(BaseModel):
    """Output Agent 2 -> menjadi input Agent 3 (batas A2A #2)."""
    lokasi: str
    kategori: str
    insight_kompetitor: List[InsightKompetitor]
    ringkasan_tema_pasar: dict = Field(
        default_factory=dict,
        description="Agregasi jumlah kemunculan tiap tema pujian/keluhan lintas kompetitor",
    )
    total_ulasan_dianalisis: int


class InsightKompetitorLLM(BaseModel):
    """Subset InsightKompetitor yang diminta ke LLM — tanpa `ulasan_terklasifikasi`
    (echo tiap ulasan individual) supaya respons LLM ringkas & tidak gampang
    terpotong oleh batas token."""
    nama: str
    rating: float
    jumlah_review: int
    rentang_harga: str
    jumlah_ulasan_dianalisis: int
    persentase_positif: float
    persentase_negatif: float
    persentase_netral: float
    tema_pujian: List[TemaUlasan] = Field(default_factory=list, description="Tema yang paling sering dipuji")
    tema_keluhan: List[TemaUlasan] = Field(default_factory=list, description="Tema yang paling sering dikeluhkan")
    kekuatan: List[str] = Field(default_factory=list)
    kelemahan: List[str] = Field(default_factory=list)


class InsightOutputLLM(BaseModel):
    """Subset InsightOutput yang diminta ke LLM pada mode real.

    `ringkasan_tema_pasar` (dict generik) & `total_ulasan_dianalisis` sengaja tidak
    diminta ke LLM karena field dict tanpa properti tetap tidak didukung oleh mode
    structured output ketat (strict JSON schema) OpenAI/OpenRouter. Dua field itu
    dihitung ulang secara deterministik di backend dari `insight_kompetitor`
    (lihat `_agregasi_tema_pasar` di sentiment_insight.py). `ulasan_terklasifikasi`
    per kompetitor juga tidak diminta (lihat InsightKompetitorLLM) — tidak dipakai
    di frontend dan boros token kalau LLM harus meng-echo tiap ulasan.
    """
    lokasi: str
    kategori: str
    insight_kompetitor: List[InsightKompetitorLLM]


# ---------------------------------------------------------------------------
# Agent 3 — Strategy
# ---------------------------------------------------------------------------

class PrioritasRekomendasi(str, Enum):
    tinggi = "tinggi"
    sedang = "sedang"
    rendah = "rendah"


class Rekomendasi(BaseModel):
    judul: str
    deskripsi: str
    prioritas: PrioritasRekomendasi
    kategori: str = Field(..., description="mis. 'positioning', 'quick win', 'diferensiator'")


class GapAnalysis(BaseModel):
    celah_pasar: List[str] = Field(default_factory=list, description="Kebutuhan pasar yang belum dilayani baik")
    peluang_diferensiasi: List[str] = Field(default_factory=list)


class StrategyOutput(BaseModel):
    """Output Agent 3 -> laporan akhir yang dikirim ke frontend."""
    executive_summary: str
    gap_analysis: GapAnalysis
    rekomendasi: List[Rekomendasi]
    disclaimer: str


# ---------------------------------------------------------------------------
# Laporan akhir gabungan (dikirim via event SSE `complete`)
# ---------------------------------------------------------------------------

class LaporanAkhir(BaseModel):
    request: AnalisisRequest
    data_collector: DataCollectorOutput
    insight: InsightOutput
    strategi: StrategyOutput


# ---------------------------------------------------------------------------
# Human-in-the-loop — keputusan manusia sebelum Strategy Agent dijalankan
# ---------------------------------------------------------------------------

class KeputusanHITL(BaseModel):
    disetujui: bool = Field(..., description="True = lanjut ke Strategy Agent, False = batalkan pipeline")
    catatan: Optional[str] = Field(None, max_length=200)
