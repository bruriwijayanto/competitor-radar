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

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request dari frontend
# ---------------------------------------------------------------------------

class KategoriUsaha(str, Enum):
    coffee_shop = "coffee shop"
    restoran = "restoran"
    salon = "salon"
    bengkel = "bengkel"
    klinik = "klinik"


class AnalisisRequest(BaseModel):
    nama_usaha: Optional[str] = Field(None, description="Nama usaha pengguna (opsional)")
    lokasi: str = Field(..., description="Lokasi/area yang dianalisis, mis. 'Dago, Bandung'")
    kategori: KategoriUsaha = Field(..., description="Kategori usaha yang dianalisis")
    radius_km: float = Field(2.0, ge=1, le=5, description="Radius pencarian kompetitor (km)")
    top_n: int = Field(5, description="Jumlah kompetitor teratas yang dianalisis (5 atau 10)")


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
    lat: Optional[float] = Field(None, description="Koordinat lintang (sintetis pada mode mock)")
    lng: Optional[float] = Field(None, description="Koordinat bujur (sintetis pada mode mock)")


class DataCollectorOutput(BaseModel):
    """Output Agent 1 -> menjadi input Agent 2 (batas A2A #1)."""
    lokasi: str
    kategori: str
    radius_km: float
    sumber_data: str = Field(..., description="'mock' atau 'google_places'")
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
    tema_pujian: List[str] = Field(default_factory=list, description="Tema yang paling sering dipuji")
    tema_keluhan: List[str] = Field(default_factory=list, description="Tema yang paling sering dikeluhkan")
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
