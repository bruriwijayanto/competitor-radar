"""
Agent 3 — Strategy.

Tanggung jawab tunggal: menerima InsightOutput (kontrak A2A dari Agent 2),
menghasilkan gap analysis (celah pasar yang belum dilayani baik) dan rekomendasi
strategis actionable (positioning, quick win, diferensiator).

- Mode mock: heuristik berbasis agregasi tema pujian/keluhan lintas kompetitor.
- Mode real: Agno Agent + LLM lewat OpenRouter dengan output_schema=StrategyOutput.

Output agent ini (StrategyOutput) adalah bagian akhir laporan yang dikirim ke frontend.
"""
import json
from typing import List

from agno.agent import Agent

from ..config import settings
from ..schemas import (
    GapAnalysis,
    InsightOutput,
    PrioritasRekomendasi,
    Rekomendasi,
    StrategyOutput,
)

TEMA_AKSI = {
    "harga": {
        "quick_win": "Tinjau ulang strategi harga — pertimbangkan paket hemat atau promo bundling untuk pelanggan yang sensitif harga.",
        "diferensiator": "Tawarkan proposisi 'value for money' yang jelas dan terukur dibanding kompetitor yang dinilai mahal.",
        "positioning": "harga yang lebih bersahabat tanpa mengorbankan kualitas",
    },
    "pelayanan": {
        "quick_win": "Latih staf agar respons ke pelanggan lebih cepat dan ramah, terutama saat jam sibuk.",
        "diferensiator": "Bangun budaya layanan personal (mengenali pelanggan tetap, sapaan hangat) sebagai pembeda utama.",
        "positioning": "kualitas pelayanan yang lebih hangat dan responsif",
    },
    "kebersihan": {
        "quick_win": "Tingkatkan frekuensi pembersihan area pelanggan (meja, lantai, toilet) terutama di jam ramai.",
        "diferensiator": "Jadikan standar kebersihan sebagai bagian dari branding, misalnya lewat badge/sertifikasi higienis yang terlihat pelanggan.",
        "positioning": "standar kebersihan dan kenyamanan tempat yang lebih terjaga",
    },
    "lokasi/parkir": {
        "quick_win": "Sediakan penataan parkir tambahan di jam ramai atau kerja sama lahan parkir terdekat.",
        "diferensiator": "Promosikan kemudahan akses dan ketersediaan parkir sebagai keunggulan dibanding kompetitor di area padat.",
        "positioning": "kemudahan akses dan kenyamanan parkir",
    },
    "kualitas produk": {
        "quick_win": "Lakukan quality control rutin agar konsistensi rasa/hasil produk terjaga di setiap kunjungan.",
        "diferensiator": "Kembangkan menu atau layanan signature yang unik dan sulit ditiru kompetitor sekitar.",
        "positioning": "kualitas produk yang lebih konsisten dan khas",
    },
}


