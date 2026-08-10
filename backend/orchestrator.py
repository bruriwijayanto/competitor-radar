"""
Orchestrator — mengoordinasi pipeline 3 agent (Agno) secara BERURUTAN dan memicu
event Server-Sent Events (SSE) di setiap transisi, supaya frontend bisa menampilkan
panel monitoring yang "hidup" secara real-time.

Pola ini menyerupai protokol Agent-to-Agent (A2A): output satu agent menjadi input
agent berikutnya, divalidasi lewat model Pydantic di backend/schemas.py. Titik-titik
handoff (A2A boundary) diberi komentar eksplisit di bawah supaya mudah dijelaskan
saat presentasi.

Generator ini sengaja berupa generator SINKRON (bukan async generator) karena agent
di mode `real` melakukan panggilan HTTP/LLM yang blocking. Starlette otomatis
menjalankan generator sinkron yang dikembalikan oleh StreamingResponse di threadpool
terpisah, sehingga tidak memblokir event loop.
"""
import json
import time
from typing import Generator

from .agents import DataCollectorAgent, SentimentInsightAgent, StrategyAgent
from .config import settings
from .schemas import AnalisisRequest, DataCollectorOutput, InsightOutput, LaporanAkhir

PIPELINE_NAMES = ["Data Collector Agent", "Sentiment & Insight Agent", "Strategy Agent"]

# Jeda kecil antar-langkah supaya panel monitoring terasa hidup (bukan meledak sekaligus).
JEDA_DETIK = 0.55


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _preview_data_collector(out: DataCollectorOutput, max_items: int = 2) -> dict:
    """Preview payload A2A #1 (Agent 1 -> Agent 2), dipangkas agar ringkas di log UI."""
    contoh = [k.model_dump(mode="json") for k in out.kompetitor[:max_items]]
    return {
        "lokasi": out.lokasi,
        "kategori": out.kategori,
        "sumber_data": out.sumber_data,
        "jumlah_kompetitor": len(out.kompetitor),
        "total_ulasan_terkumpul": out.total_ulasan_terkumpul,
        "contoh_kompetitor": contoh,
        "catatan": (
            f"+{len(out.kompetitor) - max_items} kompetitor lainnya tidak ditampilkan di preview"
            if len(out.kompetitor) > max_items
            else None
        ),
    }


def _preview_insight(out: InsightOutput, max_items: int = 2) -> dict:
    """Preview payload A2A #2 (Agent 2 -> Agent 3), dipangkas agar ringkas di log UI."""
    contoh = [
        {
            "nama": k.nama,
            "persentase_positif": k.persentase_positif,
            "persentase_negatif": k.persentase_negatif,
            "tema_pujian": k.tema_pujian,
            "tema_keluhan": k.tema_keluhan,
        }
        for k in out.insight_kompetitor[:max_items]
    ]
    return {
        "lokasi": out.lokasi,
        "kategori": out.kategori,
        "total_ulasan_dianalisis": out.total_ulasan_dianalisis,
        "ringkasan_tema_pasar": out.ringkasan_tema_pasar,
        "contoh_insight_kompetitor": contoh,
        "catatan": (
            f"+{len(out.insight_kompetitor) - max_items} kompetitor lainnya tidak ditampilkan di preview"
            if len(out.insight_kompetitor) > max_items
            else None
        ),
    }


