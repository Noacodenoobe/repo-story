/* Repo Opowieść — interactive zero-tech presentation UI */
(() => {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  let lastResult = null;
  let currentDeck = null;
  let slideIndex = 0;

  if (window.mermaid) {
    const isDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    window.mermaid.initialize({ startOnLoad: false, theme: isDark ? "dark" : "default", securityLevel: "loose" });
  }

  $$(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.tab;
      $$(".tab").forEach((b) => b.classList.toggle("tab-active", b === btn));
      $$(".panel").forEach((p) => p.classList.toggle("panel-active", p.id === `tab-${tab}`));
      if (tab === "history") refreshHistory();
      if (tab === "diag") refreshDiagnostics();
    });
  });

  async function refreshHealth() {
    const pill = $("#health-pill");
    const dot = pill.querySelector(".dot");
    const label = pill.querySelector(".label");
    dot.className = "dot dot-unknown";
    label.textContent = "Sprawdzam Ollamę…";
    try {
      const res = await fetch("/api/health");
      const data = await res.json();
      if (data.ollama && (!data.missing_models || data.missing_models.length === 0)) {
        dot.className = "dot dot-ok";
        label.textContent = `Ollama OK · ${data.models_available.length} modeli`;
      } else if (data.ollama) {
        dot.className = "dot dot-warn";
        label.textContent = `Brak modelu: ${(data.missing_models || []).join(", ")}`;
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

  $("#analyze-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    clearAlert();
    $("#results").hidden = true;

    const url = $("#repo-url").value.trim();
    if (!url) {
      showAlert("Podaj adres projektu.");
      return;
    }

    const payload = {
      url,
      force_reclone: $("#force-reclone").checked,
      include_technical: $("#include-technical").checked,
    };

    setProgress("Pobieram projekt i piszę opowieść… To może potrwać kilka minut.");
    $("#analyze-btn").disabled = true;

    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      lastResult = data;
      renderResult(data);
    } catch (e) {
      showAlert(`Błąd: ${e.message}`);
    } finally {
      setProgress("", false);
      $("#analyze-btn").disabled = false;
    }
  });

  function renderResult(data) {
    $("#results").hidden = false;
    currentDeck = data.lesson_deck || null;
    slideIndex = 0;

    $("#result-meta").innerHTML = `
      <span><strong>Projekt:</strong> <a href="${data.repo_info.url}" target="_blank" rel="noopener">${data.repo_info.url}</a></span>
      <span><strong>Czas:</strong> ${data.duration_s}s</span>
    `;

    renderDeckIntro(currentDeck);
    renderSlide();
    renderQuiz(currentDeck?.quiz || []);

    const hasTechnical = data.include_technical || (data.llm && Object.keys(data.llm).length > 0);
    $("#technical-details").open = false;
    if (hasTechnical || data.static) {
      renderTechnical(data);
    }

    $("#results").scrollIntoView({ behavior: "smooth" });
  }

  function renderDeckIntro(deck) {
    const el = $("#deck-intro");
    if (!deck || !deck.slides?.length) {
      el.innerHTML = "<p class='muted'>Nie udało się wygenerować prezentacji.</p>";
      return;
    }
    const summary = (deck.summary_3 || []).filter(Boolean).map((s) => `<li>${escapeHtml(s)}</li>`).join("");
    el.innerHTML = `
      <p class="essence">${escapeHtml(deck.essence || "")}</p>
      <h2>${escapeHtml(deck.title || "Opowieść o projekcie")}</h2>
      ${summary ? `<ul class="summary-list">${summary}</ul>` : ""}
      <p class="muted">Użyj przycisków poniżej, aby przejść przez sceny jedna po drugiej.</p>
    `;
  }

  function renderSlide() {
    const slides = currentDeck?.slides || [];
    const stage = $("#slide-stage");
    if (!slides.length) {
      stage.innerHTML = "<p>Brak slajdów.</p>";
      return;
    }

    slideIndex = Math.max(0, Math.min(slideIndex, slides.length - 1));
    const s = slides[slideIndex];
    const glossary = (s.glossary || [])
      .map(
        (g) =>
          `<button type="button" class="glossary-btn" data-def="${escapeAttr(g.definition)}">${escapeHtml(g.term)}</button>`
      )
      .join(" ");

    stage.innerHTML = `
      <article class="slide-card slide-fade">
        <div class="slide-emoji">${escapeHtml(s.emoji || "📖")}</div>
        <h3 class="slide-title">${escapeHtml(s.title || "")}</h3>
        <p class="slide-body">${escapeHtml(s.body || "")}</p>
        ${s.analogy ? `<p class="slide-analogy"><strong>Analogia:</strong> ${escapeHtml(s.analogy)}</p>` : ""}
        ${s.for_you ? `<p class="slide-for-you"><strong>Co to dla Ciebie:</strong> ${escapeHtml(s.for_you)}</p>` : ""}
        ${s.more_detail ? `<details class="slide-more"><summary>Chcę więcej szczegółów</summary><p>${escapeHtml(s.more_detail)}</p></details>` : ""}
        ${glossary ? `<div class="glossary-row"><span class="muted">Słowniczek:</span> ${glossary}</div>` : ""}
      </article>
    `;

    stage.querySelectorAll(".glossary-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        alert(btn.dataset.def || "");
      });
    });

    $("#slide-counter").textContent = `${slideIndex + 1} / ${slides.length}`;
    const pct = ((slideIndex + 1) / slides.length) * 100;
    $("#progress-bar-fill").style.width = `${pct}%`;
    $("#btn-prev").disabled = slideIndex === 0;
    $("#btn-next").textContent = slideIndex >= slides.length - 1 ? "Zakończ →" : "Dalej →";
  }

  $("#btn-prev").addEventListener("click", () => {
    slideIndex -= 1;
    renderSlide();
  });

  $("#btn-next").addEventListener("click", () => {
    const total = currentDeck?.slides?.length || 0;
    if (slideIndex < total - 1) {
      slideIndex += 1;
      renderSlide();
    } else {
      $("#quiz-card").scrollIntoView({ behavior: "smooth" });
    }
  });

  document.addEventListener("keydown", (ev) => {
    if ($("#results").hidden) return;
    if (ev.key === "ArrowRight") $("#btn-next").click();
    if (ev.key === "ArrowLeft" && !$("#btn-prev").disabled) $("#btn-prev").click();
  });

  $("#btn-fullscreen").addEventListener("click", () => {
    const card = $("#presentation-card");
    if (!document.fullscreenElement) {
      card.requestFullscreen?.();
    } else {
      document.exitFullscreen?.();
    }
  });

  function renderQuiz(questions) {
    const card = $("#quiz-card");
    const block = $("#quiz-block");
    if (!questions.length) {
      card.hidden = true;
      return;
    }
    card.hidden = false;
    block.innerHTML = questions
      .map(
        (q, qi) => `
      <div class="quiz-item" data-q="${qi}" data-correct="${q.correct_index}">
        <p class="quiz-q">${escapeHtml(q.question)}</p>
        <div class="quiz-options">
          ${(q.options || [])
            .map(
              (opt, oi) =>
                `<button type="button" class="quiz-opt" data-oi="${oi}">${escapeHtml(opt)}</button>`
            )
            .join("")}
        </div>
        <p class="quiz-feedback" hidden></p>
      </div>`
      )
      .join("");

    block.querySelectorAll(".quiz-opt").forEach((btn) => {
      btn.addEventListener("click", () => {
        const item = btn.closest(".quiz-item");
        const correct = parseInt(item.dataset.correct, 10);
        const chosen = parseInt(btn.dataset.oi, 10);
        const fb = item.querySelector(".quiz-feedback");
        item.querySelectorAll(".quiz-opt").forEach((b) => (b.disabled = true));
        fb.hidden = false;
        fb.textContent =
          chosen === correct ? "✅ Tak, dobrze!" : "💡 Nie tym razem — ale to tylko powtórka materiału.";
        fb.className = "quiz-feedback " + (chosen === correct ? "ok" : "warn");
      });
    });
  }

  function renderTechnical(data) {
    const s = data.static || {};
    const kv = (k, v) => `<div class="kv"><span class="k">${k}</span><span class="v">${v}</span></div>`;
    $("#static-block").innerHTML = `
      <div class="kv-grid">
        ${kv("Plików", s.total_files ?? "—")}
        ${kv("Linii", (s.total_lines ?? 0).toLocaleString("pl-PL"))}
      </div>`;

    if (data.diagrams) {
      renderDiagram("diagram-overview", data.diagrams.overview);
      renderDiagram("diagram-tree", data.diagrams.tree);
    }

    const hasLlm = data.llm && Object.keys(data.llm).length > 0;
    $("#card-llm").hidden = !hasLlm;
    if (hasLlm) {
      const sec = (title, body) =>
        `<div class="llm-section"><h5>${title}</h5><div>${escapeHtml(body || "—")}</div></div>`;
      $("#llm-block").innerHTML =
        sec("Architektura", data.llm.architecture) +
        sec("Moduły", data.llm.main_modules) +
        sec("Jakość", data.llm.quality_assessment);
    }

    const hasPolish = !!data.polish_report;
    $("#card-polish").hidden = !hasPolish;
    if (hasPolish && window.marked) {
      $("#polish-block").innerHTML = window.marked.parse(data.polish_report);
    }
  }

  function renderDiagram(elId, code) {
    const el = document.getElementById(elId);
    if (!el || !window.mermaid || !code) return;
    el.textContent = code;
    const renderId = `m_${elId}_${Date.now()}`;
    window.mermaid.render(renderId, code).then(({ svg }) => {
      el.innerHTML = svg;
    }).catch(() => {
      el.textContent = "(diagram niedostępny)";
    });
  }

  $("#btn-download-md").addEventListener("click", async () => {
    if (!lastResult) return;
    try {
      const res = await fetch(`/api/reports/${lastResult.id}/markdown`);
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
      downloadText(await res.text(), `${lastResult.repo_info.slug}_opowiesc.md`);
    } catch (e) {
      showAlert(`Pobieranie nie powiodło się: ${e.message}`);
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
        list.innerHTML = "<div class='history-empty'>Brak zapisanych opowieści.</div>";
        return;
      }
      list.innerHTML = data.items
        .map(
          (r) => `
        <div class="history-item" data-id="${r.id}">
          <div class="info">
            <div class="url">${escapeHtml(r.presentation_title || r.url || r.slug)}</div>
            <div class="desc">${r.created_at_iso || "?"}</div>
          </div>
          <div class="actions">
            <button type="button" class="btn-icon" data-act="view">👁️ Otwórz</button>
            <button type="button" class="btn-icon" data-act="del">🗑️</button>
          </div>
        </div>`
        )
        .join("");
    } catch (e) {
      list.innerHTML = `<div class='history-empty'>Błąd: ${escapeHtml(e.message)}</div>`;
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
      lastResult = {
        id: data.id,
        duration_s: 0,
        repo_info: data.repo_info,
        static: data.static,
        llm: data.llm,
        diagrams: data.diagrams || {},
        polish_report: data.polish_report,
        lesson_deck: data.lesson_deck,
      };
      $$(".tab").forEach((b) => b.classList.toggle("tab-active", b.dataset.tab === "analyze"));
      $$(".panel").forEach((p) => p.classList.toggle("panel-active", p.id === "tab-analyze"));
      renderResult(lastResult);
    }
  });

  async function refreshDiagnostics() {
    try {
      const [h, c] = await Promise.all([
        fetch("/api/health").then((r) => r.json()),
        fetch("/api/config").then((r) => r.json()),
      ]);
      $("#diag-output").textContent = JSON.stringify(h, null, 2);
      $("#diag-config").textContent = JSON.stringify(c, null, 2);
    } catch (e) {
      $("#diag-output").textContent = `Błąd: ${e.message}`;
    }
  }

  $("#diag-refresh").addEventListener("click", refreshDiagnostics);

  function debounce(fn, delay) {
    let t;
    return (...args) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...args), delay);
    };
  }

  function escapeHtml(s) {
    if (s == null) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function escapeAttr(s) {
    return escapeHtml(s).replace(/'/g, "&#039;");
  }

  refreshHealth();
  setInterval(refreshHealth, 60_000);
})();
