/**
 * HeishaMon Scheduler Card - Schedule block timeline editor
 * Custom Lovelace card for Home Assistant
 */

// Register in the card picker immediately; the element definition below
// waits until the Home Assistant frontend provides a Lit base class.
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "heishamon-scheduler-card")) {
  window.customCards.push({
    type: "heishamon-scheduler-card",
    name: "HeishaMon Scheduler",
    description: "Zeitblöcke für Panasonic Wärmepumpen via HeishaMon",
    preview: true,
  });
}

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

const DAY_PRESETS = {
  daily: ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
  workdays: ["mon", "tue", "wed", "thu", "fri"],
  weekend: ["sat", "sun"],
};

const TAB_LABELS = {
  daily: "Täglich",
  workdays: "Werktage",
  weekend: "Wochenende",
  custom: "Individuell",
};

const ACTION_COLORS = {
  heat: "#f59e42",
  cool: "#4fa8f6",
  dhw: "#26a69a",
  off: "#90a4ae",
};

function localizedDayLabels(lang) {
  const fmt = new Intl.DateTimeFormat(lang || undefined, { weekday: "short" });
  const labels = {};
  DAYS.forEach((day, i) => {
    // 2024-01-01 is a Monday
    labels[day] = fmt.format(new Date(Date.UTC(2024, 0, 1 + i)));
  });
  return labels;
}