def run_pipeline_sse(req: AnalisisRequest) -> Generator[str, None, None]:
    collector = DataCollectorAgent()
    insight_agent = SentimentInsightAgent()
    strategy_agent = StrategyAgent()

    try:
        yield _sse(
            "start",
            {
                "pesan": "Pipeline analisis kompetitor dimulai.",
                "pipeline": PIPELINE_NAMES,
                "mode": settings.APP_MODE,
                "request": json.loads(req.model_dump_json()),
            },
        )
        time.sleep(JEDA_DETIK)

        # ==================================================================
        # AGENT 1 — Data Collector
        # ==================================================================
        yield _sse("progress", {"agent": collector.name, "pesan": f"Mencari kompetitor kategori '{req.kategori.value}' di sekitar {req.lokasi} (radius {req.radius_km} km)..."})
        time.sleep(JEDA_DETIK)
        yield _sse("progress", {"agent": collector.name, "pesan": f"Mengumpulkan sampel ulasan untuk top-{req.top_n} kompetitor..."})

        t0 = time.time()
        data_out = collector.run(req)
        durasi1 = round(time.time() - t0, 2)

        yield _sse(
            "done",
            {
                "agent": collector.name,
                "durasi_detik": durasi1,
                "ringkasan": (
                    f"Ditemukan {len(data_out.kompetitor)} kompetitor dengan total "
                    f"{data_out.total_ulasan_terkumpul} ulasan terkumpul (sumber: {data_out.sumber_data})."
                ),
            },
        )
        time.sleep(JEDA_DETIK)

        # --- A2A BOUNDARY #1 -------------------------------------------------
        # Output Agent 1 (DataCollectorOutput) divalidasi Pydantic dan menjadi
        # input langsung Agent 2. Ini "handoff" ala Agent-to-Agent protocol.
        yield _sse(
            "handoff",
            {
                "dari": collector.name,
                "ke": insight_agent.name,
                "preview": _preview_data_collector(data_out),
            },
        )
        time.sleep(JEDA_DETIK)
        # ----------------------------------------------------------------------

        # ==================================================================
        # AGENT 2 — Sentiment & Insight
        # ==================================================================
        yield _sse("progress", {"agent": insight_agent.name, "pesan": "Mengklasifikasikan sentimen tiap ulasan (positif/negatif/netral)..."})
        time.sleep(JEDA_DETIK)
        yield _sse("progress", {"agent": insight_agent.name, "pesan": "Mengekstraksi tema pujian & keluhan: harga, pelayanan, kebersihan, lokasi/parkir, kualitas produk..."})

        t1 = time.time()
        insight_out = insight_agent.run(data_out)  # <- data_out (output Agent 1) langsung jadi input Agent 2
        durasi2 = round(time.time() - t1, 2)

        yield _sse(
            "done",
            {
                "agent": insight_agent.name,
                "durasi_detik": durasi2,
                "ringkasan": f"{insight_out.total_ulasan_dianalisis} ulasan berhasil dianalisis di {len(insight_out.insight_kompetitor)} kompetitor.",
            },
        )
        time.sleep(JEDA_DETIK)

        # --- A2A BOUNDARY #2 -------------------------------------------------
        # Output Agent 2 (InsightOutput) divalidasi Pydantic dan menjadi input Agent 3.
        yield _sse(
            "handoff",
            {
                "dari": insight_agent.name,
                "ke": strategy_agent.name,
                "preview": _preview_insight(insight_out),
            },
        )
        time.sleep(JEDA_DETIK)
        # ----------------------------------------------------------------------

        # ==================================================================
        # AGENT 3 — Strategy
        # ==================================================================
        yield _sse("progress", {"agent": strategy_agent.name, "pesan": "Menyusun gap analysis dari pola keluhan lintas kompetitor..."})
        time.sleep(JEDA_DETIK)
        yield _sse("progress", {"agent": strategy_agent.name, "pesan": "Merumuskan rekomendasi strategis (positioning, quick win, diferensiator)..."})

        t2 = time.time()
        strategy_out = strategy_agent.run(insight_out, req.nama_usaha)  # <- insight_out (output Agent 2) langsung jadi input Agent 3
        durasi3 = round(time.time() - t2, 2)

        yield _sse(
            "done",
            {
                "agent": strategy_agent.name,
                "durasi_detik": durasi3,
                "ringkasan": f"{len(strategy_out.rekomendasi)} rekomendasi strategis berhasil disusun.",
            },
        )
        time.sleep(JEDA_DETIK)

        # ==================================================================
        # SELESAI — kirim laporan akhir gabungan ke frontend
        # ==================================================================
        laporan = LaporanAkhir(request=req, data_collector=data_out, insight=insight_out, strategi=strategy_out)
        yield _sse("complete", json.loads(laporan.model_dump_json()))

    except Exception as exc:  # pragma: no cover - jaring pengaman demo
        yield _sse("error", {"pesan": f"Terjadi kesalahan pada pipeline: {exc}"})
