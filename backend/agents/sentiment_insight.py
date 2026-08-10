"""
Agent 2 — Sentiment & Insight.

Tanggung jawab tunggal: menerima DataCollectorOutput (kontrak A2A dari Agent 1),
mengklasifikasi sentimen tiap ulasan, mengekstraksi tema pujian & keluhan
(harga, pelayanan, kebersihan, lokasi/parkir, kualitas produk), lalu merangkum
kekuatan & kelemahan tiap kompetitor.

- Mode mock: heuristik rating + keyword matching Bahasa Indonesia (tanpa LLM).
- Mode real: Agno Agent + LLM lewat OpenRouter dengan output_schema=InsightOutput.

Output agent ini (InsightOutput) adalah kontrak A2A yang dikonsumsi Agent 3 (Strategy).
"""
import json
from collections import Counter
from typing import Dict, List

from agno.agent import Agent

from ..config import settings
from ..schemas import (
    DataCollectorOutput,
    InsightKompetitor,
    InsightOutput,
    SentimenLabel,
    TemaUlasan,
    UlasanTerklasifikasi,
)

TEMA_KEYWORDS: Dict[TemaUlasan, List[str]] = {
    TemaUlasan.harga: ["harga", "mahal", "murah", "terjangkau", "biaya", "rp"],
    TemaUlasan.pelayanan: [
        "pelayanan", "layanan", "pelayan", "kapster", "montir", "dokter", "perawat",
        "resepsionis", "kasir", "sigap", "komunikatif", "jutek", "ramah", "tanggap", "staff", "karyawan",
    ],
    TemaUlasan.kebersihan: [
        "bersih", "kotor", "higienis", "rapi", "berantakan", "tercecer", "steril", "berserakan", "debu",
    ],
    TemaUlasan.lokasi_parkir: [
        "parkir", "lokasi", "strategis", "gang", "akses", "dekat", "jauh", "macet",
    ],
    TemaUlasan.kualitas_produk: [
        "rasa", "kualitas", "kopi", "menu", "produk", "hasil", "otentik", "awet", "spare part",
        "alat", "obat", "makanan", "potongan", "racikan", "sambel", "wifi",
    ],
}


