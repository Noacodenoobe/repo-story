/* Repo Opowieść — interactive education guide UI */
(() => {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  let lastResult = null;
  let currentPack = null;
  let chartInstances = [];
  let visNetwork = null;
  let slideIndex = 0;

  const GROUP_COLORS = {
    people: "#58a6ff",
    core: "#3fb950",
    infra: "#d29922",
    library: "#a371f7",
    audio: "#f778ba",
    apps: "#79c0ff",
    ai: "#ff7b72",
    default: "#8b949e",
  };

  if (window.mermaid) {
    const dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    window.mermaid.initialize({ startOnLoad: false, theme: dark ? "dark" : "default", securityLevel: "loose" });
  }

  $$(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.tab;
      $$(".tab").forEach((b) => b.classList.toggle("tab-active", b === btn));
      $$(".panel").forEach((p) => p.classList.toggle("panel-active", p.id === `tab-${tab}`));
      if (tab === "history") refreshHistory();
      if (tab === "diag") refreshDiagnostics();
      if (tab === "chat") refreshChatHint();
    });
  });

  $$(".section-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const sec = btn.dataset.section;
      $$(".section-btn").forEach((b) => b.classList.toggle("section-active", b === btn));
      $$(".edu-section").forEach((el) => {
        el.classList.toggle("section-visible", el.id === `sec-${sec}`);
      });
      if (sec === "graph") renderGraph(currentPack);
      if (sec === "flow") renderFlowDiagram(currentPack);
    });
  });

  async function refreshHealth() {
    const pill = $("#health-pill");
    const dot = pill.querySelector(".dot");
    const label = pill.querySelector(".label");
    try {
      const data = await (await fetch("/api/health")).json();
      if (data.ollama && (!data.missing_models || !data.missing_models.length)) {
        dot.className = "dot dot-ok";
        label.textContent = `Ollama OK · ${data.models_available.length} modeli`;
      } else if (data.ollama) {
        dot.className = "dot dot-warn";
        label.textContent = `Brak: ${(data.missing_models || []).join(", ")}`;
      } else {
        dot.className = "dot dot-bad";
        label.textContent = "Ollama niedostępna";
      }
    } catch {
      dot.className = "dot dot-bad";
      label.textContent = "Błąd serwera";
    }
  }

  function showAlert(msg, kind = "error") {
    const el = $("#alert");
    el.textContent = msg;
    el.className = "alert" + (kind === "info" ? " alert-info" : "");
    el.hidden = false;
  }

  function clearAlert() {
    $("#alert").hidden = true;
  }

  function setProgress(text, visible = true) {
    $("#progress").hidden = !visible;
    $("#progress-text").textContent = text;
  }

  function getPack(data) {
    if (data.education_pack && Object.keys(data.education_pack).length) {
      return data.education_pack;
    }
    const ld = data.lesson_deck || {};
    return {
      title: ld.title,
      essence: ld.essence,
      summary_3: ld.summary_3 || [],
      overview: {},
      use_cases: [],
      flow_steps: [],
      flow_mermaid: "",
      install_flow_mermaid: "",
      howto: [],
      modify_guide: {},
      charts: {},
      dependency_graph: {},
      story_slides: ld.slides || [],
      quiz: ld.quiz || [],
    };
  }

  $("#analyze-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    clearAlert();
    $("#results").hidden = true;
    const url = $("#repo-url").value.trim();
    if (!url) {
      showAlert("Podaj adres projektu.");
      return;
    }
    setProgress("Pobieram projekt i tworzę przewodnik (diagramy, instrukcja, wykresy)… Zwykle 2–4 minuty.");
    $("#analyze-btn").disabled = true;
    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url,
          force_reclone: $("#force-reclone").checked,
          include_technical: $("#include-technical").checked,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      lastResult = data;
      renderEducation(data);
    } catch (e) {
      showAlert(`Błąd: ${e.message}`);
    } finally {
      setProgress("", false);
      $("#analyze-btn").disabled = false;
    }
  });

  function renderEducation(data) {
    currentPack = getPack(data);
    $("#results").hidden = false;
    $("#result-meta").innerHTML = `
      <span><strong>Projekt:</strong> <a href="${data.repo_info.url}" target="_blank" rel="noopener">${escapeHtml(data.repo_info.url)}</a></span>
      <span><strong>Czas:</strong> ${data.duration_s}s</span>`;

    const p = currentPack;
    $("#guide-header").innerHTML = `
      <p class="essence">${escapeHtml(p.essence || "")}</p>
      <h2>${escapeHtml(p.title || "Przewodnik")}</h2>
      <ul class="summary-list">${(p.summary_3 || []).filter(Boolean).map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ul>`;

    renderOverview(p);
    renderUseCases(p);
    renderFlow(p);
    renderHowto(p);
    renderModify(p);
    renderCharts(p);
    renderGraph(p);
    renderStory(p);
    renderTechnical(data);

    $$(".section-btn").forEach((b, i) => b.classList.toggle("section-active", i === 0));
    $$(".edu-section").forEach((el) => el.classList.toggle("section-visible", el.id === "sec-overview"));
    $("#results").scrollIntoView({ behavior: "smooth" });
  }

  function renderOverview(p) {
    const ov = p.overview || {};
    $("#sec-overview").innerHTML = `
      <h3>📋 Przegląd projektu</h3>
      ${block("Czym jest", ov.what)}
      ${block("Po co powstał", ov.why)}
      ${block("Jak działa (głębiej)", ov.how_it_works)}
      ${block("Ograniczenia", ov.limitations)}
    `;
  }

  function block(title, text) {
    if (!text) return "";
    return `<div class="edu-block"><h4>${escapeHtml(title)}</h4><p>${escapeHtml(text)}</p></div>`;
  }

  function renderUseCases(p) {
    const items = p.use_cases || [];
    $("#sec-use_cases").innerHTML = `
      <h3>🎯 Kiedy tego użyć?</h3>
      <div class="use-case-grid">
        ${items.map((u) => `
          <article class="use-case-card">
            <span class="uc-emoji">${escapeHtml(u.emoji || "📌")}</span>
            <h4>${escapeHtml(u.title)}</h4>
            <p><strong>Sytuacja:</strong> ${escapeHtml(u.scenario)}</p>
            <p class="uc-benefit"><strong>Korzyść:</strong> ${escapeHtml(u.benefit)}</p>
          </article>`).join("") || "<p class='muted'>Brak danych.</p>"}
      </div>`;
  }

  function renderFlow(p) {
    const steps = p.flow_steps || [];
    $("#sec-flow").innerHTML = `
      <h3>🔄 Jak to działa — krok po kroku</h3>
      <div class="flow-layout">
        <div class="mermaid-wrap"><div class="mermaid" id="flow-mermaid"></div></div>
        <div class="flow-steps-list" id="flow-steps-list">
          ${steps.map((s, i) => `
            <button type="button" class="flow-step-btn" data-idx="${i}">
              <strong>${i + 1}. ${escapeHtml(s.title)}</strong>
              <span>${escapeHtml(s.description)}</span>
              ${s.tip ? `<em>💡 ${escapeHtml(s.tip)}</em>` : ""}
            </button>`).join("")}
        </div>
      </div>
      ${p.install_flow_mermaid ? `<h4>Schemat instalacji</h4><div class="mermaid-wrap"><div class="mermaid" id="install-flow-mermaid"></div></div>` : ""}
      <div class="flow-detail" id="flow-detail"></div>`;
    renderFlowDiagram(p);
    renderInstallFlowDiagram(p);
    $("#flow-steps-list")?.querySelectorAll(".flow-step-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const s = steps[parseInt(btn.dataset.idx, 10)];
        $("#flow-detail").innerHTML = `<h4>${escapeHtml(s.title)}</h4><p>${escapeHtml(s.description)}</p>`;
      });
    });
    if (steps[0]) steps[0] && ($("#flow-detail").innerHTML = `<p>${escapeHtml(steps[0].description)}</p>`);
  }

  async function renderMermaidInto(el, code, prefix) {
    if (!el || !window.mermaid) return;
    el.textContent = code;
    try {
      const { svg } = await window.mermaid.render(`${prefix}_${Date.now()}`, code);
      el.innerHTML = svg;
    } catch {
      el.textContent = "Nie udało się narysować diagramu.";
    }
  }

  async function renderFlowDiagram(p) {
    const el = document.getElementById("flow-mermaid");
    await renderMermaidInto(el, p.flow_mermaid || "flowchart TD\n    A[Brak diagramu]", "flow");
  }

  async function renderInstallFlowDiagram(p) {
    const el = document.getElementById("install-flow-mermaid");
    if (!el || !p.install_flow_mermaid) return;
    await renderMermaidInto(el, p.install_flow_mermaid, "install");
  }

  function renderHowto(p) {
    const steps = p.howto || [];
    $("#sec-howto").innerHTML = `
      <h3>🛠️ Instrukcja instalacji i uruchomienia</h3>
      ${steps.map((h) => `
        <div class="howto-step">
          <h4>Krok ${h.step}: ${escapeHtml(h.title)}</h4>
          <p>${escapeHtml(h.body)}</p>
          ${(h.commands || []).length ? `<pre class="code-block">${(h.commands || []).map(escapeHtml).join("\n")}</pre>` : ""}
        </div>`).join("") || "<p class='muted'>Brak instrukcji.</p>"}`;
  }

  function renderModify(p) {
    const mg = p.modify_guide || {};
    const easy = mg.easy || [];
    const adv = mg.advanced || [];
    $("#sec-modify").innerHTML = `
      <h3>✏️ Co możesz zmienić?</h3>
      <p class="modify-warn">⚠️ ${escapeHtml(mg.warning || "Twórz kopię zapasową przed większymi zmianami.")}</p>
      <h4>Bez programowania</h4>
      <div class="modify-grid">${easy.map(itemCard).join("")}</div>
      <h4>Wymaga wiedzy technicznej</h4>
      <div class="modify-grid modify-advanced">${adv.map(itemCard).join("")}</div>`;
  }

  function itemCard(item) {
    return `<article class="modify-card"><h5>${escapeHtml(item.title)}</h5><p>${escapeHtml(item.body)}</p></article>`;
  }

  function renderCharts(p) {
    chartInstances.forEach((c) => c.destroy());
    chartInstances = [];
    const charts = p.charts || {};
    $("#sec-charts").innerHTML = `
      <h3>📊 Wykresy</h3>
      <div class="charts-row">
        <div class="chart-box"><canvas id="chart-lang"></canvas></div>
        <div class="chart-box"><canvas id="chart-comp"></canvas></div>
      </div>
      <p class="muted chart-metrics" id="chart-metrics"></p>`;
    const metrics = charts.metrics || {};
    $("#chart-metrics").textContent = `Plików: ${metrics.files ?? "—"} · Linii kodu: ${(metrics.lines ?? 0).toLocaleString("pl-PL")}`;

    const isDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const fg = isDark ? "#e6edf3" : "#1f2328";
    const opts = {
      responsive: true,
      plugins: { legend: { labels: { color: fg } } },
    };

    const lang = charts.languages;
    if (lang?.labels?.length && window.Chart) {
      chartInstances.push(new Chart($("#chart-lang"), {
        type: "doughnut",
        data: {
          labels: lang.labels,
          datasets: [{ data: lang.values, backgroundColor: ["#3fb950", "#58a6ff", "#d29922", "#f778ba", "#a371f7"] }],
        },
        options: { ...opts, plugins: { ...opts.plugins, title: { display: true, text: "Języki (pliki)", color: fg } } },
      }));
    }
    const comp = charts.composition;
    if (comp?.labels?.length && window.Chart) {
      chartInstances.push(new Chart($("#chart-comp"), {
        type: "bar",
        data: {
          labels: comp.labels,
          datasets: [{ label: "Liczba plików", data: comp.values, backgroundColor: "#58a6ff" }],
        },
        options: {
          ...opts,
          scales: { x: { ticks: { color: fg } }, y: { ticks: { color: fg } } },
          plugins: { ...opts.plugins, title: { display: true, text: "Skład projektu", color: fg } },
        },
      }));
    }
  }

  function renderGraph(p) {
    const container = $("#sec-graph");
    container.innerHTML = `
      <h3>🕸️ Mapa połączeń — kliknij węzeł po wyjaśnienie</h3>
      <div id="graph-network" class="graph-network"></div>
      <div id="graph-node-panel" class="graph-node-panel muted">Kliknij element na mapie.</div>`;

    const g = p.dependency_graph || {};
    const nodes = (g.nodes || []).map((n) => ({
      id: n.id,
      label: n.label,
      title: n.role,
      group: n.group,
      description: n.description,
    }));
    const edges = (g.edges || []).map((e) => ({ from: e.from, to: e.to, label: e.label || "" }));

    if (!window.vis || !nodes.length) {
      $("#graph-network").textContent = "Brak danych mapy.";
      return;
    }

    const visNodes = new vis.DataSet(
      nodes.map((n) => ({
        id: n.id,
        label: n.label,
        color: GROUP_COLORS[n.group] || GROUP_COLORS.default,
        font: { color: "#fff", size: 14 },
      }))
    );
    const visEdges = new vis.DataSet(edges.map((e) => ({ ...e, arrows: "to", color: { color: "#8b949e" } })));

    if (visNetwork) {
      visNetwork.destroy();
    }
    visNetwork = new vis.Network(
      document.getElementById("graph-network"),
      { nodes: visNodes, edges: visEdges },
      {
        physics: { stabilization: true, barnesHut: { gravitationalConstant: -3000 } },
        interaction: { hover: true },
      }
    );

    const panel = $("#graph-node-panel");
    visNetwork.on("click", (params) => {
      if (!params.nodes.length) return;
      const id = params.nodes[0];
      const node = nodes.find((n) => n.id === id);
      if (node) {
        panel.innerHTML = `<h4>${escapeHtml(node.label)}</h4><p><strong>Rola:</strong> ${escapeHtml(node.title)}</p><p>${escapeHtml(node.description)}</p>`;
      }
    });
  }

  function renderStory(p) {
    const slides = p.story_slides || [];
    slideIndex = 0;
    $("#sec-story").innerHTML = `
      <h3>📖 Opowieść — krótkie podsumowanie</h3>
      <div class="presentation-mini">
        <span id="story-counter">1 / ${slides.length || 1}</span>
        <div id="story-stage"></div>
        <div class="slide-nav">
          <button type="button" class="btn-secondary" id="story-prev">←</button>
          <button type="button" class="btn-primary" id="story-next">→</button>
        </div>
      </div>
      <div id="story-quiz"></div>`;
    renderStorySlide(slides);
    $("#story-prev")?.addEventListener("click", () => {
      slideIndex = Math.max(0, slideIndex - 1);
      renderStorySlide(slides);
    });
    $("#story-next")?.addEventListener("click", () => {
      slideIndex = Math.min(slides.length - 1, slideIndex + 1);
      renderStorySlide(slides);
    });
    renderQuiz(p.quiz || [], "#story-quiz");
  }

  function renderStorySlide(slides) {
    if (!slides.length) {
      $("#story-stage").innerHTML = "<p>Brak slajdów.</p>";
      return;
    }
    const s = slides[slideIndex];
    $("#story-counter").textContent = `${slideIndex + 1} / ${slides.length}`;
    $("#story-stage").innerHTML = `
      <div class="slide-card">
        <div class="slide-emoji">${escapeHtml(s.emoji || "📖")}</div>
        <h4>${escapeHtml(s.title)}</h4>
        <p>${escapeHtml(s.body)}</p>
        ${s.analogy ? `<p class="slide-analogy"><strong>Analogia:</strong> ${escapeHtml(s.analogy)}</p>` : ""}
        ${s.for_you ? `<p class="slide-for-you">${escapeHtml(s.for_you)}</p>` : ""}
      </div>`;
  }

  function renderQuiz(questions, sel) {
    const el = $(sel);
    if (!el || !questions.length) {
      if (el) el.innerHTML = "";
      return;
    }
    el.innerHTML = `<h4>📝 Quiz</h4>${questions.map((q, qi) => `
      <div class="quiz-item" data-correct="${q.correct_index}">
        <p>${escapeHtml(q.question)}</p>
        <div class="quiz-options">${(q.options || []).map((o, oi) =>
          `<button type="button" class="quiz-opt" data-oi="${oi}">${escapeHtml(o)}</button>`).join("")}</div>
        <p class="quiz-feedback" hidden></p>
      </div>`).join("")}`;
    el.querySelectorAll(".quiz-opt").forEach((btn) => {
      btn.addEventListener("click", () => {
        const item = btn.closest(".quiz-item");
        const correct = parseInt(item.dataset.correct, 10);
        const chosen = parseInt(btn.dataset.oi, 10);
        item.querySelectorAll(".quiz-opt").forEach((b) => (b.disabled = true));
        const fb = item.querySelector(".quiz-feedback");
        fb.hidden = false;
        fb.textContent = chosen === correct ? "✅ Dobrze!" : "💡 Spróbuj jeszcze raz przeczytać przewodnik.";
      });
    });
  }

  function renderTechnical(data) {
    const sec = $("#sec-technical");
    const hasTech = data.llm && Object.keys(data.llm).length > 0;
    const s = data.static || {};
    sec.innerHTML = `
      <h3>🔧 Szczegóły techniczne</h3>
      <p class="muted">Dla osób, które chcą głębiej — diagramy Mermaid, statystyki, analiza LLM.</p>
      <h4>Statystyki</h4>
      <div id="tech-static"></div>
      <h4>Diagramy Mermaid</h4>
      <div class="mermaid" id="tech-overview"></div>
      <div class="mermaid" id="tech-tree"></div>
      <div id="tech-llm" ${hasTech ? "" : 'hidden'}></div>
      <div id="tech-polish" ${data.polish_report ? "" : "hidden"}></div>`;
    $("#tech-static").innerHTML = `<p>Plików: ${s.total_files}, linii: ${(s.total_lines || 0).toLocaleString("pl-PL")}</p>`;
    if (data.diagrams) {
      renderMermaid("tech-overview", data.diagrams.overview);
      renderMermaid("tech-tree", data.diagrams.tree);
    }
    if (hasTech) {
      $("#tech-llm").innerHTML = `<h4>Analiza LLM</h4><pre class="code-block">${escapeHtml(JSON.stringify(data.llm, null, 2).slice(0, 8000))}</pre>`;
    }
    if (data.polish_report && window.marked) {
      $("#tech-polish").innerHTML = `<h4>Raport Markdown</h4><div class="markdown-body">${window.marked.parse(data.polish_report)}</div>`;
    }
  }

  async function renderMermaid(id, code) {
    const el = document.getElementById(id);
    if (!el || !code || !window.mermaid) return;
    try {
      const { svg } = await window.mermaid.render(`${id}_${Date.now()}`, code);
      el.innerHTML = svg;
    } catch {
      el.textContent = "(diagram niedostępny)";
    }
  }

  $("#btn-download-html").addEventListener("click", () => {
    if (!lastResult?.id) return;
    window.open(`/api/reports/${lastResult.id}/export.html`, "_blank");
  });

  $("#btn-download-md").addEventListener("click", async () => {
    if (!lastResult) return;
    try {
      const res = await fetch(`/api/reports/${lastResult.id}/markdown`);
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail);
      downloadText(await res.text(), `${lastResult.repo_info.slug}_przewodnik.md`);
    } catch (e) {
      showAlert(`Pobieranie: ${e.message}`);
    }
  });

  function downloadText(content, filename) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([content], { type: "text/plain;charset=utf-8" }));
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  async function refreshHistory() {
    const list = $("#history-list");
    list.innerHTML = "<div class='history-empty'>Ładuję…</div>";
    try {
      const q = $("#history-search").value.trim();
      const url = q ? `/api/reports?q=${encodeURIComponent(q)}` : "/api/reports";
      const data = await (await fetch(url)).json();
      if (!data.items?.length) {
        list.innerHTML = "<div class='history-empty'>Brak zapisów.</div>";
        return;
      }
      list.innerHTML = data.items.map((r) => `
        <div class="history-item" data-id="${r.id}">
          <div class="info">
            <div class="url">${escapeHtml(r.presentation_title || r.url)}</div>
            <div class="desc">${r.created_at_iso}</div>
          </div>
          <div class="actions">
            <button type="button" class="btn-icon" data-act="view">👁️ Otwórz</button>
            <button type="button" class="btn-icon" data-act="del">🗑️</button>
          </div>
        </div>`).join("");
    } catch (e) {
      list.innerHTML = `<div class='history-empty'>${escapeHtml(e.message)}</div>`;
    }
  }

  $("#history-refresh").addEventListener("click", refreshHistory);
  $("#history-search").addEventListener("input", debounce(refreshHistory, 250));

  $("#history-list").addEventListener("click", async (ev) => {
    const btn = ev.target.closest(".btn-icon");
    if (!btn) return;
    const item = btn.closest(".history-item");
    const id = item?.dataset?.id;
    if (!id) return;
    if (btn.dataset.act === "del") {
      if (confirm("Usunąć?") && (await fetch(`/api/reports/${id}`, { method: "DELETE" })).ok) item.remove();
      return;
    }
    if (btn.dataset.act === "view") {
      const data = await (await fetch(`/api/reports/${id}`)).json();
      lastResult = { ...data, duration_s: 0, repo_info: data.repo_info, static: data.static, llm: data.llm, diagrams: data.diagrams, polish_report: data.polish_report, education_pack: data.education_pack, lesson_deck: data.lesson_deck };
      $$(".tab").forEach((b) => b.classList.toggle("tab-active", b.dataset.tab === "analyze"));
      $$(".panel").forEach((p) => p.classList.toggle("panel-active", p.id === "tab-analyze"));
      renderEducation(lastResult);
    }
  });

  $("#diag-refresh").addEventListener("click", refreshDiagnostics);
  $("#profile-refresh").addEventListener("click", async () => {
    $("#diag-kb").textContent = "Zbieram profil systemu…";
    try {
      const res = await fetch("/api/system-profile/refresh", { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      $("#diag-kb").textContent = `Profil zaktualizowany.\n${JSON.stringify(data, null, 2)}`;
      refreshDiagnostics();
    } catch (e) {
      $("#diag-kb").textContent = `Błąd: ${e.message}`;
    }
  });

  async function refreshDiagnostics() {
    try {
      const [h, c, kb] = await Promise.all([
        fetch("/api/health").then((r) => r.json()),
        fetch("/api/config").then((r) => r.json()),
        fetch("/api/knowledge/stats").then((r) => r.json()),
      ]);
      $("#diag-output").textContent = JSON.stringify(h, null, 2);
      $("#diag-config").textContent = JSON.stringify(c, null, 2);
      $("#diag-kb").textContent = JSON.stringify(kb, null, 2);
    } catch (e) {
      $("#diag-output").textContent = String(e);
    }
  }

  let chatSessionId = null;
  let chatAbortController = null;
  let chatVoiceReply = true;
  let chatTtsAudio = null;
  let chatTtsAbort = null;
  let lastTtsText = "";
  let forceVoiceReplyOnce = false;
  let audioPlaybackUnlocked = false;

  const chatVoiceToggle = $("#chat-voice-reply");
  const chatTtsBar = $("#chat-tts-bar");
  const chatTtsLabel = $("#chat-tts-label");
  const chatTtsStop = $("#chat-tts-stop");
  const chatTtsReplay = $("#chat-tts-replay");

  if (chatVoiceToggle) {
    chatVoiceReply = chatVoiceToggle.checked;
    chatVoiceToggle.addEventListener("change", () => {
      chatVoiceReply = chatVoiceToggle.checked;
    });
  }

  function isVoiceReplyEnabled() {
    return chatVoiceReply || (chatVoiceToggle && chatVoiceToggle.checked);
  }

  function shouldAutoPlayVoice() {
    return isVoiceReplyEnabled() || forceVoiceReplyOnce;
  }

  /** Browsers block audio.play() without a recent user gesture — unlock on mic click. */
  function unlockAudioPlayback() {
    if (audioPlaybackUnlocked) return;
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (Ctx) {
        const ctx = new Ctx();
        if (ctx.state === "suspended") ctx.resume();
      }
      const silent = new Audio(
        "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=",
      );
      silent.volume = 0.01;
      silent.play().then(() => {
        audioPlaybackUnlocked = true;
      }).catch(() => {});
    } catch {
      /* ignore */
    }
  }

  function showTtsBar(playing) {
    if (!chatTtsBar) return;
    chatTtsBar.classList.remove("hidden");
    chatTtsBar.classList.toggle("chat-tts-bar-playing", !!playing);
    if (chatTtsLabel) {
      chatTtsLabel.textContent = playing
        ? "Odtwarzam odpowiedź… (możesz zatrzymać)"
        : "Gotowe — możesz ponowić odtwarzanie";
    }
    if (chatTtsReplay) chatTtsReplay.disabled = !lastTtsText;
  }

  function hideTtsBar() {
    if (!chatTtsBar) return;
    chatTtsBar.classList.add("hidden");
    chatTtsBar.classList.remove("chat-tts-bar-playing");
  }

  function stopTts() {
    if (chatTtsAbort) {
      chatTtsAbort.abort();
      chatTtsAbort = null;
    }
    if (chatTtsAudio) {
      chatTtsAudio.pause();
      try {
        if (chatTtsAudio.src) URL.revokeObjectURL(chatTtsAudio.src);
      } catch {
        /* ignore */
      }
      chatTtsAudio = null;
    }
    hideTtsBar();
  }

  if (chatTtsStop) chatTtsStop.addEventListener("click", () => stopTts());
  if (chatTtsReplay) {
    chatTtsReplay.addEventListener("click", () => {
      if (lastTtsText) playTtsForText(lastTtsText);
    });
  }

  async function playTtsForText(text) {
    if (!text || !text.trim()) return;
    stopTts();
    lastTtsText = text.trim();
    chatTtsAbort = new AbortController();
    showTtsBar(true);
    try {
      const res = await fetch("/api/tts/speak", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: lastTtsText }),
        signal: chatTtsAbort.signal,
      });
      if (!res.ok) {
        let detail = "TTS niedostępne";
        try {
          const err = await res.json();
          detail = err.detail || detail;
        } catch {
          /* ignore */
        }
        throw new Error(detail);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      chatTtsAudio = new Audio(url);
      chatTtsAudio.onended = () => {
        URL.revokeObjectURL(url);
        chatTtsAudio = null;
        showTtsBar(false);
      };
      await chatTtsAudio.play();
      audioPlaybackUnlocked = true;
    } catch (e) {
      if (e.name === "AbortError") {
        hideTtsBar();
      } else {
        showTtsBar(false);
        const hint =
          e.name === "NotAllowedError"
            ? "Przeglądarka zablokowała auto-odtwarzanie. Kliknij 🔊 Odtwórz przy odpowiedzi lub 🔊 Ponów."
            : `Głos: ${e.message}. Użyj 🔊 Odtwórz przy odpowiedzi.`;
        appendChatMessage("system", hint);
        if (chatMicStatus) chatMicStatus.textContent = hint;
      }
    } finally {
      chatTtsAbort = null;
    }
  }

  function attachAssistantTtsControls(wrapper, text) {
    if (!wrapper || !text || text.startsWith("Błąd:")) return;
    const actions = document.createElement("div");
    actions.className = "chat-msg-actions";
    const playBtn = document.createElement("button");
    playBtn.type = "button";
    playBtn.className = "chat-tts-btn";
    playBtn.textContent = "🔊 Odtwórz";
    playBtn.title = "Odtwórz odpowiedź głosem";
    playBtn.addEventListener("click", () => playTtsForText(text));
    const stopBtn = document.createElement("button");
    stopBtn.type = "button";
    stopBtn.className = "chat-tts-btn";
    stopBtn.textContent = "⏹ Stop";
    stopBtn.title = "Zatrzymaj odtwarzanie";
    stopBtn.addEventListener("click", () => stopTts());
    actions.append(playBtn, stopBtn);
    wrapper.appendChild(actions);
  }

  function createAssistantMessageShell() {
    const box = $("#chat-messages");
    const wrap = document.createElement("div");
    wrap.className = "chat-msg-assistant-wrap";
    const body = document.createElement("div");
    body.className = "chat-msg chat-msg-assistant chat-msg-streaming";
    wrap.appendChild(body);
    box.appendChild(wrap);
    box.scrollTop = box.scrollHeight;
    return { wrap, body };
  }

  function appendChatMessage(role, text, extraClass = "") {
    const box = $("#chat-messages");
    const div = document.createElement("div");
    div.className = `chat-msg chat-msg-${role}${extraClass ? ` ${extraClass}` : ""}`;
    div.textContent = text;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
    return div;
  }

  function formatCitations(citations) {
    return (citations || [])
      .map((c) => `• [${c.guide_title} / ${c.section}] ${(c.excerpt || "").slice(0, 120)}…`)
      .join("\n");
  }

  function renderChatCitations(citations) {
    const cites = formatCitations(citations);
    $("#chat-citations").textContent = cites ? `Źródła:\n${cites}` : "";
  }

  function parseSseBuffer(buffer) {
    const events = [];
    const parts = buffer.split("\n\n");
    const remainder = parts.pop() || "";
    for (const block of parts) {
      if (!block.trim()) continue;
      let eventName = "message";
      let dataLine = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) eventName = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLine = line.slice(5).trim();
      }
      if (!dataLine) continue;
      try {
        events.push({ event: eventName, data: JSON.parse(dataLine) });
      } catch {
        /* ignore malformed chunk */
      }
    }
    return { events, remainder };
  }

  async function streamChatMessage(msg, options = {}) {
    if (chatAbortController) chatAbortController.abort();
    chatAbortController = new AbortController();
    const signal = chatAbortController.signal;
    const autoVoice =
      options.voiceReply !== undefined ? options.voiceReply : shouldAutoPlayVoice();

    stopTts();
    appendChatMessage("user", msg);
    const { wrap: assistantWrap, body: pending } = createAssistantMessageShell();
    const submitBtn = $("#chat-submit");
    if (submitBtn) submitBtn.disabled = true;

    let buffer = "";
    let fullText = "";

    try {
      const res = await fetch("/api/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: msg,
          session_id: chatSessionId,
          voice_mode: autoVoice || isVoiceReplyEnabled(),
        }),
        signal,
      });

      if (!res.ok) {
        let detail = res.statusText;
        try {
          const err = await res.json();
          detail = err.detail || detail;
        } catch {
          /* non-JSON error body */
        }
        throw new Error(detail);
      }

      if (!res.body) throw new Error("Brak strumienia odpowiedzi.");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const { events, remainder } = parseSseBuffer(buffer);
        buffer = remainder;

        for (const { event, data } of events) {
          if (event === "meta") {
            if (data.session_id) chatSessionId = data.session_id;
            if (data.citations) renderChatCitations(data.citations);
          } else if (event === "token" && data.text) {
            fullText += data.text;
            pending.textContent = fullText;
            const box = $("#chat-messages");
            if (box) box.scrollTop = box.scrollHeight;
          } else if (event === "done") {
            if (data.session_id) chatSessionId = data.session_id;
            if (data.full_answer) fullText = data.full_answer;
            if (data.citations) renderChatCitations(data.citations);
          } else if (event === "error") {
            throw new Error(data.detail || "Błąd streamingu.");
          }
        }
      }

      pending.classList.remove("chat-msg-streaming");
      const answer = fullText || "(brak odpowiedzi)";
      pending.textContent = answer;
      attachAssistantTtsControls(assistantWrap, answer);
      const playNow = autoVoice && fullText;
      if (playNow) {
        await playTtsForText(fullText);
      }
      forceVoiceReplyOnce = false;
    } catch (e) {
      if (e.name === "AbortError") {
        pending.classList.remove("chat-msg-streaming");
        pending.textContent = fullText || "(przerwano)";
        attachAssistantTtsControls(assistantWrap, fullText || "");
        return;
      }
      pending.classList.remove("chat-msg-streaming");
      pending.textContent = `Błąd: ${e.message}`;
      attachAssistantTtsControls(assistantWrap, "");
    } finally {
      if (submitBtn) submitBtn.disabled = false;
      chatAbortController = null;
    }
  }

  function refreshChatHint() {
    fetch("/api/knowledge/stats")
      .then((r) => r.json())
      .then((s) => {
        if (!s.chunks && !$("#chat-messages").children.length) {
          appendChatMessage("system", `Baza: ${s.guides || 0} przewodników, ${s.chunks || 0} fragmentów. Zadaj pytanie.`);
        }
      })
      .catch(() => {});
  }

  $("#chat-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const input = $("#chat-input");
    const msg = input.value.trim();
    if (!msg) return;
    input.value = "";
    await streamChatMessage(msg);
  });

  // --- Phase 2: push-to-talk microphone (STT → stream chat) ---
  const chatMic = $("#chat-mic");
  const chatMicStatus = $("#chat-mic-status");
  let micRecorder = null;
  let micStream = null;
  let micChunks = [];
  let micState = "idle";
  const MAX_RECORD_MS = 120_000;
  let micMaxTimer = null;

  function setMicState(state, message = "") {
    micState = state;
    if (!chatMic) return;
    chatMic.classList.remove("chat-mic-recording", "chat-mic-transcribing", "chat-mic-active");
    if (state === "recording") {
      chatMic.classList.add("chat-mic-recording", "chat-mic-active");
      chatMic.textContent = "⏹";
      chatMic.setAttribute("aria-pressed", "true");
    } else {
      chatMic.textContent = "🎤";
      chatMic.setAttribute("aria-pressed", "false");
    }
    if (state === "transcribing") chatMic.classList.add("chat-mic-transcribing");
    chatMic.disabled = state === "transcribing";
    if (chatMicStatus) chatMicStatus.textContent = message;
  }

  async function transcribeAndChat(blob) {
    setMicState("transcribing", "Transkrybuję mowę…");
    const submitBtn = $("#chat-submit");
    if (submitBtn) submitBtn.disabled = true;
    try {
      const form = new FormData();
      form.append("audio", blob, "nagranie.webm");
      const res = await fetch("/api/stt/transcribe", { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      const text = (data.text || "").trim();
      if (!text) {
        throw new Error("Nie rozpoznano mowy — spróbuj ponownie, bliżej mikrofonu.");
      }
      setMicState("idle", `Rozpoznano (${data.model || "whisper"})`);
      if (chatVoiceToggle) {
        chatVoiceToggle.checked = true;
        chatVoiceReply = true;
      }
      forceVoiceReplyOnce = true;
      await streamChatMessage(text, { voiceReply: true });
    } catch (e) {
      setMicState("idle", "");
      appendChatMessage(
        "system",
        e.message.includes("Permission")
          ? "Brak dostępu do mikrofonu — zezwól w przeglądarce i sprawdź PipeWire."
          : `Mikrofon: ${e.message}`,
      );
    } finally {
      if (submitBtn) submitBtn.disabled = false;
    }
  }

  async function startMicRecording() {
    if (micState !== "idle" || !chatMic) return;
    unlockAudioPlayback();
    try {
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      setMicState("idle", "");
      appendChatMessage(
        "system",
        "Nie można użyć mikrofonu — sprawdź uprawnienia przeglądarki i ustawienia dźwięku (PipeWire).",
      );
      return;
    }
    micChunks = [];
    const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : "audio/webm";
    micRecorder = new MediaRecorder(micStream, { mimeType });
    micRecorder.ondataavailable = (ev) => {
      if (ev.data.size > 0) micChunks.push(ev.data);
    };
    micRecorder.start(250);
    setMicState("recording", "Nagrywam… kliknij ⏹ aby zakończyć i wysłać.");
    micMaxTimer = setTimeout(() => stopMicRecording(), MAX_RECORD_MS);
  }

  function stopMicRecording() {
    if (micMaxTimer) {
      clearTimeout(micMaxTimer);
      micMaxTimer = null;
    }
    if (micState !== "recording" || !micRecorder) return;

    const recorder = micRecorder;
    micRecorder = null;

    recorder.onstop = async () => {
      if (micStream) {
        micStream.getTracks().forEach((t) => t.stop());
        micStream = null;
      }
      const blob = new Blob(micChunks, { type: recorder.mimeType || "audio/webm" });
      micChunks = [];
      if (blob.size < 100) {
        setMicState("idle", "");
        appendChatMessage("system", "Nagranie za krótkie — kliknij 🎤, poczekaj chwilę i mów wyraźniej.");
        return;
      }
      await transcribeAndChat(blob);
    };

    if (recorder.state !== "inactive") recorder.stop();
  }

  if (chatMic) {
    chatMic.addEventListener("click", async (ev) => {
      ev.preventDefault();
      if (micState === "transcribing") return;
      if (micState === "recording") {
        stopMicRecording();
        return;
      }
      stopTts();
      await startMicRecording();
    });
  }

  function debounce(fn, ms) {
    let t;
    return (...a) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...a), ms);
    };
  }

  function escapeHtml(s) {
    if (s == null) return "";
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  refreshHealth();
  setInterval(refreshHealth, 60_000);
})();
