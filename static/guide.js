"use strict";
/* Champ guide view: pick any champion (full roster, not just ones you've
   played) and see/edit a guide — Markdown notes, patch version, and one or
   more full rune pages (primary tree + keystone + 3 minors, secondary tree +
   2 minors, 3 stat shards) — for every matchup that champion has faced, or
   add one for a matchup not yet played.
   Uses globals from app.js: $, getJSON, escapeHtml, displayName, champIcon,
   wrCell, renderNotes, accountParams, setMainView. Uses roster/
   loadChampionRoster/champDisplay from blocks.js for champion-name
   resolution and the shared #champ-list datalist. Called from matchups.js
   via openGuide(). */

const guideState = {
  wired: false,
  myChampion: "",
  matchups: [],   // stats rows for myChampion: {opp_champion, games, winrate, ...}
  guide: {},      // opp_champion -> {notes, runes: [rune page, ...], patch_version}
  editing: null,  // opp_champion whose editor is open
  draft: null,    // working copy of the guide being edited: {notes, patch_version, runes}
  openRuneIndex: null, // index into draft.runes currently expanded in the picker
  pendingFocus: null,  // opp_champion to focus once the next load completes (deep link)
};

const RUNE_TREES = [];
const SHARD_ROWS = [];

async function loadRuneTrees() {
  if (RUNE_TREES.length) return;
  const data = await getJSON("/runes.json");
  RUNE_TREES.push(...data.trees);
  SHARD_ROWS.push(...data.shardRows);
}

function runeIconUrl(icon) { return `https://ddragon.leagueoflegends.com/cdn/img/${icon}`; }
function shardIconUrl(icon) {
  return `https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/perk-images/statmods/${icon}`;
}

function treeByName(name) { return RUNE_TREES.find((t) => t.name === name); }

// row index (1-3) of a rune within a tree's non-keystone rows, or null
function rowIndexOf(tree, runeName) {
  if (!tree) return null;
  const row = tree.rows.find((r) => r.slot !== "keystone" && r.runes.some((x) => x.name === runeName));
  return row ? row.slot : null;
}

function runeIcon(name, tree) {
  if (!tree) return "";
  const rune = tree.rows.flatMap((r) => r.runes).find((x) => x.name === name);
  return rune ? rune.icon : "";
}

function emptyGuide() { return { notes: "", runes: [], patch_version: "" }; }
function emptyRunePage() {
  return { label: "", primary_tree: "", keystone: "", primary_runes: ["", "", ""],
           secondary_tree: "", secondary_runes: [], shards: ["", "", ""] };
}
function pageHasContent(p) {
  return Boolean(p.primary_tree || p.keystone || p.secondary_tree
    || p.primary_runes.some(Boolean) || p.secondary_runes.length || p.shards.some(Boolean));
}

function guideFor(champ) {
  const g = guideState.guide[champ];
  return g ? { ...emptyGuide(), ...g } : emptyGuide();
}

// ---------- init / load ----------

async function initGuide() {
  if (!guideState.wired) {
    guideState.wired = true;
    $("#guide-champion").addEventListener("change", (e) => {
      guideState.myChampion = e.target.value;
      guideState.editing = null;
      loadGuide();
    });
    $("#guide-add-form").addEventListener("submit", (e) => {
      e.preventDefault();
      addGuideMatchup();
    });
  }
  await loadChampionRoster(); // loadGuideChampionOptions needs the full roster
  await Promise.all([loadGuideChampionOptions(), loadRuneTrees()]);
  await loadGuide();
  if (guideState.pendingFocus) {
    addOrFocusMatchup(guideState.pendingFocus);
    guideState.pendingFocus = null;
    renderGuide();
  }
}

async function loadGuideChampionOptions() {
  // full roster, so you can prep a guide for a champion you haven't (or
  // haven't yet) played — default the initial selection to one you have
  // played, when available, so the page opens on real data
  const all = [...roster.nameById.keys()].sort(
    (a, b) => champDisplay(a).localeCompare(champDisplay(b)));
  if (!guideState.myChampion) {
    const played = await getJSON(`/api/filters?${accountParams()}`);
    guideState.myChampion = played.champions[0] || all[0] || "";
  }
  $("#guide-champion").innerHTML = all.length
    ? all.map((c) =>
        `<option value="${c}" ${c === guideState.myChampion ? "selected" : ""}>${escapeHtml(champDisplay(c))}</option>`).join("")
    : `<option value="">No champions found</option>`;
}