class SentimentInsightAgent:
    name = "Sentiment & Insight Agent"

    def __init__(self) -> None:
        self.agent = Agent(
            name=self.name,
            instructions=[
                "Kamu adalah agent analisis sentimen & insight ulasan pelanggan bisnis lokal di Indonesia.",
                "Klasifikasikan tiap ulasan sebagai positif/negatif/netral dan identifikasi tema: "
                "harga, pelayanan, kebersihan, lokasi/parkir, kualitas produk.",
            ],
        )

    def run(self, data: DataCollectorOutput) -> InsightOutput:
        if settings.is_real_mode_requested and settings.has_openrouter_key:
            hasil = self._run_real(data)
            if hasil is not None:
                return hasil
        return self._run_mock(data)

    # ------------------------------------------------------------------
    # Mode mock: heuristik rating (sentimen) + keyword scan (tema)
    # ------------------------------------------------------------------

    def _klasifikasi_sentimen(self, rating: int) -> SentimenLabel:
        if rating >= 4:
            return SentimenLabel.positif
        if rating == 3:
            return SentimenLabel.netral
        return SentimenLabel.negatif

    def _ekstraksi_tema(self, teks: str) -> List[TemaUlasan]:
        teks_lower = teks.lower()
        tema_ditemukan = []
        for tema, keywords in TEMA_KEYWORDS.items():
            if any(kw in teks_lower for kw in keywords):
                tema_ditemukan.append(tema)
        return tema_ditemukan

    def _run_mock(self, data: DataCollectorOutput) -> InsightOutput:
        insight_list: List[InsightKompetitor] = []
        agregasi_pujian: Counter = Counter()
        agregasi_keluhan: Counter = Counter()
        total_ulasan_dianalisis = 0

        for kompetitor in data.kompetitor:
            ulasan_terklasifikasi: List[UlasanTerklasifikasi] = []
            counter_sentimen = Counter()
            tema_pujian_counter: Counter = Counter()
            tema_keluhan_counter: Counter = Counter()

            for ulasan in kompetitor.ulasan:
                sentimen = self._klasifikasi_sentimen(ulasan.rating)
                tema = self._ekstraksi_tema(ulasan.teks)
                ulasan_terklasifikasi.append(
                    UlasanTerklasifikasi(teks=ulasan.teks, sentimen=sentimen, tema=tema)
                )
                counter_sentimen[sentimen] += 1
                for t in tema:
                    if sentimen == SentimenLabel.positif:
                        tema_pujian_counter[t.value] += 1
                    elif sentimen == SentimenLabel.negatif:
                        tema_keluhan_counter[t.value] += 1

            n = len(kompetitor.ulasan) or 1
            persen_positif = round(counter_sentimen[SentimenLabel.positif] / n * 100, 1)
            persen_negatif = round(counter_sentimen[SentimenLabel.negatif] / n * 100, 1)
            persen_netral = round(counter_sentimen[SentimenLabel.netral] / n * 100, 1)

            tema_pujian = [t for t, _ in tema_pujian_counter.most_common(3)]
            tema_keluhan = [t for t, _ in tema_keluhan_counter.most_common(3)]

            kekuatan = [f"{t.capitalize()} dinilai baik oleh pelanggan" for t in tema_pujian] or [
                "Belum ada tema pujian yang menonjol dari sampel ulasan"
            ]
            kelemahan = [f"{t.capitalize()} masih dikeluhkan pelanggan" for t in tema_keluhan] or [
                "Belum ada tema keluhan yang menonjol dari sampel ulasan"
            ]

            agregasi_pujian.update(tema_pujian_counter)
            agregasi_keluhan.update(tema_keluhan_counter)
            total_ulasan_dianalisis += len(kompetitor.ulasan)

            insight_list.append(
                InsightKompetitor(
                    nama=kompetitor.nama,
                    rating=kompetitor.rating,
                    jumlah_review=kompetitor.jumlah_review,
                    rentang_harga=kompetitor.rentang_harga,
                    jumlah_ulasan_dianalisis=len(kompetitor.ulasan),
                    persentase_positif=persen_positif,
                    persentase_negatif=persen_negatif,
                    persentase_netral=persen_netral,
                    tema_pujian=tema_pujian,
                    tema_keluhan=tema_keluhan,
                    kekuatan=kekuatan,
                    kelemahan=kelemahan,
                    ulasan_terklasifikasi=ulasan_terklasifikasi,
                )
            )

        return InsightOutput(
            lokasi=data.lokasi,
            kategori=data.kategori,
            insight_kompetitor=insight_list,
            ringkasan_tema_pasar={
                "pujian": dict(agregasi_pujian.most_common()),
                "keluhan": dict(agregasi_keluhan.most_common()),
            },
            total_ulasan_dianalisis=total_ulasan_dianalisis,
        )

    # ------------------------------------------------------------------
    # Mode real: delegasikan analisis ke LLM lewat Agno Agent
    # ------------------------------------------------------------------

    def _run_real(self, data: DataCollectorOutput):
        from agno.models.openrouter import OpenRouter

        try:
            llm_agent = Agent(
                name=self.name,
                model=OpenRouter(id=settings.OPENROUTER_MODEL, api_key=settings.OPENROUTER_API_KEY),
                instructions=self.agent.instructions,
                output_schema=InsightOutput,
            )
            prompt = (
                "Analisis sentimen & insight untuk data kompetitor berikut (format JSON DataCollectorOutput). "
                "Kembalikan hasil sesuai schema InsightOutput, semua teks dalam Bahasa Indonesia.\n\n"
                f"{data.model_dump_json()}"
            )
            result = llm_agent.run(prompt)
            content = result.content
            if isinstance(content, InsightOutput):
                return content
            if isinstance(content, str):
                return InsightOutput.model_validate(json.loads(content))
            return InsightOutput.model_validate(content)
        except Exception:
            return None
