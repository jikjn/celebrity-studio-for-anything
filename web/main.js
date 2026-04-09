const providersEl = document.getElementById("providers");
const statusBox = document.getElementById("statusBox");
const selectedChips = document.getElementById("selectedChips");
const synthesisEl = document.getElementById("synthesis");
const timelineEl = document.getElementById("timeline");
const scenarioIdEl = document.getElementById("scenarioId");
const defaultProviderIdInput = document.getElementById("defaultProviderId");
const leaderProviderIdInput = document.getElementById("leaderProviderId");
let graph = null;
let modelCatalog = {};
let providerMeta = {
  openai_compatible: { requires_api_key: true },
  codex_cli: { requires_api_key: false },
};
let defaultModels = {
  openai_compatible: "gpt-4.1",
  codex_cli: "gpt-5.3-codex",
};

function setStatus(text, type = "normal") {
  statusBox.textContent = text;
  statusBox.className = type === "error" ? "status error" : type === "ok" ? "status ok" : "status";
}

function htmlEscape(text) {
  return String(text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function currentProviderIds() {
  return Array.from(providersEl.querySelectorAll(".provider-card [data-key='provider_id']"))
    .map((el) => el.value.trim())
    .filter(Boolean);
}

function refreshProviderDefaults() {
  const ids = currentProviderIds();
  if (!ids.length) {
    defaultProviderIdInput.value = "";
    leaderProviderIdInput.value = "";
    return;
  }
  if (!defaultProviderIdInput.value.trim() || !ids.includes(defaultProviderIdInput.value.trim())) {
    defaultProviderIdInput.value = ids[0];
  }
  if (leaderProviderIdInput.value.trim() && !ids.includes(leaderProviderIdInput.value.trim())) {
    leaderProviderIdInput.value = "";
  }
}

function providerCard(defaults = {}) {
  const card = document.createElement("div");
  card.className = "provider-card";
  const headersJson = defaults.extra_headers ? JSON.stringify(defaults.extra_headers) : "{}";

  card.innerHTML = `
    <div class="row">
      <div class="field">
        <label>provider_id</label>
        <input data-key="provider_id" value="${defaults.provider_id || ""}" placeholder="default">
      </div>
      <div class="field">
        <label>provider_type</label>
        <select data-key="provider_type">
          <option value="openai_compatible">openai_compatible</option>
          <option value="codex_cli">codex_cli</option>
        </select>
      </div>
    </div>

    <div class="row">
      <div class="field">
        <label>model</label>
        <input data-key="model" value="${defaults.model || ""}" placeholder="freeform model id">
        <div class="chips" data-role="model-suggestions"></div>
      </div>
      <div class="field">
        <label>temperature</label>
        <input data-key="temperature" type="number" step="0.05" value="${defaults.temperature ?? 0.35}">
      </div>
    </div>

    <div class="field">
      <label>base_url</label>
      <input data-key="base_url" value="${defaults.base_url || ""}" placeholder="https://...">
    </div>

    <div class="field">
      <label>api_key / token (optional for codex_cli)</label>
      <input data-key="api_key" value="${defaults.api_key || ""}" placeholder="sk-...">
    </div>

    <div class="field">
      <label>extra_headers (JSON)</label>
      <input data-key="extra_headers_json" value='${headersJson.replace(/'/g, "&apos;")}' placeholder='{"X-Any-Header":"value"}'>
    </div>

    <button class="btn btn-danger remove-provider">Remove</button>
  `;

  card.querySelector("select[data-key='provider_type']").value = defaults.provider_type || "openai_compatible";
  card.querySelector("select[data-key='provider_type']").addEventListener("change", () => {
    renderModelSuggestions(card);
  });

  card.querySelector(".remove-provider").addEventListener("click", () => {
    card.remove();
    refreshProviderDefaults();
  });

  card.querySelector("input[data-key='provider_id']").addEventListener("change", refreshProviderDefaults);
  renderModelSuggestions(card);
  return card;
}

function renderModelSuggestions(card) {
  const type = card.querySelector("select[data-key='provider_type']").value;
  const suggestionsEl = card.querySelector("[data-role='model-suggestions']");
  const modelInput = card.querySelector("input[data-key='model']");
  const keyField = card.querySelector("input[data-key='api_key']");
  const keyLabel = keyField?.closest(".field")?.querySelector("label");
  const requiresApiKey = Boolean(providerMeta[type]?.requires_api_key);
  if (keyLabel) {
    keyLabel.textContent = requiresApiKey ? "api_key / token (required)" : "api_key / token (optional for codex_cli)";
  }
  if (!suggestionsEl) return;
  const models = modelCatalog[type] || [];
  suggestionsEl.innerHTML = models
    .map((name) => `<button type="button" class="btn btn-alt" data-model-pick="${htmlEscape(name)}" style="padding:4px 8px;font-size:11px;">${htmlEscape(name)}</button>`)
    .join("");
  if (modelInput && !modelInput.value.trim() && defaultModels[type]) {
    modelInput.value = defaultModels[type];
  }
  suggestionsEl.querySelectorAll("[data-model-pick]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const value = btn.getAttribute("data-model-pick");
      if (modelInput) {
        modelInput.value = value || "";
      }
    });
  });
}

