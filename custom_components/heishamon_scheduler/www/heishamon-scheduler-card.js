/**
 * HeishaMon Scheduler Card - Visual weekly schedule editor
 * Custom Lovelace card for Home Assistant
 */

// Register in the card picker immediately; the element definition below
// waits until the Home Assistant frontend provides a Lit base class.
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "heishamon-scheduler-card")) {
  window.customCards.push({
    type: "heishamon-scheduler-card",
    name: "HeishaMon Scheduler",
    description: "Visueller Wochenplan für Panasonic Wärmepumpen via HeishaMon",
    preview: true,
  });
}

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

function localizedDayLabels(lang) {
  const fmt = new Intl.DateTimeFormat(lang || undefined, { weekday: "short" });
  const labels = {};
  DAYS.forEach((day, i) => {
    // 2024-01-01 is a Monday
    labels[day] = fmt.format(new Date(Date.UTC(2024, 0, 1 + i)));
  });
  return labels;
}
const HOURS = Array.from({ length: 48 }, (_, i) => {
  const h = Math.floor(i / 2);
  const m = i % 2 === 0 ? "00" : "30";
  return `${String(h).padStart(2, "0")}:${m}`;
});

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
      _schedule: { type: Object },
      _channels: { type: Object },
      _activeChannel: { type: String },
      _editValue: { type: Number },
      _isDragging: { type: Boolean },
      _dragStart: { type: Object },
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
        padding: 16px 16px 0;
        font-size: 1.2em;
        font-weight: 500;
      }
      .tabs {
        display: flex;
        gap: 4px;
        padding: 12px 16px;
        overflow-x: auto;
      }
      .tab {
        padding: 8px 16px;
        border-radius: 20px;
        cursor: pointer;
        font-size: 0.9em;
        white-space: nowrap;
        background: var(--secondary-background-color, #e0e0e0);
        color: var(--primary-text-color);
        border: none;
        transition: all 0.2s;
      }
      .tab.active {
        background: var(--primary-color, #03a9f4);
        color: white;
      }
      .tab:hover:not(.active) {
        background: var(--disabled-color, #bdbdbd);
      }
      .schedule-grid {
        padding: 0 16px 16px;
        overflow-x: auto;
      }
      table {
        border-collapse: collapse;
        width: 100%;
        min-width: 640px;
        user-select: none;
        touch-action: none;
      }
      th {
        font-size: 0.7em;
        font-weight: 400;
        color: var(--secondary-text-color);
        padding: 2px 0 4px 3px;
        min-width: 13px;
        text-align: left;
      }
      th.day-label {
        font-size: 0.8em;
        font-weight: 500;
        text-align: left;
        padding: 0 10px 0 0;
        color: var(--primary-text-color);
        min-width: 34px;
        position: sticky;
        left: 0;
        z-index: 3;
        background: var(--card-background-color, #fff);
      }
      td.cell {
        height: 26px;
        min-width: 13px;
        cursor: pointer;
        border: none;
        border-top: 3px solid var(--card-background-color, #fff);
        background-clip: padding-box;
        transition: opacity 0.15s;
        position: relative;
      }
      td.cell.empty {
        background-color: var(--secondary-background-color, #f0f0f0);
      }
      td.cell.h3 {
        box-shadow: inset -1px 0 0 var(--card-background-color, #fff);
      }
      td.cell.slot-first {
        border-radius: 6px 0 0 6px;
      }
      td.cell.slot-last {
        border-radius: 0 6px 6px 0;
      }
      td.cell:hover {
        opacity: 0.75;
        outline: 2px solid var(--primary-color, #03a9f4);
        outline-offset: -2px;
        z-index: 1;
      }
      td.cell.now-marker {
        outline: 2px solid var(--error-color, #f44336);
        outline-offset: -2px;
        z-index: 2;
      }
      .toolbar {
        display: flex;
        gap: 8px;
        padding: 8px 16px;
        align-items: center;
        flex-wrap: wrap;
      }
      .value-picker {
        display: flex;
        align-items: center;
        gap: 8px;
        background: var(--secondary-background-color);
        border-radius: 8px;
        padding: 6px 12px;
      }
      .value-picker label {
        font-size: 0.85em;
        color: var(--secondary-text-color);
      }
      .value-picker input[type="range"] {
        width: 120px;
        accent-color: var(--primary-color);
      }
      .value-picker select {
        background: var(--card-background-color, white);
        color: var(--primary-text-color);
        border: 1px solid var(--divider-color);
        border-radius: 4px;
        padding: 4px 8px;
        font-size: 0.9em;
      }
      .value-display {
        font-weight: 500;
        min-width: 40px;
        text-align: center;
      }
      .actions {
        display: flex;
        gap: 4px;
        margin-left: auto;
      }
      .btn {
        padding: 6px 12px;
        border-radius: 6px;
        border: 1px solid var(--divider-color);
        background: var(--secondary-background-color);
        color: var(--primary-text-color);
        cursor: pointer;
        font-size: 0.8em;
        white-space: nowrap;
      }
      .btn:hover {
        background: var(--disabled-color, #bdbdbd);
      }
      .legend {
        display: flex;
        gap: 12px;
        padding: 4px 16px 12px;
        flex-wrap: wrap;
        font-size: 0.75em;
        color: var(--secondary-text-color);
      }
      .legend-item {
        display: flex;
        align-items: center;
        gap: 4px;
      }
      .legend-swatch {
        width: 12px;
        height: 12px;
        border-radius: 2px;
        border: 1px solid var(--divider-color);
      }
      .legend-gradient {
        width: 140px;
        height: 10px;
        border-radius: 5px;
        align-self: center;
      }
      .hour-markers th {
        border-bottom: 1px solid var(--divider-color, #e0e0e0);
      }
      .no-schedule {
        padding: 32px 16px;
        text-align: center;
        color: var(--secondary-text-color);
      }
    `;
  }

  constructor() {
    super();
    this._schedule = null;
    this._channels = null;
    this._dayLabels = localizedDayLabels();
    this._activeChannel = null;
    this._editValue = null;
    this._isDragging = false;
    this._dragStart = null;
    this._boundMouseUp = this._onMouseUp.bind(this);
  }

  setConfig(config) {
    this._config = config;
  }

  set hass(hass) {
    const oldHass = this._hass;
    this._hass = hass;
    if (!oldHass && hass) {
      this._dayLabels = localizedDayLabels(hass.locale?.language);
      this._loadSchedule();
    }
  }

  get hass() {
    return this._hass;
  }

  async _loadSchedule() {
    if (!this._hass) return;
    try {
      const result = await this._hass.callWS({
        type: "heishamon_scheduler/get_schedule",
        schedule_id: "default",
      });
      this._schedule = result.schedule;
      this._channels = result.channels;
      if (!this._activeChannel && this._channels) {
        this._activeChannel = Object.keys(this._channels)[0];
      }
      if (this._activeChannel && this._channels) {
        this._setDefaultEditValue();
      }
      this.requestUpdate();
    } catch (e) {
      console.error("Failed to load schedule:", e);
    }
  }

  _setDefaultEditValue() {
    const ch = this._channels[this._activeChannel];
    if (!ch) return;
    if (ch.value_type === "number") {
      this._editValue = ch.default ?? ch.min ?? 0;
    } else if (ch.value_type === "enum") {
      this._editValue = parseInt(Object.keys(ch.options)[0]);
    }
  }

  _getColor(channelId, value) {
    const ch = this._channels[channelId];
    if (!ch) return "#808080";

    if (ch.value_type === "number") {
      const min = ch.min ?? 0;
      const max = ch.max ?? 100;
      const ratio = Math.min(1, Math.max(0, (value - min) / (max - min)));
      // Blue (low) -> neutral grey (middle) -> orange-red (high)
      const lerp = (a, b, t) => a.map((x, i) => Math.round(x + (b[i] - x) * t));
      const low = [66, 133, 244];
      const mid = [158, 167, 173];
      const high = [234, 88, 54];
      const rgb = ratio < 0.5
        ? lerp(low, mid, ratio * 2)
        : lerp(mid, high, (ratio - 0.5) * 2);
      return `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
    }

    // Enum: distinct colors
    const colors = [
      "#4CAF50", "#2196F3", "#FF9800", "#9C27B0",
      "#00BCD4", "#F44336", "#8BC34A",
    ];
    const keys = Object.keys(ch.options).map(Number);
    const idx = keys.indexOf(value);
    return colors[idx % colors.length];
  }

  _getValueAtSlot(day, slotIndex) {
    if (!this._schedule || !this._activeChannel) return null;
    const channel = this._schedule.channels?.[this._activeChannel];
    if (!channel?.days) return null;

    const slotTime = HOURS[slotIndex];

    // Find value: walk backward through current day, then previous days.
    // Offset 7 wraps to the same weekday of the previous week so slots
    // before a day's first entry inherit the schedule instead of showing
    // as empty.
    const dayIdx = DAYS.indexOf(day);

    for (let offset = 0; offset < 8; offset++) {
      const checkDayIdx = (dayIdx - offset + 7) % 7;
      const checkDay = DAYS[checkDayIdx];
      const entries = channel.days[checkDay] || [];

      if (entries.length === 0) continue;

      if (offset === 0) {
        // Current day: find last entry at or before slotTime
        const candidates = entries.filter(e => e.time <= slotTime);
        if (candidates.length > 0) {
          return candidates[candidates.length - 1].value;
        }
      } else {
        // Previous days: take last entry
        return entries[entries.length - 1].value;
      }
    }
    return null;
  }

  _getNowSlot() {
    const now = new Date();
    const dayIdx = (now.getDay() + 6) % 7; // JS: 0=Sun, we need 0=Mon
    const slotIdx = now.getHours() * 2 + (now.getMinutes() >= 30 ? 1 : 0);
    return { dayIdx, slotIdx };
  }

  _onCellMouseDown(day, slotIndex, e) {
    e.preventDefault();
    // Release implicit pointer capture so pointerenter fires on
    // neighbouring cells while dragging (relevant for touch)
    if (e.target.hasPointerCapture?.(e.pointerId)) {
      e.target.releasePointerCapture(e.pointerId);
    }
    this._isDragging = true;
    this._dragStart = { day, slotIndex };
    this._applyValueToSlot(day, slotIndex, this._editValue);
    document.addEventListener("pointerup", this._boundMouseUp);
  }

  _onCellMouseEnter(day, slotIndex) {
    if (!this._isDragging) return;
    this._applyValueToSlot(day, slotIndex, this._editValue);
  }

  _onMouseUp() {
    if (this._isDragging) {
      this._isDragging = false;
      this._saveSchedule();
    }
    document.removeEventListener("pointerup", this._boundMouseUp);
  }

  _applyValueToSlot(day, slotIndex, value) {
    if (!this._schedule || !this._activeChannel) return;

    const channel = this._schedule.channels?.[this._activeChannel] ?? {
      enabled: true,
      days: {},
    };
    if (!this._schedule.channels) this._schedule.channels = {};
    this._schedule.channels[this._activeChannel] = channel;

    if (!channel.days) channel.days = {};
    if (!channel.days[day]) channel.days[day] = [];

    const time = HOURS[slotIndex];
    const entries = channel.days[day];

    // Remove existing entry at this time
    const filtered = entries.filter(e => e.time !== time);
    filtered.push({ time, value });
    filtered.sort((a, b) => a.time.localeCompare(b.time));

    // Optimize: remove entry if same value as previous
    const optimized = [];
    for (let i = 0; i < filtered.length; i++) {
      if (i === 0 || filtered[i].value !== filtered[i - 1].value) {
        optimized.push(filtered[i]);
      }
    }

    channel.days[day] = optimized;
    this.requestUpdate();
  }

  async _saveSchedule() {
    if (!this._hass || !this._activeChannel || !this._schedule) return;
    const channel = this._schedule.channels?.[this._activeChannel];
    if (!channel?.days) return;

    // Save each day individually
    for (const day of DAYS) {
      const entries = channel.days[day] || [];
      try {
        await this._hass.callWS({
          type: "heishamon_scheduler/set_schedule",
          channel_id: this._activeChannel,
          day: day,
          entries: entries,
          schedule_id: "default",
        });
      } catch (e) {
        console.error(`Failed to save ${day}:`, e);
      }
    }
  }

  _copyDayToAll(sourceDay) {
    if (!this._schedule || !this._activeChannel) return;
    const channel = this._schedule.channels?.[this._activeChannel];
    if (!channel?.days?.[sourceDay]) return;

    const source = JSON.parse(JSON.stringify(channel.days[sourceDay]));
    for (const day of DAYS) {
      channel.days[day] = JSON.parse(JSON.stringify(source));
    }
    this.requestUpdate();
    this._saveSchedule();
  }

  _copyWeekdaysToWeekend() {
    if (!this._schedule || !this._activeChannel) return;
    const channel = this._schedule.channels?.[this._activeChannel];
    if (!channel?.days?.["mon"]) return;

    const source = JSON.parse(JSON.stringify(channel.days["mon"]));
    for (const day of ["sat", "sun"]) {
      channel.days[day] = JSON.parse(JSON.stringify(source));
    }
    this.requestUpdate();
    this._saveSchedule();
  }

  _clearDay(day) {
    if (!this._schedule || !this._activeChannel) return;
    const channel = this._schedule.channels?.[this._activeChannel];
    if (!channel?.days) return;

    channel.days[day] = [];
    this.requestUpdate();
    this._saveSchedule();
  }

  _clearAll() {
    if (!this._schedule || !this._activeChannel) return;
    const channel = this._schedule.channels?.[this._activeChannel];
    if (!channel?.days) return;

    for (const day of DAYS) {
      channel.days[day] = [];
    }
    this.requestUpdate();
    this._saveSchedule();
  }

  _renderValuePicker() {
    if (!this._channels || !this._activeChannel) return html``;
    const ch = this._channels[this._activeChannel];

    if (ch.value_type === "number") {
      return html`
        <div class="value-picker">
          <label>Wert:</label>
          <input
            type="range"
            min="${ch.min}"
            max="${ch.max}"
            step="${ch.step || 1}"
            .value="${this._editValue}"
            @input="${(e) => { this._editValue = Number(e.target.value); this.requestUpdate(); }}"
          />
          <span class="value-display">
            ${this._editValue}${ch.unit || ""}
          </span>
        </div>
      `;
    }

    if (ch.value_type === "enum") {
      return html`
        <div class="value-picker">
          <label>Modus:</label>
          <select
            @change="${(e) => { this._editValue = Number(e.target.value); this.requestUpdate(); }}"
          >
            ${Object.entries(ch.options).map(
              ([val, label]) => html`
                <option value="${val}" ?selected="${Number(val) === this._editValue}">
                  ${label}
                </option>
              `
            )}
          </select>
        </div>
      `;
    }

    return html``;
  }

  _renderLegend() {
    if (!this._channels || !this._activeChannel) return html``;
    const ch = this._channels[this._activeChannel];

    if (ch.value_type === "enum") {
      return html`
        <div class="legend">
          ${Object.entries(ch.options).map(
            ([val, label]) => html`
              <div class="legend-item">
                <div
                  class="legend-swatch"
                  style="background: ${this._getColor(this._activeChannel, Number(val))}"
                ></div>
                ${label}
              </div>
            `
          )}
        </div>
      `;
    }

    if (ch.value_type === "number") {
      const mid = Math.round((ch.min + ch.max) / 2);
      const gradient = `linear-gradient(to right, ${this._getColor(
        this._activeChannel, ch.min
      )}, ${this._getColor(this._activeChannel, mid)}, ${this._getColor(
        this._activeChannel, ch.max
      )})`;
      return html`
        <div class="legend">
          <div class="legend-item">${ch.min}${ch.unit || ""}</div>
          <div class="legend-gradient" style="background: ${gradient}"></div>
          <div class="legend-item">${ch.max}${ch.unit || ""}</div>
        </div>
      `;
    }

    return html``;
  }

  render() {
    if (!this._schedule || !this._channels) {
      return html`
        <ha-card>
          <div class="no-schedule">Lade Zeitplan...</div>
        </ha-card>
      `;
    }

    const now = this._getNowSlot();

    return html`
      <ha-card>
        <div class="card-header">
          <span>HeishaMon Zeitplan</span>
        </div>

        <div class="tabs">
          ${Object.entries(this._channels).map(
            ([id, ch]) => html`
              <button
                class="tab ${this._activeChannel === id ? "active" : ""}"
                @click="${() => {
                  this._activeChannel = id;
                  this._setDefaultEditValue();
                  this.requestUpdate();
                }}"
              >
                ${ch.name}
              </button>
            `
          )}
        </div>

        <div class="toolbar">
          ${this._renderValuePicker()}
          <div class="actions">
            <button class="btn" @click="${() => this._copyDayToAll(DAYS[now.dayIdx])}">
              Heute → Alle
            </button>
            <button class="btn" @click="${this._clearAll}">
              Löschen
            </button>
            <button class="btn" @click="${this._loadSchedule}">
              ↻
            </button>
          </div>
        </div>

        ${this._renderLegend()}

        <div class="schedule-grid">
          <table>
            <thead>
              <tr class="hour-markers">
                <th class="day-label"></th>
                ${Array.from({ length: 8 }, (_, i) => html`
                  <th colspan="6">${String(i * 3).padStart(2, "0")}</th>
                `)}
              </tr>
            </thead>
            <tbody>
              ${DAYS.map(
                (day, dayIdx) => html`
                  <tr>
                    <th class="day-label">${this._dayLabels[day]}</th>
                    ${HOURS.map((_, slotIdx) => {
                      const value = this._getValueAtSlot(day, slotIdx);
                      const isNow = dayIdx === now.dayIdx && slotIdx === now.slotIdx;
                      const classes = [
                        "cell",
                        isNow ? "now-marker" : "",
                        value === null ? "empty" : "",
                        slotIdx % 6 === 5 ? "h3" : "",
                        slotIdx === 0 ? "slot-first" : "",
                        slotIdx === HOURS.length - 1 ? "slot-last" : "",
                      ].join(" ");
                      const color = value !== null
                        ? this._getColor(this._activeChannel, value)
                        : "";
                      return html`
                        <td
                          class="${classes}"
                          style="${color ? `background-color: ${color}` : ""}"
                          title="${this._dayLabels[day]} ${HOURS[slotIdx]}: ${value !== null ? value : "-"}"
                          @pointerdown="${(e) => this._onCellMouseDown(day, slotIdx, e)}"
                          @pointerenter="${() => this._onCellMouseEnter(day, slotIdx)}"
                        ></td>
                      `;
                    })}
                  </tr>
                `
              )}
            </tbody>
          </table>
        </div>
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
