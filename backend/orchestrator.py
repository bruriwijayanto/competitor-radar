"""
Orchestrator — mengoordinasi pipeline 3 agent (Agno) secara BERURUTAN dan memicu
event Server-Sent Events (SSE) di setiap transisi, supaya frontend bisa menampilkan
panel monitoring yang "hidup" secara real-time.

Pola ini menyerupai protokol Agent-to-Agent (A2A): output satu agent menjadi input
agent berikutnya, divalidasi lewat model Pydantic di backend/schemas.py. Titik-titik
handoff (A2A boundary) diberi komentar eksplisit di bawah supaya mudah dijelaskan
saat presentasi.

Antara Agent 2 dan Agent 3 ada titik HUMAN-IN-THE-LOOP wajib (lihat komentar "HITL
BOUNDARY" di bawah dan backend/approval_store.py) — pipeline berhenti dan menunggu
persetujuan manusia sebelum Strategy Agent menyusun rekomendasi akhir.

Generator ini sengaja berupa generator SINKRON (bukan async generator) karena agent
melakukan panggilan HTTP/LLM/MCP yang blocking, dan HITL menunggu (blocking wait)
keputusan manusia. Starlette otomatis menjalankan generator sinkron yang dikembalikan
oleh StreamingResponse di threadpool terpisah, sehingga tidak memblokir event loop
utama — request lain tetap bisa dilayani selagi satu pipeline menunggu approval.

Tidak ada fallback ke data palsu di mana pun (mode mock sudah dihapus): kalau satu
agent gagal, pipeline berhenti dan mengirim event `error` yang jelas — guardrail
"penanganan kegagalan" yang gagal secara terlihat, bukan diam-diam menyesatkan.
"""
import json
import time
from typing import Generator

from .agents import DataCollectorAgent, SentimentInsightAgent, StrategyAgent
from .agents.sentiment_insight import _agregasi_tema_pasar
from .approval_store import approval_store
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


def _kecualikan_kompetitor(
    data_out: DataCollectorOutput, insight_out: InsightOutput, dikecualikan: set[str]
) -> tuple[DataCollectorOutput, InsightOutput]:
    """Terapkan pilihan manusia di titik HITL: keluarkan kompetitor yang di-uncheck
    (mis. hasil pencarian yang tidak relevan/salah kategori) dari data yang diteruskan
    ke Strategy Agent DAN dari laporan akhir, supaya keduanya konsisten. Field agregat
    (total ulasan, ringkasan tema pasar) dihitung ulang dari sisa kompetitor yang dipilih."""
    kompetitor_baru = [k for k in data_out.kompetitor if k.nama not in dikecualikan]
    insight_baru = [k for k in insight_out.insight_kompetitor if k.nama not in dikecualikan]

    data_out = data_out.model_copy(
        update={
            "kompetitor": kompetitor_baru,
            "total_ulasan_terkumpul": sum(len(k.ulasan) for k in kompetitor_baru),
        }
    )
    insight_out = insight_out.model_copy(
        update={
            "insight_kompetitor": insight_baru,
            "ringkasan_tema_pasar": _agregasi_tema_pasar(insight_baru),
            "total_ulasan_dianalisis": sum(k.jumlah_ulasan_dianalisis for k in insight_baru),
        }
    )
    return data_out, insight_out


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

        # --- HITL BOUNDARY -----------------------------------------------------
        # Pipeline WAJIB berhenti di sini dan menunggu manusia meninjau hasil Data
        # Collector + Sentiment Insight sebelum Strategy Agent menyusun rekomendasi
        # bisnis final. Lihat justifikasi lengkap di backend/approval_store.py.
        run_id = approval_store.buat()
        yield _sse(
            "menunggu_persetujuan",
            {
                "run_id": run_id,
                "pesan": (
                    "Tinjau data kompetitor & insight sentimen di bawah. Hilangkan centang pada "
                    "kompetitor yang dianggap tidak relevan (mis. salah kategori/lokasi) supaya tidak "
                    "ikut dipertimbangkan, lalu setujui untuk melanjutkan ke Strategy Agent (menyusun "
                    "rekomendasi bisnis final), atau batalkan."
                ),
                "timeout_detik": settings.HITL_TIMEOUT_SECONDS,
                "preview": _preview_insight(insight_out, max_items=len(insight_out.insight_kompetitor)),
            },
        )

        keputusan = approval_store.tunggu(run_id, timeout=settings.HITL_TIMEOUT_SECONDS)
        if keputusan is None:
            yield _sse(
                "dibatalkan",
                {"alasan": f"Tidak ada keputusan manusia dalam {settings.HITL_TIMEOUT_SECONDS}s — pipeline dihentikan otomatis (guardrail timeout HITL)."},
            )
            return
        if not keputusan.disetujui:
            yield _sse("dibatalkan", {"alasan": "Pengguna menolak melanjutkan ke Strategy Agent."})
            return

        # Manusia bisa mengeluarkan kompetitor yang dianggap tidak relevan/salah
        # (mis. hasil pencarian yang salah kategori) sebelum data dipakai Strategy Agent.
        dikecualikan = set(keputusan.kompetitor_dikecualikan)
        if dikecualikan:
            jumlah_sebelum = len(insight_out.insight_kompetitor)
            data_out, insight_out = _kecualikan_kompetitor(data_out, insight_out, dikecualikan)
            if not insight_out.insight_kompetitor:
                yield _sse(
                    "error",
                    {"pesan": "Semua kompetitor dikeluarkan oleh pengguna — minimal 1 kompetitor harus dipertahankan agar Strategy Agent bisa jalan."},
                )
                return
            yield _sse(
                "disetujui",
                {
                    "pesan": (
                        f"Disetujui manusia — {len(dikecualikan)} kompetitor dikeluarkan dari pertimbangan "
                        f"({len(insight_out.insight_kompetitor)}/{jumlah_sebelum} dipertahankan). Melanjutkan ke Strategy Agent."
                    )
                },
            )
        else:
            yield _sse("disetujui", {"pesan": "Disetujui manusia — melanjutkan ke Strategy Agent."})
        time.sleep(JEDA_DETIK)
        # ------------------------------------------------------------------- /HITL

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
