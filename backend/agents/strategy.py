"""
Agent 3 — Strategy.

Tanggung jawab tunggal: menerima InsightOutput (kontrak A2A dari Agent 2),
menghasilkan gap analysis (celah pasar yang belum dilayani baik) dan rekomendasi
strategis actionable (positioning, quick win, diferensiator).

Agent Agno sungguhan berbasis LLM lewat OpenRouter, dengan `output_schema` Pydantic
(StrategyOutput). Agent ini juga dilengkapi MEMORY persisten (agno.db.json.JsonDb):
sesi disimpan per kombinasi lokasi+kategori, jadi kalau pengguna menganalisis
bisnis yang sama lagi di lain waktu, agent mengingat rekomendasi sebelumnya dan bisa
membandingkan ("dibanding analisis sebelumnya, keluhan soal X sudah berkurang").

Output agent ini (StrategyOutput) adalah bagian akhir laporan yang dikirim ke frontend.
"""
import json
import re
from pathlib import Path
from typing import Optional

from agno.agent import Agent
from agno.db.json import JsonDb
from agno.models.openrouter import OpenRouter

from ..config import settings
from ..schemas import InsightOutput, StrategyOutput

MEMORY_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "agent_memory_db"
MEMORY_DB_PATH.mkdir(parents=True, exist_ok=True)


def _session_id_untuk(lokasi: str, kategori: str) -> str:
    """Session id deterministik dari lokasi+kategori supaya analisis berulang untuk
    bisnis yang sama berbagi riwayat/memory yang sama di agno.db.json.JsonDb."""
    slug = re.sub(r"[^a-z0-9]+", "-", f"{lokasi}-{kategori}".lower()).strip("-")
    return f"strategi-{slug}"


class StrategyAgent:
    name = "Strategy Agent"

    def __init__(self) -> None:
        self.db = JsonDb(db_path=str(MEMORY_DB_PATH))

    def run(self, insight: InsightOutput, nama_usaha: Optional[str] = None) -> StrategyOutput:
        session_id = _session_id_untuk(insight.lokasi, insight.kategori)

        agent = Agent(
            name=self.name,
            model=OpenRouter(id=settings.OPENROUTER_MODEL, api_key=settings.OPENROUTER_API_KEY, max_tokens=2048),
            instructions=[
                "Kamu adalah agent strategi bisnis yang menyusun gap analysis dan rekomendasi actionable "
                "berdasarkan insight sentimen kompetitor bisnis lokal di Indonesia.",
                "Semua output berbahasa Indonesia, ringkas, dan actionable.",
                "Kalau riwayat sesi menunjukkan kamu pernah menganalisis lokasi & kategori yang sama "
                "sebelumnya, bandingkan temuan sekarang dengan yang lalu secara singkat di executive_summary.",
            ],
            output_schema=StrategyOutput,
            db=self.db,
            session_id=session_id,
            add_history_to_context=True,
            num_history_runs=3,
        )

        prompt = (
            f"Nama usaha pengguna: {nama_usaha or 'tidak disebutkan'}.\n"
            "Susun gap analysis dan rekomendasi strategis berdasarkan insight kompetitor berikut "
            "(format JSON InsightOutput). Kembalikan hasil sesuai schema StrategyOutput, "
            "semua teks dalam Bahasa Indonesia dan actionable.\n\n"
            f"{insight.model_dump_json()}"
        )
        result = agent.run(prompt, session_id=session_id)
        content = result.content
        if isinstance(content, StrategyOutput):
            return content
        if isinstance(content, str):
            return StrategyOutput.model_validate(json.loads(content))
        return StrategyOutput.model_validate(content)
