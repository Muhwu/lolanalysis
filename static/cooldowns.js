"use strict";
/* Cooldown comparison popup (opened from the Matchups view): your champion's
   ability cooldowns on the left, the opponent's on the right. Each side has
   a level slider and a drag-to-reorder skill priority (R fixed at 6/11/16)
   that decide every spell's current rank, plus a list of haste sources
   (ability haste / ultimate ability haste — items, runes, buffs, whatever);
   reduced cooldowns render next to the base values. Spell data comes from
   DDragon's champion/<id>.json at open time (cached per session). Skill
   priority persists per champion in localStorage. Uses globals from app.js:
   state, $, getJSON, escapeHtml, champIcon, championOptions,
   ICON_NAME_FIXES. */

const SPELL_KEYS = ["Q", "W", "E", "R"];
const R_LEVELS = [6, 11, 16];

const cdState = {
  sides: { me: null, opp: null }, // {champ, level, order, haste[], detail, error}
  options: { me: "", opp: "" },   // champion <select> options per side
};

const champDetailCache = new Map();

async function loadChampionDetail(champ) {
  const id = ICON_NAME_FIXES[champ] || champ;
  if (champDetailCache.has(id)) return champDetailCache.get(id);
  const data = await getJSON(
    `https://ddragon.leagueoflegends.com/cdn/${state.ddragonVersion}/data/en_US/champion/${id}.json`);
  const detail = data.data[id] || Object.values(data.data)[0];
  champDetailCache.set(id, detail);
  return detail;
}

function savedSkillOrder(champ) {
  try {
    const raw = JSON.parse(localStorage.getItem(`cp-skill-order-${champ}`) || "null");
    if (Array.isArray(raw) && raw.length === 3
        && ["Q", "W", "E"].every((k) => raw.includes(k))) return raw;
  } catch { /* corrupted — fall back to default */ }
  return ["Q", "W", "E"];
}

function newCdSide(champ) {
  return { champ: champ || "", level: 9, order: savedSkillOrder(champ),
           haste: [], detail: null, error: null };
}

async function hydrateCdSide(side) {
  side.detail = null;
  side.error = null;
  if (!side.champ) return;
  if (!state.ddragonVersion) {
    side.error = "Champion data unavailable (offline).";
    return;
  }
  try {
    side.detail = await loadChampionDetail(side.champ);
  } catch {
    side.error = "Couldn't fetch champion data.";
  }
}

// skill points at a level: R at 6/11/16; basic spells greedily by priority.
// Rank k of a basic spell needs level 2k-1 (max 5).
function ranksAtLevel(level, order) {
  const ranks = { Q: 0, W: 0, E: 0, R: 0 };
  ranks.R = R_LEVELS.filter((l) => level >= l).length;
  let points = level - ranks.R;
  const maxBasic = Math.min(5, Math.floor((level + 1) / 2));
  for (const key of order) {
    const take = Math.min(points, maxBasic);
    ranks[key] = take;
    points -= take;
  }
  return ranks;
}

function hasteTotals(side) {
  let ah = 0, ultAh = 0;
  for (const h of side.haste) {
    ah += +h.ah || 0;
    ultAh += +h.ultAh || 0;
  }
  return { ah, ultAh };
}

function fmtCd(x) { return String(Math.round(x * 10) / 10); }
function reducedCd(cd, haste) { return cd / (1 + haste / 100); }

function cdHasteSummary(side) {
  const { ah, ultAh } = hasteTotals(side);
  return `${ah} AH${ultAh ? ` · +${ultAh} ult AH` : ""}`;
}

