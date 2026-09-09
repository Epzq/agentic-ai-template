(() => {
  "use strict";
  const data = JSON.parse(document.getElementById("proposal-data").textContent);
  const scenes = Array.from(document.querySelectorAll(".scene"));
  const nav = Array.from(document.querySelectorAll("[data-scene]"));
  const controls = document.querySelector(".present-controls");
  const present = document.getElementById("present");
  let active = 0;
  let presenting = false;

  function showScene(index) {
    active = Math.max(0, Math.min(scenes.length - 1, index));
    scenes.forEach((scene, i) => { scene.hidden = presenting && i !== active; });
    nav.forEach((button, i) => {
      if (i === active) button.setAttribute("aria-current", "step");
      else button.removeAttribute("aria-current");
    });
    document.getElementById("scene-status").textContent = `${active + 1} / ${scenes.length}`;
    document.getElementById("previous").disabled = active === 0;
    document.getElementById("next").disabled = active === scenes.length - 1;
  }

  function togglePresentation(on) {
    presenting = on;
    document.body.classList.toggle("presenting", on);
    present.setAttribute("aria-pressed", String(on));
    present.textContent = on ? "Exit presentation ↙" : "Present ↗";
    controls.hidden = !on;
    showScene(active);
    window.scrollTo({top: 0});
  }

  present.addEventListener("click", () => togglePresentation(!presenting));
  nav.forEach((button, i) => button.addEventListener("click", () => {
    showScene(i);
    if (!presenting) scenes[i].scrollIntoView({block: "start"});
  }));
  document.getElementById("previous").addEventListener("click", () => showScene(active - 1));
  document.getElementById("next").addEventListener("click", () => showScene(active + 1));
  document.getElementById("notes").addEventListener("click", event => {
    const visible = document.body.classList.toggle("show-notes");
    event.currentTarget.setAttribute("aria-pressed", String(visible));
  });
  document.addEventListener("keydown", event => {
    if (!presenting) return;
    if (event.key === "Escape") { togglePresentation(false); return; }
    // Toolbar focus must not disable navigation; sliders keep their own arrow keys.
    if (event.target.closest("input, textarea, select, [contenteditable='true']")) return;
    if (event.key === "ArrowRight") { event.preventDefault(); showScene(active + 1); }
    else if (event.key === "ArrowLeft") { event.preventDefault(); showScene(active - 1); }
  });

  const sliders = Array.from(document.querySelectorAll("input[data-metric]"));
  function updateScenario() {
    let total = 0;
    let unknown = false;
    sliders.forEach(input => {
      const key = input.dataset.metric;
      const value = input.disabled ? null : Number(input.value);
      document.getElementById(`out-${key}`).textContent = value === null ? "?" : String(value);
      if (value === null) unknown = true;
      else total += data.weights[key] * (key === "competition_risk" ? 100 - value : value);
    });
    const score = unknown ? null : Math.floor((total + 50) / 100);
    document.getElementById("scenario-score").textContent = score === null ? "?" : String(score);
    const delta = score === null ? null : score - data.overall_score;
    document.getElementById("scenario-delta").textContent = delta === null
      ? "More evidence needed" : delta === 0 ? "Baseline overall"
      : `${delta > 0 ? "+" : ""}${delta} vs original overall`;
  }
  sliders.forEach(input => input.addEventListener("input", updateScenario));
  document.getElementById("reset-scenario").addEventListener("click", () => {
    sliders.forEach(input => { input.value = String(data.scores[input.dataset.metric] ?? 0); });
    updateScenario();
  });

  document.querySelectorAll('a[href^="#source-"]').forEach(link => {
    link.addEventListener("click", () => {
      document.getElementById("evidence").open = true;
      document.getElementById(link.getAttribute("href").slice(1)).open = true;
    });
  });
  document.getElementById("download").addEventListener("click", () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {type: "application/json"}));
    const link = document.createElement("a");
    link.href = url;
    link.download = "proposal-presentation.json";
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  document.getElementById("print").addEventListener("click", () => window.print());
  showScene(0);
  updateScenario();
})();