async function loadGuide() {
  if (!guideState.myChampion) {
    guideState.matchups = [];
    guideState.guide = {};
    renderGuide();
    return;
  }
  const [matchups, guide] = await Promise.all([
    getJSON(`/api/stats/matchups?${accountParams()}&champion=${encodeURIComponent(guideState.myChampion)}&min_games=1`),
    getJSON(`/api/matchups/notes?my_champion=${encodeURIComponent(guideState.myChampion)}`),
  ]);
  guideState.matchups = matchups;
  guideState.guide = guide;
  renderGuide();
}

function addGuideMatchup() {
  const typed = $("#guide-add-input").value.trim();
  if (!typed) return;
  const champ = roster.byLookup.get(typed.toLowerCase());
  if (!champ) {
    $("#guide-add-status").textContent = `"${typed}" is not a champion`;
    return;
  }
  $("#guide-add-input").value = "";
  $("#guide-add-status").textContent = "";
  addOrFocusMatchup(champ);
  renderGuide();
}

function addOrFocusMatchup(champ) {
  if (!guideState.matchups.some((m) => m.opp_champion === champ)) {
    guideState.matchups.push({ opp_champion: champ, games: 0, winrate: null, added: true });
  }
  startEditing(champ);
}

function startEditing(champ) {
  guideState.editing = champ;
  guideState.draft = guideFor(champ);
  guideState.draft.runes = guideState.draft.runes.map((p) => ({ ...emptyRunePage(), ...p }));
  guideState.openRuneIndex = null;
}

// ---------- rune page picker ----------

function treePicker(role, selected, excluded) {
  // role: "primary" | "secondary" — which field this click sets
  return `<div class="rune-tree-picker">${RUNE_TREES.map((t) => {
    if (excluded && t.name === excluded) return "";
    return `<button type="button" class="rune-tree-btn ${t.name === selected ? "active" : ""}"
        data-role="${role}-tree" data-tree="${escapeHtml(t.name)}" title="${escapeHtml(t.name)}">
      <img src="${runeIconUrl(t.icon)}" alt="${escapeHtml(t.name)}" width="28" height="28">
      <span>${escapeHtml(t.name)}</span>
    </button>`;
  }).join("")}</div>`;
}

function runeButton(role, row, rune, active) {
  return `<button type="button" class="rune-btn ${active ? "active" : ""}"
      data-role="${role}" data-row="${row}" data-rune="${escapeHtml(rune.name)}" title="${escapeHtml(rune.name)}">
    <img src="${runeIconUrl(rune.icon)}" alt="${escapeHtml(rune.name)}" width="26" height="26">
  </button>`;
}

function primaryRunesPicker(page) {
  const tree = treeByName(page.primary_tree);
  if (!tree) return "";
  const keystoneRow = tree.rows.find((r) => r.slot === "keystone");
  const regularRows = tree.rows.filter((r) => r.slot !== "keystone");
  return `<div class="rune-row rune-row-keystone">${
      keystoneRow.runes.map((r) => runeButton("keystone", "keystone", r, r.name === page.keystone)).join("")}</div>
    ${regularRows.map((row) => `<div class="rune-row">${
      row.runes.map((r) => runeButton("primary-rune", row.slot, r, page.primary_runes[row.slot - 1] === r.name)).join("")}</div>`).join("")}`;
}

function secondaryRunesPicker(page) {
  const tree = treeByName(page.secondary_tree);
  if (!tree) return "";
  const regularRows = tree.rows.filter((r) => r.slot !== "keystone");
  return `<p class="muted rune-hint">Pick 2, from different rows</p>
    ${regularRows.map((row) => `<div class="rune-row">${
      row.runes.map((r) => runeButton("secondary-rune", row.slot, r, page.secondary_runes.includes(r.name))).join("")}</div>`).join("")}`;
}

function shardsPicker(page) {
  return SHARD_ROWS.map((row, i) => `<div class="rune-row">${
    row.shards.map((s) => `<button type="button" class="rune-btn shard-btn ${page.shards[i] === s.name ? "active" : ""}"
        data-role="shard" data-row="${i}" data-shard="${escapeHtml(s.name)}" title="${escapeHtml(s.name)}">
      <img src="${shardIconUrl(s.icon)}" alt="${escapeHtml(s.name)}" width="20" height="20">
    </button>`).join("")}</div>`).join("");
}

