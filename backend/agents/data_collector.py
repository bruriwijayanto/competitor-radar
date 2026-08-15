"""
Agent 1 — Data Collector.

Tanggung jawab tunggal: mengambil daftar kompetitor + sampel ulasan berdasarkan
lokasi, kategori, radius, dan top-N yang diminta pengguna.

Agent ini adalah Agno `Agent` sungguhan berbasis LLM (lewat OpenRouter) dengan SATU
tool yang dihubungkan lewat Model Context Protocol (MCP) — bukan panggilan API
langsung. Server MCP-nya ada di backend/mcp_server.py, di-spawn sebagai subprocess
terpisah lewat `agno.tools.mcp.MCPTools` (stdio transport). Agent yang memutuskan
KAPAN dan BAGAIMANA memanggil tool `cari_kompetitor` — termasuk keputusan untuk
mencoba ulang dengan radius lebih besar kalau hasil pertama kosong — itulah bukti
perilaku agentic (menyusun rencana, memilih tool, bertindak) yang tidak dimiliki
satu panggilan LLM biasa.

Output agent ini (DataCollectorOutput) adalah kontrak A2A yang akan dikonsumsi
langsung oleh Agent 2 (Sentiment & Insight) — lihat orchestrator.py.
"""
import asyncio
import json
import sys
from pathlib import Path

from agno.agent import Agent
from agno.models.openrouter import OpenRouter
from mcp import StdioServerParameters
from mcp.client.stdio import get_default_environment

from agno.tools.mcp import MCPTools

from ..config import settings
from ..schemas import AnalisisRequest, DataCollectorOutput, KompetitorRaw

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class DataCollectorAgent:
    name = "Data Collector Agent"

    def __init__(self) -> None:
        self.instructions = [
            "Kamu adalah agent pengumpul data kompetitor bisnis lokal di Indonesia.",
            "Kamu punya SATU tool bernama `cari_kompetitor` yang mengambil data nyata dari "
            "Google Maps Places API. Panggil tool itu dengan lokasi, kategori, radius_km, dan "
            "top_n persis seperti yang diminta pengguna.",
            "Kalau hasil `kompetitor` dari tool kosong, coba panggil ulang SEKALI dengan "
            "radius_km yang lebih besar (maksimum 5 km) sebelum menyerah.",
            "Jangan pernah mengarang atau menghalusinasi data kompetitor — laporkan hanya "
            "hasil yang benar-benar dikembalikan oleh tool.",
        ]

    def run(self, req: AnalisisRequest) -> DataCollectorOutput:
        return asyncio.run(self._run_async(req))

    async def _run_async(self, req: AnalisisRequest) -> DataCollectorOutput:
        env = {
            **get_default_environment(),
            "GOOGLE_MAPS_API_KEY": settings.GOOGLE_MAPS_API_KEY,
            "GOOGLE_API_DAILY_LIMIT": str(settings.GOOGLE_API_DAILY_LIMIT),
            "GOOGLE_API_MIN_INTERVAL_SECONDS": str(settings.GOOGLE_API_MIN_INTERVAL_SECONDS),
        }
        server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "backend.mcp_server"],
            env=env,
            cwd=str(PROJECT_ROOT),
        )

        async with MCPTools(server_params=server_params, transport="stdio") as mcp_tools:
            agent = Agent(
                name=self.name,
                model=OpenRouter(id=settings.OPENROUTER_MODEL, api_key=settings.OPENROUTER_API_KEY, max_tokens=1024),
                tools=[mcp_tools],
                instructions=self.instructions,
            )
            prompt = (
                f"Cari kompetitor kategori '{req.kategori.value}' di sekitar '{req.lokasi}', "
                f"radius awal {req.radius_km} km, ambil {req.top_n} kompetitor teratas. "
                "Gunakan tool cari_kompetitor untuk ini."
            )
            result = await agent.arun(prompt)

        tool_dict = self._ekstrak_hasil_tool(result)

        kompetitor = [KompetitorRaw(**k) for k in tool_dict["kompetitor"]]
        return DataCollectorOutput(
            lokasi=req.lokasi,
            kategori=req.kategori.value,
            radius_km=req.radius_km,
            sumber_data=tool_dict.get("sumber_data", "google_places"),
            kompetitor=kompetitor,
            total_ulasan_terkumpul=tool_dict.get("total_ulasan_terkumpul", sum(len(k.ulasan) for k in kompetitor)),
            pusat_lat=tool_dict.get("pusat_lat"),
            pusat_lng=tool_dict.get("pusat_lng"),
        )

    def _ekstrak_hasil_tool(self, result) -> dict:
        """Ambil hasil panggilan tool `cari_kompetitor` TERAKHIR yang sukses dari run
        agent — dipakai apa adanya (bukan hasil tulis-ulang LLM) supaya angka rating/
        jumlah review/koordinat presisi sama dengan yang dikembalikan Google API,
        tidak rawan salah transkripsi oleh model bahasa."""
        eksekusi_tool = list(result.tools or [])
        error_terakhir = None
        for eksekusi in reversed(eksekusi_tool):
            if "cari_kompetitor" not in (eksekusi.tool_name or ""):
                continue
            if eksekusi.tool_call_error:
                error_terakhir = eksekusi.result
                continue
            try:
                return json.loads(eksekusi.result)
            except (json.JSONDecodeError, TypeError) as exc:
                error_terakhir = f"Gagal parse hasil tool: {exc}"

        raise RuntimeError(
            "Data Collector Agent tidak berhasil mendapatkan data kompetitor dari tool "
            f"`cari_kompetitor`. Detail: {error_terakhir or 'tool tidak pernah dipanggil oleh agent'}"
        )
