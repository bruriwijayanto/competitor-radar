"""
Agent 2 — Sentiment & Insight.

Tanggung jawab tunggal: menerima DataCollectorOutput (kontrak A2A dari Agent 1),
mengklasifikasi sentimen tiap ulasan, mengekstraksi tema pujian & keluhan
(harga, pelayanan, kebersihan, lokasi/parkir, kualitas produk), lalu merangkum
kekuatan & kelemahan tiap kompetitor.

Agent Agno sungguhan berbasis LLM lewat OpenRouter, dengan `output_schema` Pydantic
(InsightOutputLLM) supaya hasilnya terstruktur dan tervalidasi.

Output agent ini (InsightOutput) adalah kontrak A2A yang dikonsumsi Agent 3 (Strategy).
"""
import json
from collections import Counter
from typing import List

from agno.agent import Agent
from agno.models.openrouter import OpenRouter

from ..config import settings
from ..schemas import (
    DataCollectorOutput,
    InsightKompetitor,
    InsightOutput,
    InsightOutputLLM,
)


def _agregasi_tema_pasar(insight_kompetitor: List[InsightKompetitor]) -> dict:
    """Hitung ulang agregasi tema pujian/keluhan lintas kompetitor dari hasil LLM.

    Dilakukan di backend (bukan diminta ke LLM) karena field dict generik tidak
    kompatibel dengan structured output ketat OpenAI/OpenRouter — lihat
    schemas.InsightOutputLLM.
    """
    pujian: Counter = Counter()
    keluhan: Counter = Counter()
    for k in insight_kompetitor:
        for t in k.tema_pujian:
            pujian[t.value] += 1
        for t in k.tema_keluhan:
            keluhan[t.value] += 1
    return {"pujian": dict(pujian.most_common()), "keluhan": dict(keluhan.most_common())}


class SentimentInsightAgent:
    name = "Sentiment & Insight Agent"

    def __init__(self) -> None:
        self.agent = Agent(
            name=self.name,
            model=OpenRouter(
                id=settings.OPENROUTER_MODEL,
                api_key=settings.OPENROUTER_API_KEY,
                max_tokens=4096,  # default Agno (1024) gampang membuat JSON kepotong untuk banyak kompetitor
            ),
            instructions=[
                "Kamu adalah agent analisis sentimen & insight ulasan pelanggan bisnis lokal di Indonesia.",
                "Klasifikasikan tiap ulasan sebagai positif/negatif/netral dan identifikasi tema: "
                "harga, pelayanan, kebersihan, lokasi/parkir, kualitas produk.",
            ],
            output_schema=InsightOutputLLM,
        )

    def run(self, data: DataCollectorOutput) -> InsightOutput:
        prompt = (
            "Analisis sentimen & insight untuk data kompetitor berikut (format JSON DataCollectorOutput). "
            "Kembalikan hasil sesuai schema InsightOutputLLM, semua teks dalam Bahasa Indonesia.\n\n"
            f"{data.model_dump_json()}"
        )
        result = self.agent.run(prompt)
        content = result.content
        if isinstance(content, str):
            parsial = InsightOutputLLM.model_validate(json.loads(content))
        elif isinstance(content, InsightOutputLLM):
            parsial = content
        else:
            parsial = InsightOutputLLM.model_validate(content)

        # Lengkapi kembali jadi InsightKompetitor penuh (ulasan_terklasifikasi
        # sengaja kosong karena tidak diminta ke LLM — lihat InsightKompetitorLLM).
        insight_kompetitor = [
            InsightKompetitor(**k.model_dump(), ulasan_terklasifikasi=[]) for k in parsial.insight_kompetitor
        ]

        # ringkasan_tema_pasar & total_ulasan_dianalisis dihitung di backend, bukan
        # diminta ke LLM (lihat catatan di schemas.InsightOutputLLM).
        return InsightOutput(
            lokasi=parsial.lokasi,
            kategori=parsial.kategori,
            insight_kompetitor=insight_kompetitor,
            ringkasan_tema_pasar=_agregasi_tema_pasar(insight_kompetitor),
            total_ulasan_dianalisis=sum(k.jumlah_ulasan_dianalisis for k in insight_kompetitor),
        )
