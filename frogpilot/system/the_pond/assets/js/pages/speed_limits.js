(() => {
"use strict";

// Saved Speed Limits: the limits Keith saved by tapping the sign on the driving screen, plus a backup of them and of
// FrogPilot's learned limits.

const P = window.Pond;

const MESSAGES = {
  invalid_speed_limit: "Enter a speed limit between 5 and 90 mph (8 and 145 km/h)",
  not_a_backup: "That file isn't a speed limit backup from The Pond"
};

function unit(data) {
  return data.metric ? "km/h" : "mph";
}

function savedDate(stamp) {
  const date = new Date(stamp);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function mapLink(row) {
  if (row.latitude == null || row.longitude == null) {
    return "";
  }
  const href = `https://www.openstreetmap.org/?mlat=${row.latitude}&mlon=${row.longitude}#map=17/${row.latitude}/${row.longitude}`;
  return ` · <a class="link" href="${href}" target="_blank" rel="noopener">Map</a>`;
}

function limitRow(row, data) {
  const place = row.kind === "gps" ? `GPS spot, heading ${row.heading}` : "";
  const name = row.road_name ? P.esc(row.road_name) : (place || "Unnamed road");
  const when = savedDate(row.saved);
  return `<div class="list-row">
    <span class="grow"><b>${name}</b><span class="muted">${row.kind === "gps" && row.road_name ? `${place} · ` : ""}${when ? `Saved ${when}` : "Saved"}${mapLink(row)}</span></span>
    <span class="acts">
      <span class="num"><b>${row.speed_limit}</b> ${unit(data)}</span>
      <button class="btn btn-quiet btn-small" data-act="speed-limit-edit" data-key="${row.key}" data-value="${row.speed_limit}" data-name="${name}">Change…</button>
      <button class="icon-btn danger" data-act="speed-limit-remove" data-key="${row.key}" data-name="${name}" aria-label="Remove the saved limit for ${name}" title="Remove">${P.ic("trash")}</button>
    </span>
  </div>`;
}

P.act("speed-limit-edit", button => {
  P.dialog({
    icon: "pencil", title: `Change the limit for ${button.dataset.name}`,
    body: `<label class="field"><span>Speed limit</span><input class="input" type="number" inputmode="numeric" min="5" max="145" step="1" data-limit value="${button.dataset.value}"></label>`,
    confirm: "Save",
    errors: MESSAGES,
    onConfirm: dialog => {
      const value = Number(dialog.querySelector("[data-limit]").value);
      return P.request("PUT", `/api/saved_speed_limits/${button.dataset.key}`, { speed_limit: value }).then(() => {
        P.refresh();
        P.toast("Speed limit changed", "Used the next time you drive there");
      });
    }
  });
});

P.act("speed-limit-remove", async button => {
  const ok = await P.dialog({
    icon: "trash", tone: "danger", confirmTone: "danger", title: `Remove the saved limit for ${button.dataset.name}?`,
    body: "<p>openpilot goes back to the camera and map for this road.</p>",
    confirm: "Remove"
  });
  if (!ok) {
    return;
  }
  try {
    await P.request("DELETE", `/api/saved_speed_limits/${button.dataset.key}`);
  } catch (error) {
    P.fail(error, "Couldn't remove the saved limit");
    return;
  }
  P.refresh();
  P.toast("Saved limit removed");
});

P.act("speed-limit-export", () => {
  P.download("/api/saved_speed_limits/export", `speed-limits-${new Date().toISOString().slice(0, 10)}.json`);
});

P.act("speed-limit-import", button => {
  button.closest("[data-speed-limits]").querySelector("[data-import-file]").click();
});

async function restore(file) {
  let backup;
  try {
    backup = JSON.parse(await file.text());
  } catch {
    P.toast("Couldn't restore", MESSAGES.not_a_backup, "alert");
    return;
  }

  let result;
  try {
    result = await P.request("POST", "/api/saved_speed_limits/import", backup);
  } catch (error) {
    P.fail(error, "Couldn't restore", MESSAGES);
    return;
  }

  P.refresh();
  const parts = [`${P.plural(result.saved_restored, "saved limit")} restored`];
  if (result.learned_added) {
    parts.push(`${P.plural(result.learned_added, "learned road")} added. Reboot from the Device page before driving so openpilot uses them`);
  } else if (result.learned_skipped) {
    parts.push("Learned limits weren't restored while driving. Try again when parked");
  }
  P.toast("Backup restored", parts.join(". "));
}

P.page("speed_limits", {
  title: "Saved Speed Limits",
  async render() {
    const data = await P.get("/api/saved_speed_limits");
    const rows = data.speed_limits.map(row => limitRow(row, data)).join("");
    const empty = `<div class="empty"><h3>No saved limits yet</h3><p>While driving, tap the speed limit sign on the driving screen and pick the real limit. ` +
                  `openpilot then uses it on that road every time, ahead of the camera and the map.</p></div>`;
    return {
      body: `
      <div class="two-col" data-speed-limits>
        <section class="panel">
          <div class="panel-head"><h2>Your saved limits</h2></div>
          <div class="panel-body">${rows || empty}</div>
        </section>
        <section class="panel">
          <div class="panel-head"><h2>Backup</h2></div>
          <div class="panel-body">
            <p>Saved limits and the ${P.plural(data.learned_count, "road")} FrogPilot learned from signs stay on the device through updates. ` +
            `A backup on your phone or computer also covers a reset or a new device.</p>
            <p class="mt-12">
              <button class="btn btn-primary btn-small" type="button" data-act="speed-limit-export">${P.ic("download")}Download backup</button>
              <button class="btn btn-quiet btn-small" type="button" data-act="speed-limit-import">${P.ic("upload")}Restore from backup…</button>
              <input type="file" accept="application/json,.json" data-import-file hidden>
            </p>
            <p class="hint mt-12">Restoring keeps everything already on the device and adds what's in the backup. A saved limit in the backup replaces the one on the device for the same road.</p>
          </div>
        </section>
      </div>`,
      mount: root => {
        const input = root.querySelector("[data-import-file]");
        input.addEventListener("change", () => {
          const file = input.files[0];
          input.value = "";
          if (file) {
            restore(file);
          }
        });
      }
    };
  }
});
})();