function cdSpellsTable(side) {
  if (!side.champ) return `<p class="muted">Pick a champion.</p>`;
  if (side.error) return `<p class="muted">${escapeHtml(side.error)}</p>`;
  if (!side.detail) return `<p class="muted">Loading…</p>`;
  const { ah, ultAh } = hasteTotals(side);
  const ranks = ranksAtLevel(side.level, side.order);
  const rows = side.detail.spells.map((spell, i) => {
    const key = SPELL_KEYS[i];
    const cds = spell.cooldown || [];
    const rank = Math.min(ranks[key] ?? 0, cds.length);
    const haste = key === "R" ? ah + ultAh : ah;
    const perRank = cds.map((c, ri) =>
      `<span class="${ri === rank - 1 ? "cd-current" : ""}">${fmtCd(c)}</span>`).join(" / ");
    const base = rank > 0 ? cds[rank - 1] : null;
    const icon = `<img src="https://ddragon.leagueoflegends.com/cdn/${state.ddragonVersion}/img/spell/${spell.image.full}"
      width="28" height="28" alt="" loading="lazy" onerror="this.style.display='none'">`;
    const value = base == null
      ? `<span class="muted" title="No point at this level">–</span>`
      : haste > 0
        ? `<span class="muted cd-base">${fmtCd(base)}s</span> <strong>${fmtCd(reducedCd(base, haste))}s</strong>`
        : `<strong>${fmtCd(base)}s</strong>`;
    return `<div class="cd-spell">
      ${icon}
      <div class="cd-spell-main">
        <div class="cd-spell-name"><strong>${key}</strong> ${escapeHtml(spell.name)}
          <span class="muted">· rank ${rank}/${cds.length}</span></div>
        <div class="cd-spell-ranks muted">${perRank}s</div>
      </div>
      <div class="cd-spell-value">${value}</div>
    </div>`;
  }).join("");
  return `<div class="cd-spells">${rows}</div>`;
}

function cdSidePanel(sideKey, title) {
  const side = cdState.sides[sideKey];
  const hasteRows = side.haste.map((h, i) => `
    <div class="cd-haste-row">
      <input type="text" class="cd-haste-label" data-side="${sideKey}" data-i="${i}"
        placeholder="item / rune / buff…" value="${escapeHtml(h.label)}" aria-label="Haste source">
      <input type="number" class="cd-haste-ah" data-side="${sideKey}" data-i="${i}"
        min="0" max="500" step="5" value="${h.ah}" title="Ability haste" aria-label="Ability haste">
      <input type="number" class="cd-haste-ult" data-side="${sideKey}" data-i="${i}"
        min="0" max="500" step="5" value="${h.ultAh}" title="Ultimate ability haste" aria-label="Ultimate ability haste">
      <button type="button" class="preset icon-btn cd-haste-remove" data-side="${sideKey}" data-i="${i}"
        title="Remove" aria-label="Remove haste source">✕</button>
    </div>`).join("");
  const orderChips = side.order.map((k) => `<span class="chip chip-plain cd-order-chip"
      draggable="true" data-side="${sideKey}" data-key="${k}"
      title="Drag to change skill priority">${k}</span>`).join("");
  return `<div class="cd-side">
    <div class="filter-label">${title}</div>
    <div class="cd-side-head">
      ${champIcon(side.champ)}
      <select class="cd-champ-select" data-side="${sideKey}" aria-label="${title}">
        ${cdState.options[sideKey]}</select>
    </div>
    <div class="cd-control-row">
      <label>Level <strong class="cd-level-value" data-side="${sideKey}">${side.level}</strong></label>
      <input type="range" class="cd-level" data-side="${sideKey}" min="1" max="18" value="${side.level}">
    </div>
    <div class="cd-control-row">
      <span>Skill priority</span>
      <span class="cd-order">${orderChips}</span>
      <span class="muted">R at 6 / 11 / 16</span>
    </div>
    <div class="cd-haste">
      <div class="cd-control-row">
        <span>Haste sources</span>
        <span class="muted cd-haste-totals" data-side="${sideKey}">${cdHasteSummary(side)}</span>
      </div>
      ${side.haste.length ? `<div class="cd-haste-head muted">
        <span>Source</span><span>AH</span><span>Ult AH</span><span></span></div>` : ""}
      ${hasteRows}
      <button type="button" class="preset cd-haste-add" data-side="${sideKey}">+ Add haste source</button>
    </div>
    <div class="cd-table" data-side="${sideKey}">${cdSpellsTable(side)}</div>
  </div>`;
}

function updateCdSide(sideKey) {
  const side = cdState.sides[sideKey];
  const table = $(`.cd-table[data-side="${sideKey}"]`);
  if (table) table.innerHTML = cdSpellsTable(side);
  const totals = $(`.cd-haste-totals[data-side="${sideKey}"]`);
  if (totals) totals.textContent = cdHasteSummary(side);
}

let cdDragKey = null; // {side, key} of the skill-priority chip being dragged

function renderCooldowns() {
  const box = $("#modal-box");
  box.innerHTML = `
    <div class="modal-head">
      <h3>Cooldown comparison</h3>
      <button type="button" class="preset icon-btn" id="modal-close" title="Close" aria-label="Close">✕</button>
    </div>
    <div class="cd-grid">${cdSidePanel("me", "You")}${cdSidePanel("opp", "Opponent")}</div>`;
  wireCooldowns(box);
}