const t2m = (t) => {
  const [h, m] = t.split(":").map(Number);
  return h * 60 + m;
};
const m2t = (m) =>
  `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const pct = (mins) => (mins / 1440) * 100;

(async () => {

// Wait until the frontend has defined a Lit-based view element we can
// derive LitElement/html/css from. At resource load time none of these
// may exist yet — grabbing them eagerly kills the whole module.
const VIEW_ELEMENTS = ["hui-view", "hui-masonry-view", "hui-sections-view"];
if (!VIEW_ELEMENTS.some((el) => customElements.get(el))) {
  await Promise.race(VIEW_ELEMENTS.map((el) => customElements.whenDefined(el)));
}
const baseElement =
  customElements.get("hui-masonry-view") ||
  customElements.get("hui-sections-view") ||
  customElements.get("hui-view");
const LitElement = Object.getPrototypeOf(baseElement);
const html = LitElement.prototype.html;
const css = LitElement.prototype.css;

class HeishaMonSchedulerCard extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      _config: { type: Object },
      _blocks: { type: Array },
      _actions: { type: Object },
      _enabled: { type: Boolean },
      _tab: { type: String },
      _customDays: { type: Array },
      _selectedId: { type: String },
      _dirty: { type: Boolean },
    };
  }

  static get styles() {
    return css`
      :host {
        display: block;
      }
      .card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 16px 16px 4px;
        font-size: 1.2em;
        font-weight: 500;
      }
      .enable-toggle {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 0.7em;
        font-weight: 400;
        color: var(--secondary-text-color);
        cursor: pointer;
        user-select: none;
      }
      .enable-toggle input {
        accent-color: var(--primary-color);
        width: 18px;
        height: 18px;
        cursor: pointer;
      }
      .section-label {
        padding: 14px 16px 6px;
        font-size: 0.72em;
        font-weight: 600;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--secondary-text-color);
      }
      .tabs {
        display: flex;
        gap: 6px;
        padding: 0 16px;
        flex-wrap: wrap;
      }
      .chip {
        padding: 7px 14px;
        border-radius: 8px;
        cursor: pointer;
        font-size: 0.82em;
        font-weight: 600;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        white-space: nowrap;
        background: transparent;
        color: var(--primary-color, #03a9f4);
        border: none;
        transition: background 0.15s;
        user-select: none;
      }
      .chip:hover:not(.active) {
        background: var(--secondary-background-color, #f0f0f0);
      }
      .chip.active {
        background: var(--primary-color, #03a9f4);
        color: var(--text-primary-color, #fff);
      }
      .day-chips {
        display: flex;
        gap: 6px;
        padding: 8px 16px 0;
        flex-wrap: wrap;
      }
      .day-chip {
        min-width: 38px;
        padding: 6px 0;
        border-radius: 8px;
        border: 1px solid var(--divider-color, #e0e0e0);
        background: transparent;
        color: var(--primary-text-color);
        font-size: 0.8em;
        cursor: pointer;
        text-align: center;
      }
      .day-chip.active {
        background: var(--primary-color, #03a9f4);
        border-color: var(--primary-color, #03a9f4);
        color: var(--text-primary-color, #fff);
      }
      .timeline {
        position: relative;
        margin: 42px 20px 4px;
      }
      .track {
        position: relative;
        height: 54px;
        border-radius: 10px;
        background: color-mix(in srgb, var(--primary-color, #03a9f4) 14%, transparent);
        touch-action: none;
      }
      .block {
        position: absolute;
        top: 0;
        bottom: 0;
        border-radius: 8px;
        display: flex;
        align-items: center;
        justify-content: center;
        color: #fff;
        font-size: 0.85em;
        font-weight: 600;
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.35);
        cursor: pointer;
        overflow: hidden;
        white-space: nowrap;
      }
      .block.selected {
        box-shadow: inset 0 0 0 3px rgba(255, 255, 255, 0.85),
          0 1px 4px rgba(0, 0, 0, 0.3);
        z-index: 2;
      }
      .handle {
        position: absolute;
        top: 50%;
        width: 26px;
        height: 26px;
        border-radius: 50%;
        background: #fff;
        color: #444;
        box-shadow: 0 1px 4px rgba(0, 0, 0, 0.35);
        transform: translate(-50%, -50%);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.75em;
        font-weight: 700;
        letter-spacing: -1px;
        cursor: ew-resize;
        z-index: 3;
        touch-action: none;
        user-select: none;
      }
      .bubble {
        position: absolute;
        top: -34px;
        transform: translateX(-50%);
        background: var(--primary-color, #03a9f4);
        color: var(--text-primary-color, #fff);
        font-size: 0.75em;
        font-weight: 600;
        padding: 3px 8px;
        border-radius: 6px;
        white-space: nowrap;
        z-index: 4;
        pointer-events: none;
      }
      .bubble::after {
        content: "";
        position: absolute;
        left: 50%;
        bottom: -4px;
        transform: translateX(-50%);
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 5px solid var(--primary-color, #03a9f4);
      }
      .now-line {
        position: absolute;
        top: -4px;
        bottom: -4px;
        width: 2px;
        background: var(--error-color, #f44336);
        z-index: 1;
        pointer-events: none;
      }
      .axis {
        position: relative;
        height: 18px;
        margin: 6px 20px 0;
        font-size: 0.72em;
        color: var(--secondary-text-color);
      }
      .axis span {
        position: absolute;
        transform: translateX(-50%);
      }
      .toolbar {
        display: flex;
        gap: 18px;
        padding: 10px 16px 2px;
        align-items: center;
        justify-content: space-between;
      }
      .toolbar-hint {
        font-size: 0.8em;
        color: var(--secondary-text-color);
      }
      .icon-btn {
        display: flex;
        align-items: center;
        gap: 8px;
        background: none;
        border: none;
        color: var(--primary-color, #03a9f4);
        font-size: 0.82em;
        font-weight: 600;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        cursor: pointer;
        padding: 6px 4px;
      }
      .icon-btn:disabled {
        color: var(--disabled-text-color, #9e9e9e);
        cursor: default;
      }
      .icon-btn .circle {
        width: 22px;
        height: 22px;
        border-radius: 50%;
        border: 2px solid currentColor;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.1em;
        line-height: 1;
      }
      .actions-row {
        display: flex;
        gap: 6px;
        padding: 0 16px;
        flex-wrap: wrap;
      }
      .action-chip {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 8px 14px;
        border-radius: 8px;
        border: none;
        background: transparent;
        color: var(--primary-color, #03a9f4);
        font-size: 0.82em;
        font-weight: 600;
        letter-spacing: 0.03em;
        text-transform: uppercase;
        cursor: pointer;
        user-select: none;
      }
      .action-chip:hover:not(.active) {
        background: var(--secondary-background-color, #f0f0f0);
      }
      .action-chip.active {
        background: var(--primary-color, #03a9f4);
        color: var(--text-primary-color, #fff);
      }
      .action-chip .dot {
        width: 10px;
        height: 10px;
        border-radius: 50%;
      }
      .value-row {
        display: flex;
        align-items: center;
        gap: 14px;
        padding: 10px 24px 2px;
      }
      .value-row input[type="range"] {
        flex: 1;
        accent-color: var(--primary-color);
      }
      .sub-toggle {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 0.88em;
        white-space: nowrap;
        cursor: pointer;
        user-select: none;
      }
      .sub-toggle input {
        accent-color: var(--primary-color);
        width: 17px;
        height: 17px;
        cursor: pointer;
      }
      .sub-hint {
        font-size: 0.82em;
        color: var(--secondary-text-color);
      }
      .value-display {
        font-weight: 600;
        min-width: 48px;
        text-align: right;
      }
      .footer {
        display: flex;
        gap: 10px;
        padding: 14px 16px 16px;
      }
      .btn {
        padding: 8px 18px;
        border-radius: 8px;
        border: 1px solid var(--primary-color, #03a9f4);
        background: transparent;
        color: var(--primary-color, #03a9f4);
        font-size: 0.82em;
        font-weight: 600;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        cursor: pointer;
      }
      .btn.primary {
        background: var(--primary-color, #03a9f4);
        color: var(--text-primary-color, #fff);
      }
      .hint {
        padding: 4px 24px 10px;
        font-size: 0.8em;
        color: var(--secondary-text-color);
      }
      .overview-row {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 3px 20px;
        cursor: pointer;
      }
      .overview-row:hover .ov-label {
        color: var(--primary-color, #03a9f4);
      }
      .ov-label {
        flex: 0 0 150px;
        font-size: 0.78em;
        color: var(--secondary-text-color);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .overview-row.current .ov-label {
        color: var(--primary-color, #03a9f4);
        font-weight: 600;
      }
      .ov-track {
        flex: 1;
        position: relative;
        height: 16px;
        border-radius: 5px;
        background: color-mix(in srgb, var(--primary-color, #03a9f4) 10%, transparent);
      }
      .overview-row.current .ov-track {
        outline: 2px solid var(--primary-color, #03a9f4);
        outline-offset: 1px;
      }
      .ov-block {
        position: absolute;
        top: 0;
        bottom: 0;
        border-radius: 4px;
      }
      .loading {
        padding: 32px 16px;
        text-align: center;
        color: var(--secondary-text-color);
      }
    `;
  }

  constructor() {
    super();
    this._blocks = null;
    this._orig = null;
    this._actions = null;
    this._enabled = true;
    this._tab = "daily";
    this._customDays = ["mon"];
    this._selectedId = null;
    this._dirty = false;
    this._drag = null;
    this._newCounter = 0;
    this._dayLabels = localizedDayLabels();
    this._boundDragMove = this._onDragMove.bind(this);
    this._boundDragUp = this._onDragUp.bind(this);
  }

  setConfig(config) {
    this._config = config;
  }

  set hass(hass) {
    const oldHass = this._hass;
    this._hass = hass;
    if (!oldHass && hass) {
      this._dayLabels = localizedDayLabels(hass.locale?.language);
      this._load();
    }
  }

  get hass() {
    return this._hass;
  }

  async _load() {
    if (!this._hass) return;
    try {
      const result = await this._hass.callWS({
        type: "heishamon_scheduler/get_schedule",
      });
      this._blocks = result.blocks.map((b) => ({ ...b, days: [...b.days] }));
      this._orig = JSON.parse(JSON.stringify(this._blocks));
      this._actions = result.actions;
      this._enabled = result.enabled;
      this._dirty = false;
      this._selectedId = null;
      this.requestUpdate();
    } catch (e) {
      console.error("Failed to load schedule:", e);
    }
  }

  async _save() {
    if (!this._hass || !this._blocks) return;
    try {
      const result = await this._hass.callWS({
        type: "heishamon_scheduler/set_blocks",
        blocks: this._blocks,
      });
      this._blocks = result.blocks.map((b) => ({ ...b, days: [...b.days] }));
      this._orig = JSON.parse(JSON.stringify(this._blocks));
      this._dirty = false;
      this._selectedId = null;
      this.requestUpdate();
    } catch (e) {
      console.error("Failed to save schedule:", e);
    }
  }

  _cancel() {
    this._blocks = JSON.parse(JSON.stringify(this._orig));
    this._dirty = false;
    this._selectedId = null;
    this.requestUpdate();
  }

  async _toggleEnabled(e) {
    const enabled = e.target.checked;
    try {
      await this._hass.callWS({
        type: "heishamon_scheduler/set_enabled",
        enabled: enabled,
      });
      this._enabled = enabled;
    } catch (err) {
      console.error("Failed to toggle schedule:", err);
    }
    this.requestUpdate();
  }

  _tabDays() {
    return this._tab === "custom" ? this._customDays : DAY_PRESETS[this._tab];
  }

  _sameDays(a, b) {
    if (!a || !b || a.length !== b.length) return false;
    const set = new Set(a);
    return b.every((d) => set.has(d));
  }

  _tabBlocks() {
    const days = this._tabDays();
    return (this._blocks || [])
      .filter((b) => this._sameDays(b.days, days))
      .sort((a, b) => t2m(a.start) - t2m(b.start));
  }

  _groups() {
    const groups = new Map();
    for (const b of this._blocks || []) {
      const key = DAYS.filter((d) => b.days.includes(d)).join(",");
      if (!groups.has(key)) groups.set(key, { days: b.days, blocks: [] });
      groups.get(key).blocks.push(b);
    }
    // Sort: daily, workdays, weekend, then custom sets
    const order = (days) => {
      if (this._sameDays(days, DAY_PRESETS.daily)) return 0;
      if (this._sameDays(days, DAY_PRESETS.workdays)) return 1;
      if (this._sameDays(days, DAY_PRESETS.weekend)) return 2;
      return 3;
    };
    return [...groups.values()].sort((a, b) => order(a.days) - order(b.days));
  }

  _groupLabel(days) {
    if (this._sameDays(days, DAY_PRESETS.daily)) return "Täglich";
    if (this._sameDays(days, DAY_PRESETS.workdays)) {
      return `Werktage (${this._dayLabels.mon}–${this._dayLabels.fri})`;
    }
    if (this._sameDays(days, DAY_PRESETS.weekend)) {
      return `Wochenende (${this._dayLabels.sat}–${this._dayLabels.sun})`;
    }
    return DAYS.filter((d) => days.includes(d))
      .map((d) => this._dayLabels[d])
      .join(", ");
  }

  _selectGroup(days) {
    if (this._sameDays(days, DAY_PRESETS.daily)) this._tab = "daily";
    else if (this._sameDays(days, DAY_PRESETS.workdays)) this._tab = "workdays";
    else if (this._sameDays(days, DAY_PRESETS.weekend)) this._tab = "weekend";
    else {
      this._tab = "custom";
      this._customDays = DAYS.filter((d) => days.includes(d));
    }
    this._selectedId = null;
    this.requestUpdate();
  }

  _selectedBlock() {
    return (this._blocks || []).find((b) => b.id === this._selectedId) || null;
  }

  _blockLabel(block) {
    const action = this._actions?.[block.action];
    if (!action) return block.action;
    const sub = action.sub;
    if (sub && block.value != null) {
      const sign = sub.min < 0 && block.value > 0 ? "+" : "";
      return `${action.name} ${sign}${block.value}${sub.unit || ""}`;
    }
    return action.name;
  }

  _createBlockAt(start, end) {
    const tmpId = crypto.randomUUID
      ? `tmp-${crypto.randomUUID()}`
      : `tmp-${Date.now()}-${++this._newCounter}`;
    const block = {
      id: tmpId,
      days: [...this._tabDays()],
      start: m2t(start),
      end: m2t(end),
      action: "heat",
      value: null,
      enabled: true,
    };
    this._blocks = [...this._blocks, block];
    this._selectedId = block.id;
    this._dirty = true;
    this.requestUpdate();
  }

  _onTrackClick(e) {
    // Only clicks on the empty track, not on blocks or handles
    if (e.target !== e.currentTarget) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const raw = ((e.clientX - rect.left) / rect.width) * 1440;
    const mins = clamp(Math.floor(raw / 10) * 10, 0, 1430);

    // Find the free gap containing the clicked position
    let gapStart = 0;
    let gapEnd = 1440;
    for (const b of this._tabBlocks()) {
      const bs = t2m(b.start);
      const be = t2m(b.end);
      if (bs <= mins && mins < be) return; // inside an existing block
      if (be <= mins) gapStart = Math.max(gapStart, be);
      if (bs > mins) gapEnd = Math.min(gapEnd, bs);
    }
    if (gapEnd - gapStart < 20) return;

    const start = clamp(mins, gapStart, gapEnd - 20);
    const end = Math.min(start + 120, gapEnd);
    this._createBlockAt(start, end);
  }

  _removeBlock() {
    if (!this._selectedId) return;
    this._blocks = this._blocks.filter((b) => b.id !== this._selectedId);
    this._selectedId = null;
    this._dirty = true;
    this.requestUpdate();
  }

  _setAction(actionId) {
    const block = this._selectedBlock();
    const action = this._actions?.[actionId];
    if (!block || !action) return;
    block.action = actionId;
    block.value = null; // sub-setting off by default
    this._dirty = true;
    this.requestUpdate();
  }

  _toggleSub(checked) {
    const block = this._selectedBlock();
    const action = this._actions?.[block?.action];
    if (!block || !action?.sub) return;
    block.value = checked ? action.sub.default : null;
    this._dirty = true;
    this.requestUpdate();
  }

  _setValue(value) {
    const block = this._selectedBlock();
    if (!block) return;
    block.value = Number(value);
    this._dirty = true;
    this.requestUpdate();
  }

  _toggleCustomDay(day) {
    const days = new Set(this._customDays);
    if (days.has(day)) {
      if (days.size > 1) days.delete(day);
    } else {
      days.add(day);
    }
    this._customDays = DAYS.filter((d) => days.has(d));
    this._selectedId = null;
    this.requestUpdate();
  }

  // --- Handle dragging -------------------------------------------------

  _onHandleDown(e, blockId, edge) {
    e.preventDefault();
    e.stopPropagation();
    const track = this.renderRoot.querySelector(".track");
    if (!track) return;
    this._drag = { blockId, edge, rect: track.getBoundingClientRect() };
    window.addEventListener("pointermove", this._boundDragMove);
    window.addEventListener("pointerup", this._boundDragUp);
  }

  _onDragMove(e) {
    if (!this._drag) return;
    const { blockId, edge, rect } = this._drag;
    const raw = ((e.clientX - rect.left) / rect.width) * 1440;
    const mins = clamp(Math.round(raw / 10) * 10, 0, 1440);

    const blocks = this._tabBlocks();
    const idx = blocks.findIndex((b) => b.id === blockId);
    if (idx < 0) return;
    const block = blocks[idx];

    if (edge === "start") {
      const prev = blocks[idx - 1];
      const linked = prev && t2m(prev.end) === t2m(block.start);
      const lo = prev ? (linked ? t2m(prev.start) + 10 : t2m(prev.end)) : 0;
      const hi = t2m(block.end) - 10;
      const v = clamp(mins, lo, hi);
      block.start = m2t(v);
      if (linked) prev.end = m2t(v);
    } else {
      const next = blocks[idx + 1];
      const linked = next && t2m(next.start) === t2m(block.end);
      const lo = t2m(block.start) + 10;
      const hi = next
        ? linked ? t2m(next.end) - 10 : t2m(next.start)
        : 1440;
      const v = clamp(mins, lo, hi);
      block.end = m2t(v);
      if (linked) next.start = m2t(v);
    }

    this._dirty = true;
    this.requestUpdate();
  }

  _onDragUp() {
    this._drag = null;
    window.removeEventListener("pointermove", this._boundDragMove);
    window.removeEventListener("pointerup", this._boundDragUp);
  }

  // --- Rendering --------------------------------------------------------

  _renderTimeline() {
    const blocks = this._tabBlocks();
    const bubbles = new Map();
    for (const b of blocks) {
      bubbles.set(t2m(b.start), b.start);
      bubbles.set(t2m(b.end), b.end);
    }

    const today = DAYS[(new Date().getDay() + 6) % 7];
    const showNow = this._tabDays().includes(today);
    const nowMins = new Date().getHours() * 60 + new Date().getMinutes();

    return html`
      <div class="timeline">
        <div class="track" @click="${this._onTrackClick}">
          ${showNow
            ? html`<div class="now-line" style="left: ${pct(nowMins)}%"></div>`
            : ""}
          ${blocks.map((b) => {
            const start = t2m(b.start);
            const end = Math.max(t2m(b.end), start + 10);
            const color = ACTION_COLORS[b.action] || "#888";
            return html`
              <div
                class="block ${b.id === this._selectedId ? "selected" : ""}"
                style="left: ${pct(start)}%; width: ${pct(end - start)}%; background: ${color}"
                @click="${() => {
                  this._selectedId = b.id === this._selectedId ? null : b.id;
                  this.requestUpdate();
                }}"
              >
                ${end - start >= 90 ? this._blockLabel(b) : ""}
              </div>
            `;
          })}
          ${blocks.map((b) => html`
            <div
              class="handle"
              style="left: ${pct(t2m(b.start))}%"
              @pointerdown="${(e) => this._onHandleDown(e, b.id, "start")}"
            >&#x2039;&#x203a;</div>
            <div
              class="handle"
              style="left: ${pct(t2m(b.end))}%"
              @pointerdown="${(e) => this._onHandleDown(e, b.id, "end")}"
            >&#x2039;&#x203a;</div>
          `)}
          ${[...bubbles.entries()].map(
            ([mins, label]) => html`
              <div class="bubble" style="left: ${pct(mins)}%">${label}</div>
            `
          )}
        </div>
      </div>
      <div class="axis">
        ${[3, 6, 9, 12, 15, 18, 21].map(
          (h) => html`
            <span style="left: ${pct(h * 60)}%">
              ${String(h).padStart(2, "0")}:00
            </span>
          `
        )}
      </div>
      ${blocks.length === 0
        ? html`<div class="hint">
            Noch keine Zeitblöcke für diese Tage — einfach auf eine freie
            Stelle in der Zeitleiste tippen. Außerhalb der Blöcke gelten
            die HeishaMon-Einstellungen.
          </div>`
        : ""}
    `;
  }

  _renderOverview() {
    const groups = this._groups();
    if (groups.length < 2) return html``;
    const currentDays = this._tabDays();

    return html`
      <div class="section-label">Übersicht</div>
      ${groups.map((g) => {
        const current = this._sameDays(g.days, currentDays);
        return html`
          <div
            class="overview-row ${current ? "current" : ""}"
            @click="${() => this._selectGroup(g.days)}"
            title="Zum Bearbeiten anklicken"
          >
            <span class="ov-label">${this._groupLabel(g.days)}</span>
            <div class="ov-track">
              ${g.blocks.map((b) => {
                const start = t2m(b.start);
                const end = Math.max(t2m(b.end), start + 10);
                return html`
                  <div
                    class="ov-block"
                    style="left: ${pct(start)}%; width: ${pct(end - start)}%; background: ${ACTION_COLORS[b.action] || "#888"}"
                    title="${this._blockLabel(b)} ${b.start}–${b.end}"
                  ></div>
                `;
              })}
            </div>
          </div>
        `;
      })}
      <div class="hint">
        Alle Pläne laufen gleichzeitig. Bei Überschneidungen führt der
        spezifischere Plan: Individuell vor Werktage/Wochenende vor Täglich.
      </div>
    `;
  }

  _renderActionEditor() {
    const block = this._selectedBlock();
    if (!block || !this._actions) return html``;
    const action = this._actions[block.action];
    const sub = action?.sub;
    const subOn = sub && block.value != null;

    return html`
      <div class="section-label">Aktion</div>
      <div class="actions-row">
        ${Object.entries(this._actions).map(
          ([id, a]) => html`
            <button
              class="action-chip ${block.action === id ? "active" : ""}"
              @click="${() => this._setAction(id)}"
            >
              <span
                class="dot"
                style="background: ${ACTION_COLORS[id] || "#888"}"
              ></span>
              ${a.name}
            </button>
          `
        )}
      </div>
      ${sub
        ? html`
            <div class="value-row">
              <label class="sub-toggle">
                <input
                  type="checkbox"
                  .checked="${subOn}"
                  @change="${(e) => this._toggleSub(e.target.checked)}"
                />
                ${sub.name}
              </label>
              ${subOn
                ? html`
                    <input
                      type="range"
                      min="${sub.min}"
                      max="${sub.max}"
                      step="${sub.step || 1}"
                      .value="${String(block.value)}"
                      @input="${(e) => this._setValue(e.target.value)}"
                    />
                    <span class="value-display">
                      ${sub.min < 0 && block.value > 0 ? "+" : ""}${block.value}${sub.unit || ""}
                    </span>
                  `
                : html`
                    <span class="sub-hint">
                      Standard der Wärmepumpe bleibt unverändert
                    </span>
                  `}
            </div>
          `
        : ""}
    `;
  }

  render() {
    if (!this._blocks || !this._actions) {
      return html`
        <ha-card><div class="loading">Lade Zeitplan...</div></ha-card>
      `;
    }

    return html`
      <ha-card>
        <div class="card-header">
          <span>HeishaMon Zeitplan</span>
          <label class="enable-toggle">
            <input
              type="checkbox"
              .checked="${this._enabled}"
              @change="${this._toggleEnabled}"
            />
            ${this._enabled ? "Aktiv" : "Pausiert"}
          </label>
        </div>

        <div class="section-label">Tage</div>
        <div class="tabs">
          ${Object.keys(TAB_LABELS).map(
            (tab) => html`
              <button
                class="chip ${this._tab === tab ? "active" : ""}"
                @click="${() => {
                  this._tab = tab;
                  this._selectedId = null;
                  this.requestUpdate();
                }}"
              >
                ${TAB_LABELS[tab]}
              </button>
            `
          )}
        </div>
        ${this._tab === "custom"
          ? html`
              <div class="day-chips">
                ${DAYS.map(
                  (day) => html`
                    <button
                      class="day-chip ${this._customDays.includes(day) ? "active" : ""}"
                      @click="${() => this._toggleCustomDay(day)}"
                    >
                      ${this._dayLabels[day]}
                    </button>
                  `
                )}
              </div>
            `
          : ""}

        <div class="section-label">Zeit</div>
        ${this._renderTimeline()}

        <div class="toolbar">
          <span class="toolbar-hint">
            Klick auf eine freie Stelle im Zeitstrahl fügt einen Block hinzu
          </span>
          <button
            class="icon-btn"
            ?disabled="${!this._selectedId}"
            @click="${this._removeBlock}"
          >
            <span class="circle">&#8722;</span> Entfernen
          </button>
        </div>

        ${this._renderActionEditor()}

        ${this._renderOverview()}

        ${this._dirty
          ? html`
              <div class="footer">
                <button class="btn" @click="${this._cancel}">Abbrechen</button>
                <button class="btn primary" @click="${this._save}">
                  Speichern
                </button>
              </div>
            `
          : html`<div style="height: 12px"></div>`}
      </ha-card>
    `;
  }

  static getConfigElement() {
    return document.createElement("heishamon-scheduler-card-editor");
  }

  static getStubConfig() {
    return {};
  }

  getCardSize() {
    return 6;
  }

  // Sections view (HA 2024.11+): default to full row width
  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  // Older sections layout API
  getLayoutOptions() {
    return { grid_columns: 4, grid_min_columns: 2 };
  }
}

// Card Editor
class HeishaMonSchedulerCardEditor extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      _config: { type: Object },
    };
  }

  setConfig(config) {
    this._config = config;
  }

  render() {
    return html`
      <div>
        <p>HeishaMon Scheduler Card benötigt keine zusätzliche Konfiguration.</p>
        <p>Füge die Card hinzu und der Zeitplan wird automatisch geladen.</p>
      </div>
    `;
  }
}

if (!customElements.get("heishamon-scheduler-card")) {
  customElements.define(
    "heishamon-scheduler-card",
    HeishaMonSchedulerCard
  );
  customElements.define(
    "heishamon-scheduler-card-editor",
    HeishaMonSchedulerCardEditor
  );
}

})().catch((e) =>
  console.error("heishamon-scheduler-card failed to initialize:", e)
);
