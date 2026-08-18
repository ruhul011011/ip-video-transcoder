const state = {
  channels: [],
  selectedId: null,
  editing: false,
};

const $ = (sel) => document.querySelector(sel);
const form = $("#channel-form");
const fields = $("#form-fields");

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    let detail = "Request failed";
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch (_) {
      detail = await res.text();
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (res.status === 204) return null;
  return res.json();
}

function selected() {
  return state.channels.find((c) => c.id === state.selectedId) || null;
}

function setEditing(on) {
  state.editing = on;
  fields.disabled = !on;
  $("#btn-apply").disabled = !on;
  $("#btn-cancel").disabled = !on;
  const ch = selected();
  $("#btn-edit").disabled = !ch || on;
  syncApplyRestart();
}

function syncApplyRestart() {
  const ch = selected();
  const starting = ch && ch.status === "STARTING";
  $("#btn-apply-restart").disabled = !ch || starting;
}

function fillForm(ch) {
  if (!ch) {
    form.reset();
    $("#last-log").textContent = "Select a channel";
    return;
  }
  form.memo.value = ch.memo || "";
  form.media_source.value = ch.media_source || "";
  form.target_format.value = ch.target_format || "rtmp";
  form.target_url.value = ch.target_url || "";
  form.user_agent.value = ch.user_agent || "";
  form.http_headers.value = ch.http_headers || "";
  form.video_enabled.checked = ch.video?.enabled ?? true;
  form.video_encoding.value = ch.video?.encoding || "libx264";
  form.frame_size.value = ch.video?.frame_size || "640x360";
  form.frame_rate.value = ch.video?.frame_rate || "original";
  form.video_bitrate.value = ch.video?.bitrate_kbps ?? 800;
  form.keyframe.value = ch.video?.keyframe_interval_sec ?? 5;
  form.cbr.checked = !!ch.video?.cbr;
  form.audio_enabled.checked = ch.audio?.enabled ?? true;
  form.audio_encoding.value = ch.audio?.encoding || "aac";
  form.sample_rate.value = ch.audio?.sample_rate || "original";
  form.channels.value = ch.audio?.channels || "stereo";
  form.audio_bitrate.value = ch.audio?.bitrate_kbps ?? "";
  $("#last-log").textContent = ch.error || ch.last_log || "(no output yet)";
}

function formPayload() {
  const audioBitrate = form.audio_bitrate.value
    ? Number(form.audio_bitrate.value)
    : null;
  return {
    memo: form.memo.value.trim(),
    media_source: form.media_source.value.trim(),
    target_format: form.target_format.value,
    target_url: form.target_url.value.trim(),
    user_agent: form.user_agent.value.trim(),
    http_headers: form.http_headers.value.trim(),
    video: {
      enabled: form.video_enabled.checked,
      encoding: form.video_encoding.value,
      frame_size: form.frame_size.value,
      frame_rate: form.frame_rate.value,
      bitrate_kbps: Number(form.video_bitrate.value || 800),
      keyframe_interval_sec: Number(form.keyframe.value || 5),
      cbr: form.cbr.checked,
      preset: "veryfast",
    },
    audio: {
      enabled: form.audio_enabled.checked,
      encoding: form.audio_encoding.value,
      sample_rate: form.sample_rate.value,
      channels: form.channels.value,
      bitrate_kbps: audioBitrate,
    },
  };
}

