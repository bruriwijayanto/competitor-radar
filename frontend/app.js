/**
 * Competitor Radar — frontend logic (jQuery + EventSource/SSE + Chart.js).
 * Tidak ada build step: file ini dipakai langsung oleh browser.
 */
$(function () {
  "use strict";

  const PIPELINE = ["Data Collector Agent", "Sentiment & Insight Agent", "Strategy Agent"];
  // Peta nama agent -> id elemen panah handoff yang menyala saat data dioper (A2A).
  const HANDOFF_ID_BY_FROM = {
    "Data Collector Agent": "handoff-1",
    "Sentiment & Insight Agent": "handoff-2",
  };

  let eventSource = null;
  let sentimentChart = null;
  const agentState = {}; // { [agentName]: { $node, $badge, $timer, timerInterval, startTime } }

  // ---------------------------------------------------------------- setup

  PIPELINE.forEach((name) => {
    const $node = $(`.agent-node[data-agent="${name}"]`);
    agentState[name] = {
      $node,
      $badge: $node.find("[data-status-badge]"),
      $timer: $node.find("[data-timer]"),
      timerInterval: null,
      startTime: null,
    };
  });

  fetchHealth();

  function fetchHealth() {
    $.getJSON("/api/health")
      .done((res) => {
        const $badge = $("#mode-badge");
        if (res.mode === "real") {
          $badge
            .removeClass("mode--mock")
            .addClass("mode--real")
            .html('<i class="fa-solid fa-plug-circle-check"></i> Mode REAL (Google Places + LLM)');
        } else {
          $badge
            .removeClass("mode--real")
            .addClass("mode--mock")
            .html('<i class="fa-solid fa-flask"></i> Mode MOCK (tanpa API key)');
        }
      })
      .fail(() => $("#mode-badge").text("Mode tidak diketahui"));
  }

  // ---------------------------------------------------------------- form controls

  $("#radius_km").on("input", function () {
    $("#radius-value").text($(this).val() + " km");
  });

  $("#top_n_group .segmented__option").on("click", function () {
    $("#top_n_group .segmented__option").removeClass("is-active");
    $(this).addClass("is-active");
    $("#top_n").val($(this).data("value"));
  });

  // ---------------------------------------------------------------- submit -> mulai pipeline

  $("#analysis-form").on("submit", function (e) {
    e.preventDefault();

    const params = {
      lokasi: $("#lokasi").val().trim(),
      kategori: $("#kategori").val(),
      radius_km: $("#radius_km").val(),
      top_n: $("#top_n").val(),
    };
    const namaUsaha = $("#nama_usaha").val().trim();
    if (namaUsaha) params.nama_usaha = namaUsaha;

    startPipeline(params);
  });

  function startPipeline(params) {
    if (eventSource) {
      eventSource.close();
    }

    // Reset UI monitoring
    $("#submit-btn").prop("disabled", true).html('<i class="fa-solid fa-spinner spin-icon"></i> Menjalankan…');
    $("#monitoring-section").prop("hidden", false);
    $("#result-section").prop("hidden", true);
    $("#monitor-subtitle").text("Menghubungkan ke pipeline…");
    $("#log-area").empty();
    $("#handoff-preview").prop("hidden", true);
    resetAgentNodes();

    $("html, body").animate({ scrollTop: $("#monitoring-section").offset().top - 20 }, 400);

    const qs = $.param(params);
    eventSource = new EventSource("/api/analisis/stream?" + qs);

    eventSource.addEventListener("start", (e) => {
      const data = JSON.parse(e.data);
      $("#monitor-subtitle").text("Pipeline berjalan — 3 agent akan bekerja berurutan.");
      appendLog("start", null, data.pesan);
    });

    eventSource.addEventListener("progress", (e) => {
      const data = JSON.parse(e.data);
      setAgentRunning(data.agent);
      appendLog("progress", data.agent, data.pesan);
    });

    eventSource.addEventListener("done", (e) => {
      const data = JSON.parse(e.data);
      setAgentDone(data.agent, data.durasi_detik);
      appendLog("done", data.agent, data.ringkasan);
    });

    // =====================================================================
    // A2A HANDOFF (frontend side): event `handoff` menandakan output satu
    // agent baru saja divalidasi Pydantic di backend dan dioper sebagai input
    // ke agent berikutnya. Di sini kita menyalakan panah pipeline yang sesuai
    // dan menampilkan preview payload JSON yang benar-benar dioper tersebut.
    // =====================================================================
    eventSource.addEventListener("handoff", (e) => {
      const data = JSON.parse(e.data);
      const handoffId = HANDOFF_ID_BY_FROM[data.dari];
      if (handoffId) {
        const $arrow = $("#" + handoffId);
        $arrow.addClass("is-active");
        setTimeout(() => $arrow.removeClass("is-active"), 2000);
      }

      $("#handoff-preview-title").text(`Payload Handoff: ${data.dari} → ${data.ke}`);
      $("#handoff-preview-json").text(JSON.stringify(data.preview, null, 2));
      $("#handoff-preview").prop("hidden", false).hide().fadeIn(200);

      appendLog("handoff", null, `Data dioper dari <b>${data.dari}</b> ke <b>${data.ke}</b> (kontrak A2A tervalidasi).`);
    });
    // ================================================================== /A2A

    eventSource.addEventListener("complete", (e) => {
      const laporan = JSON.parse(e.data);
      appendLog("complete", null, "Pipeline selesai. Laporan akhir siap ditampilkan.");
      $("#monitor-subtitle").text("Pipeline selesai — lihat hasil di bawah.");
      renderResult(laporan);
      finishSubmitButton();
      eventSource.close();
    });

    eventSource.addEventListener("error", (e) => {
      let pesan = "Koneksi ke server terputus atau terjadi kesalahan pada pipeline.";
      if (e.data) {
        try { pesan = JSON.parse(e.data).pesan || pesan; } catch (err) { /* biarkan pesan default */ }
      }
      appendLog("error", null, pesan);
      $("#monitor-subtitle").text("Pipeline berhenti karena kesalahan.");
      finishSubmitButton();
      if (eventSource) eventSource.close();
    });
  }

  function finishSubmitButton() {
    $("#submit-btn").prop("disabled", false).html('<i class="fa-solid fa-play"></i> Jalankan Analisis');
  }

  // ---------------------------------------------------------------- agent node state

  function resetAgentNodes() {
    PIPELINE.forEach((name) => {
      const st = agentState[name];
      clearInterval(st.timerInterval);
      st.timerInterval = null;
      st.startTime = null;
      st.$node.removeClass("is-running is-done");
      st.$badge.attr("class", "status-badge status-badge--idle").text("Idle");
      st.$timer.text("0.0s");
    });
    $(".handoff").removeClass("is-active");
  }

  function setAgentRunning(name) {
    const st = agentState[name];
    if (!st || st.$node.hasClass("is-running") || st.$node.hasClass("is-done")) return;
    st.$node.addClass("is-running");
    st.$badge.attr("class", "status-badge status-badge--running").html('<span class="spinner"></span> Berjalan');
    st.startTime = Date.now();
    st.timerInterval = setInterval(() => {
      const elapsed = ((Date.now() - st.startTime) / 1000).toFixed(1);
      st.$timer.text(elapsed + "s");
    }, 100);
  }

  function setAgentDone(name, durasiBackend) {
    const st = agentState[name];
    if (!st) return;
    clearInterval(st.timerInterval);
    st.timerInterval = null;
    st.$node.removeClass("is-running").addClass("is-done");
    st.$badge.attr("class", "status-badge status-badge--done").html('<i class="fa-solid fa-check"></i> Selesai');
    const elapsed = st.startTime ? ((Date.now() - st.startTime) / 1000).toFixed(1) : durasiBackend;
    st.$timer.text(elapsed + "s");
  }

  // ---------------------------------------------------------------- log

  const LOG_ICON = {
    start: '<i class="fa-solid fa-flag-checkered"></i>',
    progress: '<i class="fa-solid fa-gear"></i>',
    done: '<i class="fa-solid fa-circle-check"></i>',
    handoff: '<i class="fa-solid fa-right-left"></i>',
    complete: '<i class="fa-solid fa-trophy"></i>',
    error: '<i class="fa-solid fa-triangle-exclamation"></i>',
  };

  function appendLog(type, agent, message) {
    const time = new Date().toLocaleTimeString("id-ID", { hour12: false });
    const agentLabel = agent ? `<span class="log-entry__agent">[${agent}]</span> ` : "";
    const $entry = $(`
      <div class="log-entry log-entry--${type}">
        <span class="log-entry__time">${time}</span>
        <span class="log-entry__icon">${LOG_ICON[type] || ""}</span>
        <span class="log-entry__msg">${agentLabel}${message}</span>
      </div>
    `);
    const $area = $("#log-area");
    $area.append($entry);
    $area.scrollTop($area[0].scrollHeight);
  }

  // ---------------------------------------------------------------- render hasil

  function renderResult(laporan) {
    const { data_collector, insight, strategi } = laporan;

    $("#result-section").prop("hidden", false);
    $("#exec-summary-text").text(strategi.executive_summary);

    renderCompetitorTable(data_collector.kompetitor, insight.insight_kompetitor);
    renderSentimentChart(insight.ringkasan_tema_pasar);
    renderGapAnalysis(strategi.gap_analysis);
    renderRekomendasi(strategi.rekomendasi);

    $("#disclaimer-text").text(strategi.disclaimer);

    setTimeout(() => {
      $("html, body").animate({ scrollTop: $("#result-section").offset().top - 20 }, 500);
    }, 300);
  }

  function renderCompetitorTable(kompetitorList, insightList) {
    const insightByName = {};
    insightList.forEach((i) => (insightByName[i.nama] = i));

    const $body = $("#competitor-table-body").empty();
    kompetitorList.forEach((k) => {
      const insight = insightByName[k.nama] || {};
      const kekuatan = (insight.kekuatan || []).map((s) => `<li>${s}</li>`).join("");
      const kelemahan = (insight.kelemahan || []).map((s) => `<li>${s}</li>`).join("");

      const $row = $(`
        <tr>
          <td class="cell-name">${k.nama}<br><span style="font-weight:400;color:var(--text-faint);font-size:11.5px">${k.alamat}</span></td>
          <td><span class="rating-pill"><i class="fa-solid fa-star"></i> ${k.rating.toFixed(1)}</span></td>
          <td>${k.jumlah_review.toLocaleString("id-ID")}</td>
          <td>${k.rentang_harga}</td>
          <td><ul class="mini-list mini-list--strength">${kekuatan}</ul></td>
          <td><ul class="mini-list mini-list--weak">${kelemahan}</ul></td>
        </tr>
      `);
      $body.append($row);
    });
  }

  function renderSentimentChart(ringkasanTemaPasar) {
    const pujian = ringkasanTemaPasar.pujian || {};
    const keluhan = ringkasanTemaPasar.keluhan || {};
    const semuaTema = Array.from(new Set([...Object.keys(pujian), ...Object.keys(keluhan)]));

    const labels = semuaTema.length ? semuaTema : ["harga", "pelayanan", "kebersihan", "lokasi/parkir", "kualitas produk"];
    const dataPujian = labels.map((t) => pujian[t] || 0);
    const dataKeluhan = labels.map((t) => keluhan[t] || 0);

    const ctx = document.getElementById("sentiment-chart").getContext("2d");
    if (sentimentChart) sentimentChart.destroy();
    sentimentChart = new Chart(ctx, {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            label: "Pujian",
            data: dataPujian,
            backgroundColor: "#16a34a",
            borderRadius: 6,
            maxBarThickness: 34,
          },
          {
            label: "Keluhan",
            data: dataKeluhan,
            backgroundColor: "#dc2626",
            borderRadius: 6,
            maxBarThickness: 34,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: "top", labels: { usePointStyle: true, boxWidth: 8, font: { family: "Inter" } } },
          tooltip: { backgroundColor: "#1c2333", padding: 10, cornerRadius: 8 },
        },
        scales: {
          x: { grid: { display: false }, ticks: { font: { family: "Inter", size: 11.5 } } },
          y: { beginAtZero: true, ticks: { precision: 0, font: { family: "Inter" } }, grid: { color: "#e6e9f2" } },
        },
      },
    });
  }

  function renderGapAnalysis(gap) {
    const $celah = $("#gap-celah-list").empty();
    (gap.celah_pasar || []).forEach((s) => $celah.append(`<li>${s}</li>`));

    const $peluang = $("#gap-peluang-list").empty();
    (gap.peluang_diferensiasi || []).forEach((s) => $peluang.append(`<li>${s}</li>`));
  }

  function renderRekomendasi(list) {
    const urutanPrioritas = { tinggi: 0, sedang: 1, rendah: 2 };
    const sorted = [...list].sort((a, b) => urutanPrioritas[a.prioritas] - urutanPrioritas[b.prioritas]);

    const $container = $("#rekomendasi-list").empty();
    sorted.forEach((r) => {
      const $card = $(`
        <div class="rekomendasi-card">
          <div class="rekomendasi-card__top">
            <span class="rekomendasi-card__title">${r.judul}</span>
            <span class="priority-pill priority-pill--${r.prioritas}">${r.prioritas}</span>
          </div>
          <p class="rekomendasi-card__desc">${r.deskripsi}</p>
          <span class="category-tag">${r.kategori}</span>
        </div>
      `);
      $container.append($card);
    });
  }
});