function runePageEditor(index) {
  const page = guideState.draft.runes[index];
  return `<div class="rune-page-editor" data-index="${index}">
    <input type="text" class="rune-page-label" data-index="${index}" placeholder="Label (optional) — e.g. “vs poke”"
      value="${escapeHtml(page.label)}">
    <div class="rune-page-cols">
      <div class="rune-tree-col">
        <h5>Primary tree</h5>
        ${treePicker("primary", page.primary_tree, page.secondary_tree)}
        ${primaryRunesPicker(page)}
      </div>
      <div class="rune-tree-col">
        <h5>Secondary tree</h5>
        ${treePicker("secondary", page.secondary_tree, page.primary_tree)}
        ${secondaryRunesPicker(page)}
      </div>
    </div>
    <h5>Stat shards</h5>
    ${shardsPicker(page)}
    <div class="session-actions">
      <button type="button" class="preset rune-page-done" data-index="${index}">Done</button>
      <button type="button" class="preset rune-page-remove" data-index="${index}">Remove page</button>
    </div>
  </div>`;
}

function runePageSummary(index) {
  const page = guideState.draft.runes[index];
  const primaryTree = treeByName(page.primary_tree);
  const secondaryTree = treeByName(page.secondary_tree);
  const keystoneIcon = page.keystone ? runeIcon(page.keystone, primaryTree) : "";
  const label = page.label || `Page ${index + 1}`;
  const empty = !pageHasContent(page);
  return `<div class="rune-page-chip">
    <div class="rune-page-chip-icons">
      ${keystoneIcon ? `<img src="${runeIconUrl(keystoneIcon)}" alt="${escapeHtml(page.keystone)}" width="28" height="28" title="${escapeHtml(page.keystone)}">` : ""}
      ${secondaryTree ? `<img src="${runeIconUrl(secondaryTree.icon)}" alt="${escapeHtml(secondaryTree.name)}" width="20" height="20" title="${escapeHtml(secondaryTree.name)}" class="rune-page-chip-secondary">` : ""}
    </div>
    <div class="rune-page-chip-text">
      <strong>${escapeHtml(label)}</strong>
      ${empty ? `<span class="muted">empty — click edit to build a page</span>` : `<span class="muted">${
        [page.keystone, page.secondary_tree].filter(Boolean).join(" · ")}</span>`}
    </div>
    <button type="button" class="preset icon-btn rune-page-edit" data-index="${index}"
      title="Edit rune page" aria-label="Edit rune page">✎</button>
    <button type="button" class="preset icon-btn rune-page-remove" data-index="${index}"
      title="Remove rune page" aria-label="Remove rune page">✕</button>
  </div>`;
}

function runePagesBuilder() {
  const pages = guideState.draft.runes;
  const chips = pages.map((_, i) =>
    guideState.openRuneIndex === i ? runePageEditor(i) : runePageSummary(i)).join("");
  return `<div class="rune-pages-builder">
    <h4>Rune pages</h4>
    ${chips || `<p class="muted">No rune pages yet.</p>`}
    <button type="button" class="preset rune-page-add">+ Add rune page</button>
  </div>`;
}

// ---------- read-only display ----------

function runePageCard(page, i) {
  const primaryTree = treeByName(page.primary_tree);
  const secondaryTree = treeByName(page.secondary_tree);
  const primaryMinorIcons = page.primary_runes.map((name) =>
    name ? `<img src="${runeIconUrl(runeIcon(name, primaryTree))}" alt="${escapeHtml(name)}" title="${escapeHtml(name)}" width="20" height="20">` : "").join("");
  const secondaryMinorIcons = page.secondary_runes.map((name) =>
    `<img src="${runeIconUrl(runeIcon(name, secondaryTree))}" alt="${escapeHtml(name)}" title="${escapeHtml(name)}" width="20" height="20">`).join("");
  const shardIcons = page.shards.map((name, r) => {
    if (!name) return "";
    const shard = SHARD_ROWS[r].shards.find((s) => s.name === name);
    return shard ? `<img src="${shardIconUrl(shard.icon)}" alt="${escapeHtml(name)}" title="${escapeHtml(name)}" width="16" height="16">` : "";
  }).join("");
  return `<div class="rune-page-card">
    <div class="rune-page-title${page.label ? "" : " muted"}">${escapeHtml(page.label || `Page ${i + 1}`)}</div>
    <div class="rune-page-display">
      ${page.keystone ? `<img class="rune-keystone-icon" src="${runeIconUrl(runeIcon(page.keystone, primaryTree))}" alt="${escapeHtml(page.keystone)}" title="${escapeHtml(page.keystone)}" width="34" height="34">` : ""}
      <div class="rune-page-minors">${primaryMinorIcons}</div>
      ${secondaryTree ? `<img class="rune-tree-icon" src="${runeIconUrl(secondaryTree.icon)}" alt="${escapeHtml(secondaryTree.name)}" title="${escapeHtml(secondaryTree.name)}" width="24" height="24">` : ""}
      <div class="rune-page-minors">${secondaryMinorIcons}</div>
      <div class="rune-page-shards">${shardIcons}</div>
    </div>
  </div>`;
}