function renderRows() {
  const tbody = $("#channel-rows");
  if (!state.channels.length) {
    tbody.innerHTML = `<tr class="empty"><td colspan="4">No channels yet. Create one to start.</td></tr>`;
  } else {
    tbody.innerHTML = state.channels
      .map((ch) => {
        const selectedCls = ch.id === state.selectedId ? "selected" : "";
        return `<tr data-id="${ch.id}" class="${selectedCls}">
          <td>${ch.index}</td>
          <td class="source">${escapeHtml(ch.media_source || "(empty)")}</td>
          <td>${escapeHtml(ch.memo || "")}</td>
          <td><span class="status ${ch.status}"><span class="status-dot"></span>${ch.status}</span></td>
        </tr>`;
      })
      .join("");
  }

  const running = state.channels.filter((c) => c.status === "RUNNING").length;
  $("#channel-count").textContent = `${state.channels.length} channel${state.channels.length === 1 ? "" : "s"}`;
  $("#running-count").textContent = `${running} running`;

  const ch = selected();
  const busy = ch && ["RUNNING", "STARTING"].includes(ch.status);
  const canStart = ch && !state.editing && ["IDLE", "ERROR"].includes(ch.status);
  $("#btn-remove").disabled = !ch || state.editing;
  $("#btn-start").disabled = !canStart;
  $("#btn-stop").disabled = !ch || !busy || state.editing;
  if (!state.editing) {
    $("#btn-edit").disabled = !ch;
  }
  syncApplyRestart();
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function refreshChannels({ keepSelection = true } = {}) {
  const channels = await api("/api/channels");
  state.channels = channels.sort((a, b) => a.index - b.index);
  if (keepSelection && state.selectedId) {
    if (!state.channels.some((c) => c.id === state.selectedId)) {
      state.selectedId = state.channels[0]?.id || null;
      setEditing(false);
    }
  } else if (!state.selectedId && state.channels.length) {
    state.selectedId = state.channels[0].id;
  }
  // Avoid clobbering the form while typing / focused inside it
  const active = document.activeElement;
  const formFocused = fields.contains(active);
  if (!state.editing && !formFocused) fillForm(selected());
  else if (!state.editing) {
    const ch = selected();
    $("#last-log").textContent = ch
      ? ch.error || ch.last_log || "(no output yet)"
      : "Select a channel";
  }
  renderRows();
}

async function refreshStats() {
  try {
    const stats = await api("/api/stats");
    const bars = $("#cpu-bars");
    bars.innerHTML = stats.cpu_percent
      .map((p) => {
        const h = Math.max(3, Math.round((p / 100) * 22));
        const color = p > 80 ? "#d45454" : p > 50 ? "#d4a017" : "#2f9e6b";
        return `<span style="height:${h}px;background:${color}"></span>`;
      })
      .join("");
    $("#cpu-avg").textContent = `${Math.round(stats.cpu_avg)}%`;
    $("#mem-fill").style.width = `${Math.round(stats.memory_percent)}%`;
    $("#mem-avg").textContent = `${Math.round(stats.memory_percent)}%`;
  } catch (_) {
    /* ignore */
  }
}

$("#channel-rows").addEventListener("click", (e) => {
  const tr = e.target.closest("tr[data-id]");
  if (!tr) return;
  if (state.editing) {
    if (!confirm("Discard unsaved changes?")) return;
    setEditing(false);
  }
  state.selectedId = tr.dataset.id;
  fillForm(selected());
  renderRows();
});

$("#btn-new").addEventListener("click", async () => {
  try {
    const ch = await api("/api/channels", {
      method: "POST",
      body: JSON.stringify({
        memo: `channel ${state.channels.length + 1}`,
        media_source: "",
        target_format: "rtmp",
        target_url: "",
        user_agent:
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        http_headers: "",
        video: {
          enabled: true,
          encoding: "libx264",
          frame_size: "640x360",
          frame_rate: "original",
          bitrate_kbps: 800,
          keyframe_interval_sec: 5,
          cbr: false,
          preset: "veryfast",
        },
        audio: {
          enabled: true,
          encoding: "aac",
          sample_rate: "original",
          channels: "stereo",
          bitrate_kbps: null,
        },
      }),
    });
    state.selectedId = ch.id;
    await refreshChannels();
    setEditing(true);
  } catch (err) {
    alert(err.message);
  }
});

$("#btn-remove").addEventListener("click", async () => {
  const ch = selected();
  if (!ch) return;
  if (!confirm(`Remove channel #${ch.index}?`)) return;
  try {
    await api(`/api/channels/${ch.id}`, { method: "DELETE" });
    state.selectedId = null;
    setEditing(false);
    await refreshChannels({ keepSelection: false });
    fillForm(null);
  } catch (err) {
    alert(err.message);
  }
});

$("#btn-edit").addEventListener("click", () => setEditing(true));

$("#btn-cancel").addEventListener("click", () => {
  setEditing(false);
  fillForm(selected());
});

async function saveChannel(ch) {
  await api(`/api/channels/${ch.id}`, {
    method: "PUT",
    body: JSON.stringify(formPayload()),
  });
}

$("#btn-apply").addEventListener("click", async () => {
  const ch = selected();
  if (!ch) return;
  try {
    await saveChannel(ch);
    setEditing(false);
    await refreshChannels();
  } catch (err) {
    alert(err.message);
  }
});

$("#btn-apply-restart").addEventListener("click", async () => {
  const ch = selected();
  if (!ch) return;
  const btn = $("#btn-apply-restart");
  btn.disabled = true;
  try {
    if (state.editing) {
      await saveChannel(ch);
      setEditing(false);
    }
    await api(`/api/channels/${ch.id}/restart`, { method: "POST" });
    await refreshChannels();
  } catch (err) {
    alert(err.message);
    await refreshChannels();
  }
});

$("#btn-start").addEventListener("click", async () => {
  const ch = selected();
  if (!ch) return;
  try {
    await api(`/api/channels/${ch.id}/start`, { method: "POST" });
    await refreshChannels();
  } catch (err) {
    alert(err.message);
    await refreshChannels();
  }
});

$("#btn-stop").addEventListener("click", async () => {
  const ch = selected();
  if (!ch) return;
  try {
    await api(`/api/channels/${ch.id}/stop`, { method: "POST" });
    await refreshChannels();
  } catch (err) {
    alert(err.message);
  }
});

const settingsModal = $("#settings-modal");
const settingsForm = $("#settings-form");

async function loadSettings() {
  const s = await api("/api/settings");
  settingsForm.http_port.value = s.http_port;
  settingsForm.debug_log.checked = !!s.debug_log;
  settingsForm.auto_start_on_boot.checked = !!s.auto_start_on_boot;
  settingsForm.auto_restart_on_error.checked = !!s.auto_restart_on_error;
  settingsForm.auto_restart_delay_sec.value = s.auto_restart_delay_sec ?? 3;
  settingsForm.loop_file_source.checked = !!s.loop_file_source;
  settingsForm.seamless_streaming.checked = !!s.seamless_streaming;
}

$("#btn-settings").addEventListener("click", async () => {
  try {
    await loadSettings();
    settingsModal.hidden = false;
  } catch (err) {
    alert(err.message);
  }
});

$("#btn-settings-close").addEventListener("click", () => {
  settingsModal.hidden = true;
});

settingsModal.addEventListener("click", (e) => {
  if (e.target === settingsModal) settingsModal.hidden = true;
});

settingsForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify({
        http_port: Number(settingsForm.http_port.value || 9527),
        debug_log: settingsForm.debug_log.checked,
        auto_start_on_boot: settingsForm.auto_start_on_boot.checked,
        auto_restart_on_error: settingsForm.auto_restart_on_error.checked,
        auto_restart_delay_sec: Number(settingsForm.auto_restart_delay_sec.value || 3),
        loop_file_source: settingsForm.loop_file_source.checked,
        seamless_streaming: settingsForm.seamless_streaming.checked,
      }),
    });
    settingsModal.hidden = true;
  } catch (err) {
    alert(err.message);
  }
});

setEditing(false);
refreshChannels();
refreshStats();
setInterval(refreshChannels, 2500);
setInterval(refreshStats, 2000);