function collectProviders() {
  const cards = Array.from(providersEl.querySelectorAll(".provider-card"));
  return cards
    .map((card) => {
      const obj = {};
      card.querySelectorAll("[data-key]").forEach((input) => {
        const key = input.getAttribute("data-key");
        obj[key] = input.value;
      });

      obj.provider_id = (obj.provider_id || "").trim();
      obj.temperature = Number(obj.temperature || 0.35);
      obj.timeout_s = obj.provider_type === "codex_cli" ? 300 : 120;

      try {
        obj.extra_headers = obj.extra_headers_json ? JSON.parse(obj.extra_headers_json) : {};
      } catch {
        obj.extra_headers = {};
      }
      delete obj.extra_headers_json;
      return obj;
    })
    .filter((x) => {
      if (!x.provider_id) {
        return false;
      }
      const requiresApiKey = Boolean(providerMeta[x.provider_type]?.requires_api_key);
      return !requiresApiKey || Boolean(x.api_key);
    });
}

function renderSelected(items) {
  selectedChips.innerHTML = "";
  (items || []).forEach((name) => {
    const span = document.createElement("span");
    span.className = "chip";
    span.textContent = name;
    selectedChips.appendChild(span);
  });
}

function makeList(title, arr) {
  return `<div style="margin-bottom:8px;"><div style="font-weight:700;font-size:12px;color:#365849;">${title}</div><ul>${
    (arr || []).map((x) => `<li>${htmlEscape(x)}</li>`).join("")
  }</ul></div>`;
}

function renderSynthesis(result) {
  const synthesis = result?.debate?.synthesis || {};
  synthesisEl.innerHTML =
    makeList("Consensus", synthesis.consensus_points) +
    makeList("Disagreement", synthesis.disagreement_points) +
    makeList("Reservations", synthesis.reservation_points) +
    `<div style="font-size:13px;line-height:1.5;background:#eef7f2;border:1px solid #cbe3d6;border-radius:10px;padding:8px;"><b>Final synthesis:</b> ${htmlEscape(
      synthesis.final_synthesis || ""
    )}</div>`;
}

function renderTimeline(result) {
  const messages = result?.debate?.messages || [];
  timelineEl.innerHTML = messages
    .map(
      (m) => `
      <div class="msg">
        <div class="meta">[R${m.round_no}] ${htmlEscape(m.phase)} | ${htmlEscape(m.type)} | ${htmlEscape(m.from_agent)} -> ${htmlEscape(m.to_agent)}</div>
        <div class="content">${htmlEscape(m.content || "")}</div>
      </div>
    `,
    )
    .join("");
}

