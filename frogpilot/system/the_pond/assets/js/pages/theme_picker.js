(() => {
"use strict";

// Pick a Theme: tap one and everything (colors, icons, sounds, turn signal, distance icons, wheel) switches right away.

const P = window.Pond;

function card(theme) {
  const swatches = theme.colors.map(color => `<span class="tp-sw" style="background:${color}"></span>`).join("");
  const key = encodeURIComponent(theme.key);
  return `<div class="tp-card${theme.current ? " tp-current" : ""}">
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
    const c = data.cycle;
    let cycle = "";
    if (c.enabled) {
      const stay = c.current && c.boots_left > 0
        ? `${P.esc(c.current)} stays for ${c.boots_left} more start-up${c.boots_left === 1 ? "" : "s"}, then ${P.esc(c.next)}.`
        : `Next start-up: ${P.esc(c.next || "")}.`;
      cycle = `<div class="notice">${P.ic("refresh")}<span><b>Theme cycle is on.</b> Each theme stays for 3 start-ups, taking turns between the categories. ${stay} A theme you pick here gets its own 3 start-ups.</span></div>`;
    }
    const groups = data.groups.map(group => `
      <section class="panel"><div class="panel-body"><h3 class="tp-cat">${P.esc(group.name)}</h3>
      <div class="tp-grid">${group.themes.map(card).join("")}</div></div></section>`).join("");
    return {
      body: `
      <style>
        .tp-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(170px,1fr)); gap:12px; }
        .tp-card { display:flex; flex-direction:column; align-items:center; gap:8px; padding:12px; border-radius:12px;
                   border:1px solid var(--line, #ccc); text-align:center; }
        .tp-current { outline:3px solid var(--accent, #2e7d32); }
        .tp-imgs { display:flex; align-items:center; gap:6px; }
        .tp-imgs img { width:72px; height:72px; }
        .tp-imgs img.tp-wheel { width:48px; height:48px; }
        .tp-sws { display:flex; gap:4px; }
        .tp-sw { width:16px; height:16px; border-radius:4px; border:1px solid rgba(0,0,0,.2); }
        .tp-cat { margin:0 0 10px; font-size:17px; }
        .tp-badge { display:inline-flex; align-items:center; gap:4px; font-size:13px; }
      </style>
      ${cycle}
      ${groups || `<div class="empty"><h3>None of your themes are installed</h3></div>`}`
    };
  }
});
})();