function runePagesDisplay(runes) {
  if (!runes || !runes.length) return "";
  return `<div class="rune-pages-display">${runes.map(runePageCard).join("")}</div>`;
}

// ---------- matchup rows ----------

function guideRow(m) {
  const champ = m.opp_champion;
  const editing = guideState.editing === champ;
  const statLine = m.games
    ? `<span class="muted guide-stat">${m.games} games · ${wrCell(m.winrate)}</span>`
    : `<span class="muted guide-stat">Not played yet</span>`;
  let body;
  if (editing) {
    const draft = guideState.draft;
    body = `${runePagesBuilder()}
      <label class="filter-label" for="guide-patch">Patch</label>
      <input type="text" id="guide-patch" placeholder="e.g. 14.14" value="${escapeHtml(draft.patch_version)}" style="max-width:10em">
      <label class="filter-label" for="guide-notes">How to play this matchup</label>
      <textarea id="guide-notes" rows="8"
        placeholder="Markdown supported — game plan, power spikes, bans…">${escapeHtml(draft.notes)}</textarea>
      <div class="session-actions">
        <button class="preset guide-save" data-opp="${escapeHtml(champ)}">Save</button>
        <button class="preset guide-cancel">Cancel</button>
        <span class="muted guide-status"></span>
      </div>`;
  } else {
    const { notes, runes, patch_version } = guideFor(champ);
    const patchLine = patch_version
      ? `<div class="muted mu-guide-patch">Patch ${escapeHtml(patch_version)}</div>` : "";
    const notesBody = notes ? `<div class="md-body">${renderNotes(notes)}</div>` : "";
    const hasAny = notes || (runes && runes.length) || patch_version;
    body = `${runePagesDisplay(runes)}${patchLine}${notesBody}${
      hasAny ? "" : `<p class="muted">No guide yet — click ✎ to add one.</p>`}`;
  }
  return `<div class="mu-notes mu-guide guide-row" data-opp="${escapeHtml(champ)}">
    <div class="mu-notes-head">
      <h4>${champIcon(champ)}${displayName(champ)}</h4>
      ${statLine}
      ${editing ? "" : `<button class="preset icon-btn guide-edit" data-opp="${escapeHtml(champ)}"
        title="Edit champ guide" aria-label="Edit champ guide">✎</button>`}
    </div>
    ${body}
  </div>`;
}

function renderGuide() {
  const target = $("#guide-list");
  if (!guideState.myChampion) {
    target.innerHTML = `<div class="empty">Pick a champion above to see or build its champ guide.</div>`;
    return;
  }
  const rows = [...guideState.matchups].sort((a, b) => {
    // guided/freshly-added matchups float to the top, then most-played
    const aHas = Boolean(guideState.guide[a.opp_champion]) || a.added;
    const bHas = Boolean(guideState.guide[b.opp_champion]) || b.added;
    if (aHas !== bHas) return aHas ? -1 : 1;
    return (b.games || 0) - (a.games || 0);
  });
  target.innerHTML = rows.length
    ? rows.map(guideRow).join("")
    : `<div class="empty">No matchups for ${displayName(guideState.myChampion)} yet — add one below.</div>`;
  wireGuideHandlers(target);
  if (guideState.editing) {
    const row = target.querySelector(`.guide-row[data-opp="${guideState.editing}"]`);
    if (row) row.scrollIntoView({ block: "center", behavior: "smooth" });
  }
}

// ---------- event wiring ----------