function renderChallengeGraph(result) {
  const edges = result?.debate?.challenge_edges || [];
  const members = result?.studio?.members || [];

  const nodes = members.map((m) => ({
    data: {
      id: m.celebrity_name,
      label: `${m.celebrity_name}\n${m.role_in_studio}`,
    },
  }));

  const edgeEls = edges.map((e, idx) => ({
    data: {
      id: `e${idx}`,
      source: e.source,
      target: e.target,
      count: Number(e.count || 1),
      label: `x${e.count}`,
    },
  }));

  if (graph) {
    graph.destroy();
  }

  graph = cytoscape({
    container: document.getElementById("challengeGraph"),
    elements: { nodes, edges: edgeEls },
    style: [
      {
        selector: "node",
        style: {
          "background-color": "#0f8f67",
          color: "#0f2f24",
          "font-size": 11,
          label: "data(label)",
          "text-valign": "center",
          "text-halign": "center",
          "text-wrap": "wrap",
          "text-max-width": 100,
          "border-width": 1,
          "border-color": "#d3ece1",
          width: 70,
          height: 70,
        },
      },
      {
        selector: "edge",
        style: {
          width: "mapData(count, 1, 8, 1, 6)",
          "line-color": "#d0632a",
          "target-arrow-color": "#d0632a",
          "target-arrow-shape": "triangle",
          label: "data(label)",
          "font-size": 10,
          color: "#7d3d1c",
          "curve-style": "bezier",
        },
      },
    ],
    layout: { name: "cose", fit: true, padding: 12, animate: false },
  });
}

