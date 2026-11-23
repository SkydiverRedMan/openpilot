(() => {
"use strict";

// Pick a Theme: tap one and everything (colors, icons, sounds, turn signal, distance icons, wheel) switches right away.
// The panel on top sets how themes change at start-up: in order (categories take turns), random, or keep one theme;
// how many start-ups each theme stays; which categories (and ★ Favorites) to use. Works while driving too.

const P = window.Pond;
const MODES = [["cycle", "In order", "Categories take turns"], ["random", "Random", "Never the same one twice in a row"],
               ["keep", "Keep one theme", "Stays until you pick another"]];
const BOOTS = [1, 2, 3, 4, 5, 7, 10];

function card(theme) {
  const swatches = theme.colors.map(color => `<span class="tp-sw" style="background:${color}"></span>`).join("");
  const key = encodeURIComponent(theme.key);
  return `<div class="tp-card${theme.current ? " tp-current" : ""}">
    <button class="tp-star${theme.favorite ? " on" : ""}" type="button" data-act="theme-star" data-key="${P.esc(theme.key)}"
            data-on="${theme.favorite ? "1" : "0"}" aria-label="${theme.favorite ? "Remove from" : "Add to"} favorites">${theme.favorite ? "★" : "☆"}</button>
    <div class="tp-imgs">
      <img src="/api/theme_picker/${key}/home" alt="" loading="lazy">
      <img class="tp-wheel" src="/api/theme_picker/${key}/wheel" alt="" loading="lazy">
    </div>
    <b>${P.esc(theme.name)}</b>
    <span class="tp-sws">${swatches}</span>
    ${theme.current ? `<span class="tp-badge">${P.ic("check")}In use</span>`
                    : `<button class="btn btn-primary btn-small" type="button" data-act="theme-pick" data-key="${P.esc(theme.key)}" data-name="${P.esc(theme.name)}">Use this theme</button>`}
  </div>`;
}

function choice(act, value, label, selected, hint) {
  return `<button class="btn btn-small ${selected ? "btn-primary" : "btn-quiet"} tp-choice" type="button" data-act="${act}"
          data-value="${P.esc(String(value))}" aria-pressed="${selected}" ${hint ? `title="${P.esc(hint)}"` : ""}>${P.esc(label)}</button>`;
}

function panel(data) {
  const s = data.settings;
  const c = data.cycle;
  const on = s.enabled;
  const chosen = new Set(s.categories);
  let status = "";
  if (on && c.enabled) {
    if (s.mode === "keep") {
      status = `Showing ${P.esc(c.current || "")} until you pick another theme.`;
    } else {
      const stay = c.current && c.boots_left > 0 ? `${P.esc(c.current)} stays for ${c.boots_left} more start-up${c.boots_left === 1 ? "" : "s"}. ` : "";
      status = stay + (c.next ? `Then: ${P.esc(c.next)}.` : "The next one is picked at random at that start-up.");
    }
  } else {
    status = "Off: FrogPilot's own theme settings are used.";
  }
  const modeRow = MODES.map(([value, label, hint]) => choice("theme-mode", value, label, s.mode === value, hint)).join("");
  const bootRow = BOOTS.map(n => choice("theme-boots", n, String(n), s.boots_per_theme === n)).join("");
  const categoryRow = choice("theme-category", "", "All", chosen.size === 0) +
    data.categories.map(name => choice("theme-category", name, name === "Favorites" ? "★ Favorites" : name, chosen.has(name))).join("");
  return `<section class="panel tp-settings"><div class="panel-body">
    <h3 class="tp-cat">How themes change</h3>
    <div class="tp-row"><span class="tp-label">Theme changes</span>${choice("theme-enabled", "1", "On", on)}${choice("theme-enabled", "0", "Off", !on)}</div>
    <div class="tp-row${on ? "" : " tp-off"}"><span class="tp-label">How</span>${modeRow}</div>
    <div class="tp-row${on && s.mode !== "keep" ? "" : " tp-off"}"><span class="tp-label">Change every</span>${bootRow}<span class="tp-unit">start-ups</span></div>
    <div class="tp-row${on ? "" : " tp-off"}"><span class="tp-label">Use</span>${categoryRow}</div>
    <p class="tp-status">${status}</p>
    ${on ? `<button class="btn btn-small" type="button" data-act="theme-next">${P.ic("refresh")}Next theme now</button>` : ""}
    <p class="tp-hint">Tap ☆ on a theme to add it to ★ Favorites. A theme you pick by hand gets its own turn, even outside the chosen categories.</p>
  </div></section>`;
}

async function save(button, changes, message) {
  try {
    await P.busy(button, P.request("POST", "/api/theme_picker/settings", changes));
  } catch (error) {
    P.fail(error, "Couldn't save that", { unknown_theme: "That theme isn't installed anymore" });
    return;
  }
  if (message) P.toast(message, "");
  P.refresh();
}

P.act("theme-enabled", button => save(button, { enabled: button.dataset.value === "1" },
  button.dataset.value === "1" ? "Theme changes on" : "Theme changes off"));
P.act("theme-mode", button => save(button, { mode: button.dataset.value }, `Themes: ${button.textContent.trim()}`));
P.act("theme-boots", button => save(button, { boots_per_theme: Number(button.dataset.value) },
  `Each theme stays ${button.dataset.value} start-up${button.dataset.value === "1" ? "" : "s"}`));
P.act("theme-category", async button => {
  const value = button.dataset.value;
  const current = [...document.querySelectorAll('[data-act="theme-category"][aria-pressed="true"]')].map(b => b.dataset.value).filter(Boolean);
  let categories = [];
  if (value) {
    categories = current.includes(value) ? current.filter(c => c !== value) : [...current, value];
  }
  await save(button, { categories }, categories.length ? `Using: ${categories.join(", ")}` : "Using all categories");
});
P.act("theme-star", button => save(button, { favorite: button.dataset.key, starred: button.dataset.on !== "1" }));
P.act("theme-next", async button => {
  let result;
  try {
    result = await P.busy(button, P.request("POST", "/api/theme_picker/next", {}));
  } catch (error) {
    P.fail(error, "Couldn't switch themes", { no_next_theme: "There's no other theme to switch to" });
    return;
  }
  P.toast(`Switching to ${result && result.name ? result.name : "the next theme"}`, "The comma's screen and sounds change in a moment");
  setTimeout(() => P.refresh(), 1500);
});

P.act("theme-pick", async button => {
  try {
    await P.busy(button, P.request("POST", "/api/theme_picker/apply", { key: button.dataset.key }));
  } catch (error) {
    P.fail(error, "Couldn't switch themes", { unknown_theme: "That theme isn't installed anymore" });
    return;
  }
  P.toast(`Switching to ${button.dataset.name}`, "The comma's screen and sounds change in a moment");
  setTimeout(() => P.refresh(), 1500);
});

P.page("theme_picker", {
  title: "Pick a Theme",
  async render() {
    const data = await P.get("/api/theme_picker");
    const groups = data.groups.map(group => `
      <section class="panel"><div class="panel-body"><h3 class="tp-cat">${P.esc(group.name)}</h3>
      <div class="tp-grid">${group.themes.map(card).join("")}</div></div></section>`).join("");
    return {
      body: `
      <style>
        .tp-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(170px,1fr)); gap:12px; }
        .tp-card { position:relative; display:flex; flex-direction:column; align-items:center; gap:8px; padding:12px; border-radius:12px;
                   border:1px solid var(--line, #ccc); text-align:center; }
        .tp-current { outline:3px solid var(--accent, #2e7d32); }
        .tp-imgs { display:flex; align-items:center; gap:6px; }
        .tp-imgs img { width:72px; height:72px; }
        .tp-imgs img.tp-wheel { width:48px; height:48px; }
        .tp-sws { display:flex; gap:4px; }
        .tp-sw { width:16px; height:16px; border-radius:4px; border:1px solid rgba(0,0,0,.2); }
        .tp-cat { margin:0 0 10px; font-size:17px; }
        .tp-badge { display:inline-flex; align-items:center; gap:4px; font-size:13px; }
        .tp-star { position:absolute; top:6px; left:8px; background:none; border:0; font-size:22px; line-height:1; cursor:pointer;
                   color:var(--muted, #888); padding:4px; min-width:32px; min-height:32px; }
        .tp-star.on { color:#f9a825; }
        .tp-row { display:flex; flex-wrap:wrap; align-items:center; gap:6px; margin:0 0 10px; }
        .tp-label { min-width:110px; font-weight:600; }
        .tp-unit { color:var(--muted, #888); font-size:13px; }
        .tp-off { opacity:.45; }
        .tp-status { margin:4px 0 10px; }
        .tp-hint { margin:10px 0 0; color:var(--muted, #888); font-size:13px; }
      </style>
      ${panel(data)}
      ${groups || `<div class="empty"><h3>None of your themes are installed</h3></div>`}`
    };
  }
});
})();
