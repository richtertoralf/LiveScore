import { t, errorText } from './i18n.js';
import { auth, csrfHeaders, canOperate } from './auth-client.js';
export const $ = (selector) => document.querySelector(selector);
export const escape = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function uuid() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}
export function message(text) { $('#message').textContent = text; }
export class Connection {
  constructor(render) {
    this.render = render; this.state = null; this.online = false; this.busy = false; this.socket = null;
    this.connect();
    this.watchdog = setInterval(() => {
      if (this.online && Date.now() - this.lastSeen > 12000) {
        this.online = false; this.controls(); this.socket.close();
      }
    }, 2000);
    window.addEventListener('offline', () => {
      this.online = false; this.controls(); this.socket?.close();
    });
    window.addEventListener('online', () => {
      if (!this.socket || this.socket.readyState > 1) { clearTimeout(this.retry); this.connect(); }
    });
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden && (!this.socket || this.socket.readyState > 1)) { clearTimeout(this.retry); this.connect(); }
    });
    this.controls();
  }
  controls() {
    $('#connection').textContent = this.online ? t('Verbunden') : t('Offline · Bedienung gesperrt');
    $('#connection').classList.toggle('offline', !this.online);
    document.querySelectorAll('button[data-action], button[type=submit], #finish-confirm, #period-confirm').forEach(button => {
      button.disabled = !canOperate() || !this.online || this.busy || button.dataset.disabled === 'true';
    });
    if ($('#import-file')) $('#import-file').disabled = !this.online || this.busy;
  }
  accept(state, initial = false) {
    if (!initial && this.state && (state.stream_id !== this.state.stream_id || state.stream_revision <= this.state.stream_revision)) return;
    const label = $('#active-event-name');
    if (label) label.textContent = state.event?.name || (state.active_event_id ? t('Noch nicht eingerichtet') : t('Keine ausgewählt'));
    this.state = state; this.render(state); this.controls();
  }
  connect() {
    if (!navigator.onLine) { this.retry = setTimeout(() => this.connect(), 1000); return; }
    const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/v1/ws`);
    this.socket = ws; let initial = true;
    ws.onmessage = event => {
      if (this.socket !== ws || !navigator.onLine) return;
      const data = JSON.parse(event.data); this.lastSeen = Date.now(); this.online = true;
      if (!data.heartbeat) { this.accept(data, initial); initial = false; }
      this.controls();
    };
    ws.onclose = async () => {
      if (this.socket !== ws) return;
      this.online = false; this.controls();
      if (auth.enabled) {
        try {
          const session = await fetch('/api/auth/session').then(r => r.json());
          if (!session.authenticated) { location.replace('/login'); return; }
        } catch {}
      }
      this.retry = setTimeout(() => this.connect(), 1000);
    };
    ws.onerror = () => ws.close();
  }
  async send(path, fields, revision = this.state?.revision, context = {event_id:this.state?.active_event_id, selection_token:this.state?.selection_token}) {
    if (!this.state || !this.online || this.busy) return false;
    this.busy = true; this.controls(); message('');
    const catalog = path.startsWith('event-catalog/');
    const payload = {request_id: uuid(), ...(catalog ? {catalog_session:this.state.stream_id} : context), ...fields};
    if (!catalog && !path.endsWith('/score') && !path.endsWith('/counter')) payload.expected_revision = revision;
    try {
      let response;
      // Retry only transport errors, using the exact same persisted request ID.
      for (let attempt = 0; attempt < 2; attempt++) {
        try {
          response = await fetch(`/api/v1/${path}`, {method:'POST', headers:csrfHeaders(), body:JSON.stringify(payload), signal:AbortSignal.timeout(8000)});
          break;
        } catch (error) { if (attempt === 1) throw error; }
      }
      const data = await response.json();
      if (!response.ok) {
        if (response.status === 401) { location.replace('/login'); return false; }
        message(errorText(data.detail));
        const fresh = await fetch('/api/v1/tournament').then(r => r.json()); this.accept(fresh);
        return false;
      }
      this.accept(data);
      if (!catalog && this.state.selection_token !== context.selection_token) {
        message(t('Veranstaltung wurde inzwischen gewechselt. Bitte aktuellen Stand prüfen.')); return false;
      }
      return data;
    } catch (error) {
      message(t('Verbindung unterbrochen. Aktion möglicherweise gespeichert; aktuellen Stand prüfen, bevor erneut gebucht wird.'));
      this.online = false; this.socket.close(); return false;
    } finally {
      await new Promise(resolve => setTimeout(resolve, 250));
      this.busy = false; this.controls();
    }
  }
}