async function runStudio() {
  const query = document.getElementById("query").value.trim();
  if (!query) {
    setStatus("Please provide a scenario.", "error");
    return;
  }

  const providers = collectProviders();
  if (!providers.length) {
    setStatus("Configure at least one provider. Providers marked as key-required must include api_key.", "error");
    return;
  }

  const providerIds = providers.map((p) => p.provider_id);
  const defaultProviderId = defaultProviderIdInput.value.trim() || providers[0].provider_id;
  if (!providerIds.includes(defaultProviderId)) {
    setStatus(`default_provider_id '${defaultProviderId}' is not in provider list.`, "error");
    return;
  }

  const leaderProviderId = leaderProviderIdInput.value.trim();
  if (leaderProviderId && !providerIds.includes(leaderProviderId)) {
    setStatus(`leader_provider_id '${leaderProviderId}' is not in provider list.`, "error");
    return;
  }
  const minTurnsPerMember = Math.max(1, Number(document.getElementById("minTurnsPerMember").value || 5) || 5);
  const turnLength = document.getElementById("turnLength").value || "long";
  const interactionStyle =
    document.getElementById("interactionStyle").value.trim() ||
    "像同桌沙龙一样自由交流，允许质疑、支持、反驳、补充，不走模板话术，优先真实观点碰撞。";

  const runtime = {
    providers,
    default_provider_id: defaultProviderId,
    leader_provider_id: leaderProviderId || defaultProviderId,
    assignment_strategy: document.getElementById("assignmentStrategy").value,
    strict_online: document.getElementById("strictOnline").value === "true",
    realtime_distill: document.getElementById("realtimeDistill").value === "true",
    discussion: {
      mode: "free_salon",
      min_turns_per_member: minTurnsPerMember,
      turn_length: turnLength,
      interaction_style: interactionStyle,
    },
  };

  const payload = {
    query,
    team_size: Number(document.getElementById("teamSize").value || 0) || null,
    language_hint: document.getElementById("languageHint").value.trim() || null,
    include_celebrities: document
      .getElementById("includeCelebrities")
      .value.split(",")
      .map((x) => x.trim())
      .filter(Boolean),
    exclude_celebrities: document
      .getElementById("excludeCelebrities")
      .value.split(",")
      .map((x) => x.trim())
      .filter(Boolean),
    selection_mode: document.getElementById("selectionMode").value || "auto",
    runtime,
  };

  setStatus("Running: dynamic retrieval, realtime distillation, and Open Studio Field flow...");

  try {
    const resp = await fetch("/api/studio/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }

    const data = await resp.json();
    setStatus(`Completed: ${data.scenario_id}`, "ok");
    scenarioIdEl.textContent = data.scenario_id;
    renderSelected(data.selected);
    renderSynthesis(data.result);
    renderTimeline(data.result);
    renderChallengeGraph(data.result);
  } catch (err) {
    setStatus(`Run failed: ${err.message || err}`, "error");
  }
}

function addDefaultProvider() {
  providersEl.appendChild(
    providerCard({
      provider_id: "codex-local",
      provider_type: "codex_cli",
      model: "gpt-5.3-codex",
      temperature: 0.0,
    }),
  );
  refreshProviderDefaults();
}

async function useCodexPreset() {
  try {
    const resp = await fetch("/api/provider/preset/codex-cli");
    const preset = await resp.json();
    providersEl.innerHTML = "";
    preset.providers.forEach((p) => providersEl.appendChild(providerCard(p)));
    defaultProviderIdInput.value = preset.default_provider_id || (preset.providers[0]?.provider_id || "");
    leaderProviderIdInput.value = preset.leader_provider_id || defaultProviderIdInput.value;
    if (preset.discussion) {
      document.getElementById("minTurnsPerMember").value = String(preset.discussion.min_turns_per_member ?? 5);
      document.getElementById("turnLength").value = preset.discussion.turn_length || "long";
      document.getElementById("interactionStyle").value =
        preset.discussion.interaction_style ||
        "像同桌沙龙一样自由交流，允许质疑、支持、反驳、补充，不走模板话术，优先真实观点碰撞。";
    }
    setStatus("Loaded Codex CLI preset. No external API key is required for local Codex login mode.", "ok");
  } catch (err) {
    setStatus(`Failed to load preset: ${err.message || err}`, "error");
  }
}

async function loadModelCatalog() {
  try {
    const resp = await fetch("/api/provider/model-catalog");
    if (!resp.ok) return;
    const data = await resp.json();
    if (data && data.popular_models && typeof data.popular_models === "object") {
      modelCatalog = data.popular_models;
    }
    if (data && data.default_models && typeof data.default_models === "object") {
      defaultModels = data.default_models;
    }
    if (data && Array.isArray(data.provider_types)) {
      const nextMeta = {};
      data.provider_types.forEach((item) => {
        if (!item || !item.id) return;
        nextMeta[item.id] = { requires_api_key: Boolean(item.requires_api_key) };
      });
      if (Object.keys(nextMeta).length) {
        providerMeta = nextMeta;
      }
    }
    providersEl.querySelectorAll(".provider-card").forEach((card) => renderModelSuggestions(card));
  } catch {
    // keep local fallback catalog
  }
}

document.getElementById("addProvider").addEventListener("click", () => {
  providersEl.appendChild(providerCard({ provider_id: `provider-${Date.now()}` }));
  refreshProviderDefaults();
});

document.getElementById("runBtn").addEventListener("click", runStudio);
document.getElementById("useCodexPreset").addEventListener("click", useCodexPreset);

document.getElementById("fillDemo").addEventListener("click", () => {
  document.getElementById("query").value =
    "I want a Cantonese song blending classical Chinese aesthetics and cyberpunk worldbuilding. " +
    "I need concrete multi-agent free-salon synthesis, not generic suggestions.";
  document.getElementById("teamSize").value = "6";
  document.getElementById("selectionMode").value = "prefer";
  document.getElementById("minTurnsPerMember").value = "5";
  document.getElementById("turnLength").value = "long";
  document.getElementById("interactionStyle").value =
    "像同桌沙龙一样自由交流，允许质疑、支持、反驳、补充，不走模板话术，优先真实观点碰撞。";
  document.getElementById("includeCelebrities").value = "Jay Chou, James Wong, Wong Kar-wai, Lin Xi";
  document.getElementById("excludeCelebrities").value = "Donald Trump, Winston Churchill, Cao Cao";
});

addDefaultProvider();
loadModelCatalog();