function wireCooldowns(box) {
  box.querySelector("#modal-close").addEventListener("click", closeModal);
  box.querySelectorAll(".cd-champ-select").forEach((select) => {
    select.value = cdState.sides[select.dataset.side].champ; // innerHTML selection can be stale
    select.addEventListener("change", async () => {
      const side = cdState.sides[select.dataset.side];
      side.champ = select.value;
      side.order = savedSkillOrder(side.champ);
      renderCooldowns();
      await hydrateCdSide(side);
      renderCooldowns();
    });
  });
  box.querySelectorAll(".cd-level").forEach((input) =>
    input.addEventListener("input", () => {
      const side = cdState.sides[input.dataset.side];
      side.level = +input.value;
      $(`.cd-level-value[data-side="${input.dataset.side}"]`).textContent = side.level;
      updateCdSide(input.dataset.side);
    }));
  box.querySelectorAll(".cd-haste-add").forEach((btn) =>
    btn.addEventListener("click", () => {
      cdState.sides[btn.dataset.side].haste.push({ label: "", ah: 10, ultAh: 0 });
      renderCooldowns();
    }));
  box.querySelectorAll(".cd-haste-remove").forEach((btn) =>
    btn.addEventListener("click", () => {
      cdState.sides[btn.dataset.side].haste.splice(+btn.dataset.i, 1);
      renderCooldowns();
    }));
  box.querySelectorAll(".cd-haste-label").forEach((input) =>
    input.addEventListener("input", () => {
      cdState.sides[input.dataset.side].haste[+input.dataset.i].label = input.value;
    }));
  box.querySelectorAll(".cd-haste-ah").forEach((input) =>
    input.addEventListener("input", () => {
      cdState.sides[input.dataset.side].haste[+input.dataset.i].ah = +input.value || 0;
      updateCdSide(input.dataset.side);
    }));
  box.querySelectorAll(".cd-haste-ult").forEach((input) =>
    input.addEventListener("input", () => {
      cdState.sides[input.dataset.side].haste[+input.dataset.i].ultAh = +input.value || 0;
      updateCdSide(input.dataset.side);
    }));
  box.querySelectorAll(".cd-order-chip").forEach((chip) => {
    chip.addEventListener("dragstart", (e) => {
      cdDragKey = { side: chip.dataset.side, key: chip.dataset.key };
      chip.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", chip.dataset.key);
    });
    chip.addEventListener("dragend", () => {
      cdDragKey = null;
      chip.classList.remove("dragging");
    });
    chip.addEventListener("dragover", (e) => {
      if (!cdDragKey || cdDragKey.side !== chip.dataset.side
          || cdDragKey.key === chip.dataset.key) return;
      e.preventDefault();
      chip.classList.add("drag-over");
    });
    chip.addEventListener("dragleave", () => chip.classList.remove("drag-over"));
    chip.addEventListener("drop", (e) => {
      e.preventDefault();
      chip.classList.remove("drag-over");
      if (!cdDragKey || cdDragKey.side !== chip.dataset.side) return;
      const side = cdState.sides[chip.dataset.side];
      const from = side.order.indexOf(cdDragKey.key);
      const to = side.order.indexOf(chip.dataset.key);
      if (from < 0 || to < 0 || from === to) return;
      side.order.splice(from, 1);
      side.order.splice(to, 0, cdDragKey.key);
      if (side.champ) {
        localStorage.setItem(`cp-skill-order-${side.champ}`, JSON.stringify(side.order));
      }
      renderCooldowns();
    });
  });
}

async function openCooldowns(me, opp) {
  cdState.sides.me = newCdSide(me);
  cdState.sides.opp = newCdSide(opp);
  $("#modal-overlay").classList.remove("hidden");
  $("#modal-box").innerHTML = `<p class="muted">Loading…</p>`;
  [cdState.options.me, cdState.options.opp] = await Promise.all([
    championOptions(cdState.sides.me.champ, "– pick a champion –"),
    championOptions(cdState.sides.opp.champ, "– pick a champion –"),
  ]);
  renderCooldowns();
  await Promise.all([hydrateCdSide(cdState.sides.me), hydrateCdSide(cdState.sides.opp)]);
  renderCooldowns();
}

function closeModal() {
  $("#modal-overlay").classList.add("hidden");
}

// overlay click (outside the box) and Esc close the modal
$("#modal-overlay").addEventListener("click", (e) => {
  if (e.target === $("#modal-overlay")) closeModal();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !$("#modal-overlay").classList.contains("hidden")) closeModal();
});