class StrategyAgent:
    name = "Strategy Agent"

    def __init__(self) -> None:
        self.agent = Agent(
            name=self.name,
            instructions=[
                "Kamu adalah agent strategi bisnis yang menyusun gap analysis dan rekomendasi actionable "
                "berdasarkan insight sentimen kompetitor bisnis lokal di Indonesia.",
                "Semua output berbahasa Indonesia, ringkas, dan actionable.",
            ],
        )

    def run(self, insight: InsightOutput, nama_usaha: str | None = None) -> StrategyOutput:
        if settings.is_real_mode_requested and settings.has_openrouter_key:
            hasil = self._run_real(insight, nama_usaha)
            if hasil is not None:
                return hasil
        return self._run_mock(insight, nama_usaha)

    # ------------------------------------------------------------------
    # Mode mock: heuristik agregasi tema pujian/keluhan pasar
    # ------------------------------------------------------------------

    def _run_mock(self, insight: InsightOutput, nama_usaha: str | None) -> StrategyOutput:
        keluhan_pasar = insight.ringkasan_tema_pasar.get("keluhan", {})
        pujian_pasar = insight.ringkasan_tema_pasar.get("pujian", {})

        top_keluhan: List[str] = sorted(keluhan_pasar, key=lambda k: keluhan_pasar[k], reverse=True)[:3]
        top_pujian: List[str] = sorted(pujian_pasar, key=lambda k: pujian_pasar[k], reverse=True)

        # Celah pasar: tema yang paling sering dikeluhkan lintas kompetitor -> belum dilayani dengan baik.
        celah_pasar = [
            f"Mayoritas kompetitor di {insight.lokasi} masih dikeluhkan soal {tema} — celah yang bisa dimanfaatkan pemain baru."
            for tema in top_keluhan
        ] or [f"Belum ada celah keluhan yang menonjol dari sampel ulasan di {insight.lokasi}."]

        # Peluang diferensiasi: tema pujian yang paling jarang muncul -> baru sedikit kompetitor yang unggul di sana.
        tema_semua = list(TEMA_AKSI.keys())
        tema_jarang_dipuji = [t for t in tema_semua if t not in top_pujian[:2]]
        peluang_diferensiasi = [
            TEMA_AKSI[t]["diferensiator"] for t in tema_jarang_dipuji[:3] if t in TEMA_AKSI
        ] or [TEMA_AKSI[t]["diferensiator"] for t in tema_semua[:2]]

        gap_analysis = GapAnalysis(celah_pasar=celah_pasar, peluang_diferensiasi=peluang_diferensiasi)

        # Rekomendasi: quick win dari top keluhan (prioritas tinggi), diferensiator (sedang), positioning (tinggi/sedang).
        rekomendasi: List[Rekomendasi] = []
        for i, tema in enumerate(top_keluhan):
            aksi = TEMA_AKSI.get(tema)
            if not aksi:
                continue
            rekomendasi.append(
                Rekomendasi(
                    judul=f"Perbaiki {tema} secepatnya",
                    deskripsi=aksi["quick_win"],
                    prioritas=PrioritasRekomendasi.tinggi if i == 0 else PrioritasRekomendasi.sedang,
                    kategori="quick win",
                )
            )

        for tema in tema_jarang_dipuji[:2]:
            aksi = TEMA_AKSI.get(tema)
            if not aksi:
                continue
            rekomendasi.append(
                Rekomendasi(
                    judul=f"Jadikan {tema} sebagai diferensiator",
                    deskripsi=aksi["diferensiator"],
                    prioritas=PrioritasRekomendasi.sedang,
                    kategori="diferensiator",
                )
            )

        positioning_tema = top_keluhan[0] if top_keluhan else tema_semua[0]
        positioning_frasa = TEMA_AKSI.get(positioning_tema, TEMA_AKSI["kualitas produk"])["positioning"]
        nama = nama_usaha or "usaha Anda"
        rekomendasi.insert(
            0,
            Rekomendasi(
                judul="Posisikan sebagai alternatif yang lebih unggul",
                deskripsi=f"Posisikan {nama} sebagai pilihan dengan {positioning_frasa} dibanding kompetitor di {insight.lokasi}.",
                prioritas=PrioritasRekomendasi.tinggi,
                kategori="positioning",
            ),
        )

        jumlah_kompetitor = len(insight.insight_kompetitor)
        rata_rating = (
            round(sum(k.rating for k in insight.insight_kompetitor) / jumlah_kompetitor, 2)
            if jumlah_kompetitor
            else 0
        )
        executive_summary = (
            f"Analisis terhadap {jumlah_kompetitor} kompetitor {insight.kategori} di {insight.lokasi} "
            f"menunjukkan rata-rata rating {rata_rating} dari ulasan sampel yang dikumpulkan. "
            + (
                f"Tema yang paling sering dikeluhkan pelanggan adalah {', '.join(top_keluhan)}, "
                if top_keluhan
                else "Tidak ada tema keluhan yang menonjol dari sampel ulasan, "
            )
            + (
                f"sementara {', '.join(top_pujian[:2])} menjadi kekuatan yang paling sering dipuji. "
                if top_pujian
                else "namun variasi kekuatan antar kompetitor masih cukup merata. "
            )
            + f"Peluang terbesar bagi {nama} adalah menutup celah tersebut sambil membangun diferensiasi yang jelas."
        )

        disclaimer = (
            f"Berdasarkan {insight.total_ulasan_dianalisis} ulasan sampel dari {jumlah_kompetitor} kompetitor "
            f"di {insight.lokasi}. Hasil bersifat indikatif untuk demonstrasi akademik, bukan riset pasar formal."
        )

        return StrategyOutput(
            executive_summary=executive_summary,
            gap_analysis=gap_analysis,
            rekomendasi=rekomendasi,
            disclaimer=disclaimer,
        )

    # ------------------------------------------------------------------
    # Mode real: delegasikan penyusunan strategi ke LLM lewat Agno Agent
    # ------------------------------------------------------------------

    def _run_real(self, insight: InsightOutput, nama_usaha: str | None):
        from agno.models.openrouter import OpenRouter

        try:
            llm_agent = Agent(
                name=self.name,
                model=OpenRouter(id=settings.OPENROUTER_MODEL, api_key=settings.OPENROUTER_API_KEY, max_tokens=2048),
                instructions=self.agent.instructions,
                output_schema=StrategyOutput,
            )
            prompt = (
                f"Nama usaha pengguna: {nama_usaha or 'tidak disebutkan'}.\n"
                "Susun gap analysis dan rekomendasi strategis berdasarkan insight kompetitor berikut "
                "(format JSON InsightOutput). Kembalikan hasil sesuai schema StrategyOutput, "
                "semua teks dalam Bahasa Indonesia dan actionable.\n\n"
                f"{insight.model_dump_json()}"
            )
            result = llm_agent.run(prompt)
            content = result.content
            if isinstance(content, StrategyOutput):
                return content
            if isinstance(content, str):
                return StrategyOutput.model_validate(json.loads(content))
            return StrategyOutput.model_validate(content)
        except Exception:
            return None
