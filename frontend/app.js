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
  let currentRunId = null;
  let sentimentChart = null;
  let googleMap = null;
  let googleMapsLoadPromise = null;
  let leafletMap = null;
  let mapsApiKey = null; // diisi dari /api/maps-key sekali di awal
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
  fetchMapsKey();

  function fetchMapsKey() {
    $.getJSON("/api/maps-key")
      .done((res) => { mapsApiKey = res.key || null; })
      .fail(() => { mapsApiKey = null; });
  }

  function fetchHealth() {
    $.getJSON("/api/health")
      .done((res) => {
        const $badge = $("#mode-badge");
        if (res.google_maps_key_terpasang && res.openrouter_key_terpasang) {
          $badge
            .removeClass("mode--mock")
            .addClass("mode--real")
            .html('<i class="fa-solid fa-plug-circle-check"></i> Agentic • MCP (Google Places) • LLM (OpenRouter)');
        } else {
          $badge
            .removeClass("mode--real")
            .addClass("mode--mock")
            .html('<i class="fa-solid fa-triangle-exclamation"></i> Konfigurasi API key belum lengkap');
        }
      })
      .fail(() => $("#mode-badge").text("Status tidak diketahui"));
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
    $("#hitl-panel").prop("hidden", true);
    currentRunId = null;
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

    // =====================================================================
    // HUMAN-IN-THE-LOOP: pipeline berhenti di sini menunggu persetujuan
    // manusia sebelum Strategy Agent menyusun rekomendasi bisnis final.
    // =====================================================================
    eventSource.addEventListener("menunggu_persetujuan", (e) => {
      const data = JSON.parse(e.data);
      currentRunId = data.run_id;
      appendLog("handoff", null, `<b>Menunggu persetujuan manusia</b> sebelum lanjut ke Strategy Agent (batas ${data.timeout_detik}s).`);
      $("#monitor-subtitle").text("Pipeline dijeda — menunggu keputusan Anda.");
      renderHitlPreview(data.preview);
      $("#hitl-panel-desc").text(data.pesan);
      $("#hitl-panel").prop("hidden", false).hide().fadeIn(200);
      $("#hitl-approve-btn, #hitl-reject-btn").prop("disabled", false);
      $("html, body").animate({ scrollTop: $("#hitl-panel").offset().top - 20 }, 400);
    });

    eventSource.addEventListener("disetujui", (e) => {
      const data = JSON.parse(e.data);
      $("#hitl-panel").fadeOut(200, function () { $(this).prop("hidden", true); });
      appendLog("done", null, data.pesan);
    });

    eventSource.addEventListener("dibatalkan", (e) => {
      const data = JSON.parse(e.data);
      $("#hitl-panel").fadeOut(200, function () { $(this).prop("hidden", true); });
      appendLog("error", null, `Pipeline dibatalkan: ${data.alasan}`);
      $("#monitor-subtitle").text("Pipeline dibatalkan.");
      finishSubmitButton();
      if (eventSource) eventSource.close();
    });
    // ================================================================== /HITL

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

  // ---------------------------------------------------------------- human-in-the-loop

  function renderHitlPreview(preview) {
    const $box = $("#hitl-panel-preview").empty();
    (preview.contoh_insight_kompetitor || []).forEach((k) => {
      $box.append(`
        <div class="hitl-preview-row">
          <span class="hitl-preview-row__name">${k.nama}</span>
          <span class="hitl-preview-row__stat"><i class="fa-solid fa-thumbs-up" style="color:var(--green)"></i> ${k.persentase_positif}%</span>
          <span class="hitl-preview-row__stat"><i class="fa-solid fa-thumbs-down" style="color:var(--red)"></i> ${k.persentase_negatif}%</span>
        </div>
      `);
    });
  }

  function kirimKeputusanHitl(disetujui) {
    if (!currentRunId) return;
    $("#hitl-approve-btn, #hitl-reject-btn").prop("disabled", true);
    $.ajax({
      url: `/api/analisis/${currentRunId}/keputusan`,
      method: "POST",
      contentType: "application/json",
      data: JSON.stringify({ disetujui }),
    }).fail(() => {
      appendLog("error", null, "Gagal mengirim keputusan ke server. Coba lagi.");
      $("#hitl-approve-btn, #hitl-reject-btn").prop("disabled", false);
    });
  }

  $("#hitl-approve-btn").on("click", () => kirimKeputusanHitl(true));
  $("#hitl-reject-btn").on("click", () => kirimKeputusanHitl(false));

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
    renderCompetitorMap(data_collector);
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
          <td class="cell-name">
            <a class="competitor-link" href="${googleMapsUrl(k)}" target="_blank" rel="noopener noreferrer">${k.nama} <i class="fa-solid fa-arrow-up-right-from-square"></i></a>
            <br><span style="font-weight:400;color:var(--text-faint);font-size:11.5px">${k.alamat}</span>
          </td>
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

  // ---------------------------------------------------------------- peta sebaran kompetitor

  // Tautan ke halaman Google Maps (termasuk ulasannya) untuk satu kompetitor.
  // place_id selalu tersedia (data selalu dari Google Places), fallback pencarian
  // nama+alamat cuma jaga-jaga kalau field itu kosong.
  function googleMapsUrl(k) {
    if (k.place_id) {
      return `https://www.google.com/maps/place/?q=place_id:${encodeURIComponent(k.place_id)}`;
    }
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(k.nama + ", " + k.alamat)}`;
  }

  function ratingTier(rating) {
    if (rating >= 4.5) return "high";
    if (rating >= 3.5) return "mid";
    return "low";
  }

  const TIER_COLOR = { high: "#16a34a", mid: "#d97706", low: "#dc2626" };

  function renderCompetitorMap(dataCollector) {
    const $note = $("#map-source-note");
    const punyaKoordinat = dataCollector.pusat_lat != null && dataCollector.pusat_lng != null;

    if (!punyaKoordinat) {
      $("#competitor-map").html('<div style="padding:20px;color:var(--text-faint);font-size:13px;">Koordinat tidak tersedia untuk lokasi ini.</div>');
      $note.text("");
      return;
    }

    if (mapsApiKey) {
      $note.html('<i class="fa-solid fa-circle-check" style="color:var(--green)"></i> Google Maps aktif');
      loadGoogleMaps(mapsApiKey)
        .then(() => renderGoogleMap(dataCollector))
        .catch(() => renderLeafletMap(dataCollector)); // gagal load Maps JS -> tetap tampil via peta gratis
    } else {
      $note.html('<i class="fa-solid fa-map"></i> Peta OpenStreetMap (gratis, tanpa API key)');
      renderLeafletMap(dataCollector);
    }
  }

  function loadGoogleMaps(key) {
    if (window.google && window.google.maps) return Promise.resolve();
    if (googleMapsLoadPromise) return googleMapsLoadPromise;

    googleMapsLoadPromise = new Promise((resolve, reject) => {
      window.__onGoogleMapsLoaded = () => resolve();
      const script = document.createElement("script");
      script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&callback=__onGoogleMapsLoaded`;
      script.async = true;
      script.onerror = () => reject(new Error("Gagal memuat Google Maps JavaScript API"));
      document.head.appendChild(script);
    });
    return googleMapsLoadPromise;
  }

  function renderGoogleMap(dataCollector) {
    $("#competitor-map").empty();
    const pusat = { lat: dataCollector.pusat_lat, lng: dataCollector.pusat_lng };
    const zoomByRadius = { 1: 15, 2: 14, 3: 13, 4: 13, 5: 12 };

    googleMap = new google.maps.Map(document.getElementById("competitor-map"), {
      center: pusat,
      zoom: zoomByRadius[Math.round(dataCollector.radius_km)] || 13,
      disableDefaultUI: true,
      zoomControl: true,
      styles: [{ featureType: "poi", elementType: "labels", stylers: [{ visibility: "off" }] }],
    });

    new google.maps.Marker({
      position: pusat,
      map: googleMap,
      title: "Titik pusat pencarian",
      icon: { path: google.maps.SymbolPath.CIRCLE, scale: 8, fillColor: "#4f5df7", fillOpacity: 1, strokeColor: "#fff", strokeWeight: 2 },
    });

    new google.maps.Circle({
      map: googleMap,
      center: pusat,
      radius: dataCollector.radius_km * 1000,
      fillColor: "#4f5df7",
      fillOpacity: 0.06,
      strokeColor: "#4f5df7",
      strokeOpacity: 0.4,
      strokeWeight: 1.5,
    });

    const infoWindow = new google.maps.InfoWindow();
    dataCollector.kompetitor.forEach((k) => {
      if (k.lat == null || k.lng == null) return;
      const marker = new google.maps.Marker({
        position: { lat: k.lat, lng: k.lng },
        map: googleMap,
        title: k.nama,
        icon: {
          path: google.maps.SymbolPath.CIRCLE,
          scale: 8,
          fillColor: TIER_COLOR[ratingTier(k.rating)],
          fillOpacity: 1,
          strokeColor: "#fff",
          strokeWeight: 2,
        },
      });
      marker.addListener("click", () => {
        infoWindow.setContent(competitorInfoHtml(k));
        infoWindow.open(googleMap, marker);
        showSelectedInfo(k);
      });
    });
  }

  function renderLeafletMap(dataCollector) {
    $("#competitor-map").empty();
    if (leafletMap) {
      leafletMap.remove(); // buang instance peta lama sebelum re-render (Leaflet tidak bisa init dobel di container yang sama)
      leafletMap = null;
    }

    const pusat = [dataCollector.pusat_lat, dataCollector.pusat_lng];
    const zoomByRadius = { 1: 15, 2: 14, 3: 13, 4: 13, 5: 12 };

    leafletMap = L.map("competitor-map", { scrollWheelZoom: false }).setView(
      pusat,
      zoomByRadius[Math.round(dataCollector.radius_km)] || 13
    );

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(leafletMap);

    L.circleMarker(pusat, { radius: 9, weight: 2, color: "#fff", fillColor: "#4f5df7", fillOpacity: 1 })
      .addTo(leafletMap)
      .bindTooltip("Titik pusat pencarian");

    L.circle(pusat, {
      radius: dataCollector.radius_km * 1000,
      weight: 1.5,
      color: "#4f5df7",
      fillColor: "#4f5df7",
      fillOpacity: 0.06,
    }).addTo(leafletMap);

    dataCollector.kompetitor.forEach((k) => {
      if (k.lat == null || k.lng == null) return;
      const marker = L.circleMarker([k.lat, k.lng], {
        radius: 8,
        weight: 2,
        color: "#fff",
        fillColor: TIER_COLOR[ratingTier(k.rating)],
        fillOpacity: 1,
      }).addTo(leafletMap);
      marker.bindPopup(competitorInfoHtml(k));
      marker.on("click", () => showSelectedInfo(k));
    });
  }

  function competitorInfoHtml(k) {
    return `<div style="font-family:Inter,sans-serif;font-size:12.5px;max-width:220px;">
      <a href="${googleMapsUrl(k)}" target="_blank" rel="noopener noreferrer" style="color:#4f5df7;font-weight:700;text-decoration:none;">${k.nama} <i class="fa-solid fa-arrow-up-right-from-square" style="font-size:10px;"></i></a><br>
      <span>⭐ ${k.rating.toFixed(1)} · ${k.jumlah_review.toLocaleString("id-ID")} ulasan</span><br>
      <span>${k.rentang_harga}</span><br>
      <span style="color:#6b7280">${k.alamat}</span>
    </div>`;
  }

  function showSelectedInfo(k) {
    $("#map-selected-info").html(`
      <a class="competitor-link" href="${googleMapsUrl(k)}" target="_blank" rel="noopener noreferrer"><strong>${k.nama}</strong> <i class="fa-solid fa-arrow-up-right-from-square" style="font-size:10px;"></i></a>
       — ⭐ ${k.rating.toFixed(1)} (${k.jumlah_review.toLocaleString("id-ID")} ulasan) · ${k.rentang_harga}<br>
      <span style="color:var(--text-faint)">${k.alamat}</span>
    `);
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