function wireGuideHandlers(target) {
  target.querySelectorAll(".guide-edit").forEach((btn) =>
    btn.addEventListener("click", () => { startEditing(btn.dataset.opp); renderGuide(); }));
  target.querySelectorAll(".guide-cancel").forEach((btn) =>
    btn.addEventListener("click", () => {
      guideState.editing = null;
      guideState.draft = null;
      guideState.openRuneIndex = null;
      renderGuide();
    }));
  target.querySelectorAll(".guide-save").forEach((btn) =>
    btn.addEventListener("click", async () => {
      const opp = btn.dataset.opp;
      const payload = {
        notes: $("#guide-notes").value,
        patch_version: $("#guide-patch").value,
        runes: guideState.draft.runes.filter(pageHasContent),
      };
      const response = await fetch(
        `/api/matchups/notes/${encodeURIComponent(guideState.myChampion)}/${encodeURIComponent(opp)}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        btn.parentElement.querySelector(".guide-status").textContent =
          body.detail || `error ${response.status}`;
        return;
      }
      const hasAny = payload.notes.trim() || payload.runes.length || payload.patch_version.trim();
      if (hasAny) guideState.guide[opp] = payload;
      else delete guideState.guide[opp];
      guideState.editing = null;
      guideState.draft = null;
      guideState.openRuneIndex = null;
      renderGuide();
    }));

  // rune page builder — only present while editing
  target.querySelectorAll(".rune-page-add").forEach((btn) =>
    btn.addEventListener("click", () => {
      guideState.draft.runes.push(emptyRunePage());
      guideState.openRuneIndex = guideState.draft.runes.length - 1;
      renderGuide();
    }));
  target.querySelectorAll(".rune-page-edit").forEach((btn) =>
    btn.addEventListener("click", () => {
      guideState.openRuneIndex = +btn.dataset.index;
      renderGuide();
    }));
  target.querySelectorAll(".rune-page-done").forEach((btn) =>
    btn.addEventListener("click", () => { guideState.openRuneIndex = null; renderGuide(); }));
  target.querySelectorAll(".rune-page-remove").forEach((btn) =>
    btn.addEventListener("click", () => {
      const i = +btn.dataset.index;
      guideState.draft.runes.splice(i, 1);
      if (guideState.openRuneIndex === i) guideState.openRuneIndex = null;
      else if (guideState.openRuneIndex > i) guideState.openRuneIndex -= 1;
      renderGuide();
    }));
  target.querySelectorAll(".rune-page-label").forEach((input) =>
    input.addEventListener("input", () => {
      guideState.draft.runes[+input.dataset.index].label = input.value;
      // no re-render needed — avoids losing focus mid-type
    }));
  target.querySelectorAll("[data-role='primary-tree']").forEach((btn) =>
    btn.addEventListener("click", () => {
      const page = guideState.draft.runes[guideState.openRuneIndex];
      if (page.primary_tree === btn.dataset.tree) return;
      page.primary_tree = btn.dataset.tree;
      page.keystone = "";
      page.primary_runes = ["", "", ""];
      renderGuide();
    }));
  target.querySelectorAll("[data-role='secondary-tree']").forEach((btn) =>
    btn.addEventListener("click", () => {
      const page = guideState.draft.runes[guideState.openRuneIndex];
      if (page.secondary_tree === btn.dataset.tree) return;
      page.secondary_tree = btn.dataset.tree;
      page.secondary_runes = [];
      renderGuide();
    }));
  target.querySelectorAll("[data-role='keystone']").forEach((btn) =>
    btn.addEventListener("click", () => {
      const page = guideState.draft.runes[guideState.openRuneIndex];
      page.keystone = page.keystone === btn.dataset.rune ? "" : btn.dataset.rune;
      renderGuide();
    }));
  target.querySelectorAll("[data-role='primary-rune']").forEach((btn) =>
    btn.addEventListener("click", () => {
      const page = guideState.draft.runes[guideState.openRuneIndex];
      const row = +btn.dataset.row - 1;
      page.primary_runes[row] = page.primary_runes[row] === btn.dataset.rune ? "" : btn.dataset.rune;
      renderGuide();
    }));
  target.querySelectorAll("[data-role='secondary-rune']").forEach((btn) =>
    btn.addEventListener("click", () => {
      const page = guideState.draft.runes[guideState.openRuneIndex];
      const tree = treeByName(page.secondary_tree);
      const name = btn.dataset.rune;
      const rowIdx = rowIndexOf(tree, name);
      if (page.secondary_runes.includes(name)) {
        page.secondary_runes = page.secondary_runes.filter((n) => n !== name);
      } else {
        const withoutThisRow = page.secondary_runes.filter((n) => rowIndexOf(tree, n) !== rowIdx);
        if (withoutThisRow.length < 2) page.secondary_runes = [...withoutThisRow, name];
      }
      renderGuide();
    }));
  target.querySelectorAll("[data-role='shard']").forEach((btn) =>
    btn.addEventListener("click", () => {
      const page = guideState.draft.runes[guideState.openRuneIndex];
      const row = +btn.dataset.row;
      page.shards[row] = page.shards[row] === btn.dataset.shard ? "" : btn.dataset.shard;
      renderGuide();
    }));
}

// deep link from the Matchups table's 📖 button — sets pending state and
// lets setMainView's normal initGuide() call apply it once loaded, so we
// don't race two concurrent initGuide() calls against each other
function openGuide(myChampion, oppChampion) {
  guideState.myChampion = myChampion;
  guideState.pendingFocus = oppChampion;
  setMainView("guide");
}
