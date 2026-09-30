import { t, errorText } from './i18n.js';
import { csrfHeaders, isAdmin } from './auth-client.js';
import { $, escape as e, Connection, message } from './common.js';
let preview = null, uploadGeneration = 0, resetTarget = null;
const app = new Connection(render);
function description(event) {
  return `${e(event?.date_from || '')}${event?.date_to !== event?.date_from ? ' – ' + e(event?.date_to || '') : ''}${event?.location ? ' · ' + e(event.location) : ''}`;
}
function render(state) {
  const match = state.matches.find(item => item.id === state.active_match_id);
  const blocked = match && ['ready','live','paused'].includes(match.status);
  $('#switch-status').textContent = blocked ? t('Wechsel gesperrt: Spiel zuerst beenden oder Vorbereitung zurücknehmen.') : '';
  $('#catalog-list').innerHTML = state.catalog.items.map(item => {
    const active = item.id === state.active_event_id;
    // Nur Admins: Veranstaltung aus der gespeicherten Importdatei neu einlesen.
    const reset = !isAdmin() ? '' : item.reset_available
      ? `<button data-action="reset-event" data-id="${e(item.id)}" class="danger" data-disabled="${active && blocked}">${t('Zurücksetzen')}</button>`
      : `<p class="muted">${t('Zurücksetzen erst nach einem JSON-Import dieser Veranstaltung möglich.')}</p>`;
    return `<article class="panel ${active ? 'active-event' : ''}" data-event-id="${e(item.id)}"><h2>${e(item.event?.name || t('Noch nicht eingerichtet'))}${active ? ' · ' + t('AKTIV') : ''}</h2><p class="muted">${description(item.event)}</p><p>${item.matches} ${t("Spiele")} · ${item.participants} ${t("Teilnehmer")} · ${item.referees} ${t("Referees")} · ${item.play_areas} ${t("Play Areas")}</p><div class="event-buttons"><button data-action="select-event" data-id="${e(item.id)}" data-disabled="${active}" class="${active ? '' : 'primary'}">${active ? t('Ausgewählt') : t('Auswählen')}</button><a href="/api/v1/event-catalog/${encodeURIComponent(item.id)}/export" download>${t("JSON exportieren")}</a>${reset}</div></article>`;
  }).join('') || `<p>${t("Noch keine Veranstaltungen gespeichert.")}</p>`;
  if ($('#reset-dialog').open && !state.catalog.items.some(item => item.id === resetTarget?.id && item.reset_available)) $('#reset-dialog').close();
  if (preview && preview.session !== state.stream_id) {
    preview = null; $('#import-preview').hidden = true; $('#replace-dialog').close();
    message(t('Server wurde neu gestartet. Bitte Import-Vorschau erneut laden.'));
  }
}
$('#catalog-list').addEventListener('click', async event => {
  const button = event.target.closest('button[data-action]');
  if (!button || button.disabled) return;
  if (button.dataset.action === 'reset-event') {
    const item = app.state.catalog.items.find(entry => entry.id === button.dataset.id);
    resetTarget = {id:item.id, session:app.state.stream_id};
    $('#reset-name').textContent = item.event?.name || item.id; $('#reset-dialog').showModal(); return;
  }
  const result = await app.send('event-catalog/select',{event_id:button.dataset.id,selection_token:app.state.selection_token});
  if (result) message(t('Veranstaltung ausgewählt. Bedienung und Konfiguration verwenden jetzt diese Veranstaltung.'));
});
$('#create-event').addEventListener('submit', async event => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.target));
  if (await app.send('event-catalog/create',{event:data})) {
    event.target.reset(); $('#new-event').open = false;
    message(t('Veranstaltung angelegt. Zum Konfigurieren bitte in der Liste auswählen.'));
  }
});
$('#import-file').addEventListener('change', async event => {
  const generation = ++uploadGeneration;
  preview = null; $('#import-preview').hidden = true; message('');
  const file = event.target.files[0];
  if (!file) return;
  if (file.size > 10 * 1024 * 1024) { message(t('Datei ist größer als 10 MiB.')); return; }
  try {
    const json_text = await file.text();
    const stem = file.name.replace(/\.json$/i,'');
    const event_id = /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$/.test(stem) ? stem : null;
    const response = await fetch('/api/v1/event-catalog/import/preview', {
      method:'POST',headers:csrfHeaders(),body:JSON.stringify({json_text,event_id}),signal:AbortSignal.timeout(15000)
    });
    const data = await response.json();
    if (generation !== uploadGeneration) return;
    if (!response.ok) { message(errorText(data.detail)); return; }
    preview = {json_text,event_id:data.event_id,preview_token:data.preview_token,session:app.state.stream_id,name:data.event.name};
    // Nur Admins dürfen eine vorhandene Veranstaltung ersetzen, z. B. um Testspiele vollständig zurückzusetzen.
    const replace = data.collision && isAdmin() ? `<button data-action="replace-import" class="danger">${t('Bestehende Veranstaltung ersetzen')}</button>` : '';
    $('#import-preview').innerHTML = `<h2>${t("Diese Veranstaltung importieren?")}</h2><p><strong>${e(data.event.name)}</strong></p><p>${description(data.event)}</p><p>${data.participants} ${t("Teilnehmer")} · ${data.referees} ${t("Referees")} · ${data.play_areas} ${t("Play Areas")} · ${data.matches} ${t("Spiele")}</p><p>${data.collision ? t('Eine Veranstaltung mit dieser ID existiert bereits. Vorhandene Daten bleiben erhalten.') : t('Die Datei wird als eigene Veranstaltung gespeichert.')}</p><div class="stack"><button data-action="confirm-import" class="primary" data-as-new="${data.collision}">${data.collision ? t('Als neue Veranstaltung importieren') : t('Importieren')}</button>${replace}<button data-action="cancel-import">${t("Abbrechen")}</button></div>`;
    $('#import-preview').hidden = false; app.controls();
  } catch (error) { if (generation === uploadGeneration) message(t('Datei konnte nicht geprüft werden. Verbindung und JSON-Datei prüfen.')); }
});
$('#import-preview').addEventListener('click', async event => {
  const button = event.target.closest('button[data-action]');
  if (!button || button.disabled) return;
  if (button.dataset.action === 'cancel-import') {
    preview = null; ++uploadGeneration; $('#import-preview').hidden = true; $('#import-file').value = ''; return;
  }
  if (!preview) return;
  const {session, name, ...payload} = preview;
  if (session !== app.state.stream_id) { message(t('Bitte Import-Vorschau erneut laden.')); return; }
  if (button.dataset.action === 'replace-import') {
    $('#replace-name').textContent = name; $('#replace-dialog').showModal(); return;
  }
  const result = await app.send('event-catalog/import',{...payload,as_new:button.dataset.asNew === 'true'});
  if (result) {
    preview = null; $('#import-preview').hidden = true; $('#import-file').value = '';
    message(t('Veranstaltung importiert. Sie kann jetzt in der Liste ausgewählt werden.'));
  } else if (app.state.catalog.items.some(item => item.id === preview.event_id)) {
    button.dataset.asNew = 'true'; button.textContent = t('Als neue Veranstaltung importieren');
  }
});
$('#replace-cancel').onclick = () => $('#replace-dialog').close();
$('#replace-confirm').onclick = async () => {
  $('#replace-dialog').close();
  if (!preview) return;
  const {session, name, ...payload} = preview;
  if (session !== app.state.stream_id) { message(t('Bitte Import-Vorschau erneut laden.')); return; }
  if (await app.send('event-catalog/replace',payload)) {
    preview = null; $('#import-preview').hidden = true; $('#import-file').value = '';
    message(t('Veranstaltung ersetzt. Alle Daten entsprechen jetzt der Importdatei.'));
  }
};
$('#reset-cancel').onclick = () => $('#reset-dialog').close();
$('#reset-confirm').onclick = async () => {
  $('#reset-dialog').close();
  if (!resetTarget || resetTarget.session !== app.state.stream_id) { message(t('Server wurde neu gestartet. Bitte Anzeige prüfen.')); return; }
  if (await app.send('event-catalog/reset',{event_id:resetTarget.id}))
    message(t('Veranstaltung zurückgesetzt. Alle Daten entsprechen wieder der gespeicherten Importdatei.'));
};
