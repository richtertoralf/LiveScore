import { t } from './i18n.js';
import { $, escape as e, Connection, uuid, message } from './common.js';
const definitions = {
  event: {title:t('Veranstaltung'), fields:[['name',t('Name')],['date_from',t('Datum von'),'date'],['date_to',t('Datum bis'),'date'],['location',t('Ort'),'optional'],['logo_path',t('Logo-Pfad'),'optional'],['score_label',t('Score-Bezeichnung')]]},
  'play-areas': {title:t('Play Areas'), key:'play_areas', fields:[['label',t('Bezeichnung (z. B. Field 1)')]]},
  participants: {title:t('Teilnehmer'), key:'participants', fields:[['name',t('Name')],['short_name',t('Kurzname'),'optional'],['country_code',t('Ländercode (optional, z. B. DE)'),'optional'],['logo_path',t('Logo-Pfad'),'optional']]},
  referees: {title:t('Referees'), key:'referees', fields:[['name',t('Name')],['country_code',t('Ländercode (optional, z. B. DE)'),'optional']]},
  matches: {title:t('Spielplan'), key:'matches', fields:[['date',t('Datum'),'date'],['time',t('Uhrzeit'),'time'],['play_area_id',t('Play Area'),'areas'],['round',t('Runde / Bezeichnung'),'optional'],['participant_1',t('Teilnehmer 1'),'people'],['participant_2',t('Teilnehmer 2'),'people'],['placeholder_1',t('Platzhalter 1'),'optional'],['placeholder_2',t('Platzhalter 2'),'optional']]}
};
let initialized = false, selectionToken = null;
const app = new Connection(render);
function selectOptions(kind, state) {
  return '<option value="">'+(kind === 'people' ? t('Noch offen') : t('Bitte wählen'))+'</option>' + (kind === 'people' ? state.participants : state.play_areas).map(i => `<option value="${e(i.id)}">${e(i.name || i.label)}</option>`).join('');
}
function render(state) {
  if (selectionToken !== state.selection_token) {
    if (document.querySelector('form[data-dirty]')) message(t('Veranstaltung wurde gewechselt. Ungespeicherte Formulare wurden geschlossen.'));
    initialized = false; selectionToken = state.selection_token;
  }
  if (!state.active_event_id) {
    $('#forms').innerHTML = `<p>${t("Bitte unter")} <a href="/events">${t("Veranstaltungen")}</a> ${t("eine Veranstaltung anlegen, importieren oder auswählen.")}</p>`;
    $('#config-status').textContent = t('Keine Veranstaltung ausgewählt.');
    return;
  }
  if (!initialized) {
    $('#forms').innerHTML = Object.entries(definitions).map(([kind, def]) => `<details open><summary>${def.title}</summary><form data-kind="${kind}"><fieldset><input name="id" type="hidden"><div class="form-grid">${def.fields.map(([key,label,type]) => `<div><label for="${kind}-${key}">${label}</label>${['people','areas'].includes(type) ? `<select name="${key}" id="${kind}-${key}" ${type === 'areas' ? 'required' : ''}>${selectOptions(type,state)}</select>` : `<input name="${key}" id="${kind}-${key}" type="${['date','time'].includes(type) ? type : 'text'}" ${type !== 'optional' ? 'required' : ''} maxlength="${key === 'short_name' ? 40 : key === 'logo_path' ? 500 : 200}">`}</div>`).join('')}</div>${kind === 'matches' ? '<div id="official-slots" class="form-grid"></div>' : ''}<button type="submit" class="primary">${t("Speichern")}</button><div class="edit-list"><button type="button" data-new="${kind}">${kind === 'event' ? t('Gespeicherten Stand laden') : t('Neuer Eintrag')}</button></div></fieldset></form><div class="edit-list" id="list-${kind}"></div></details>`).join('');
    initialized = true;
    Object.keys(definitions).forEach(kind => fill(kind, kind === 'event' ? state.event : null, state));
  }
  const active = state.matches.find(m => m.id === state.active_match_id);
  const locked = active && ['ready','live','paused'].includes(active.status);
  $('#config-status').textContent = locked ? t('Konfiguration gesperrt: Spiel ist vorbereitet oder läuft.') : t('Änderungen werden beim Speichern sofort für alle Bediener wirksam.');
  document.querySelectorAll('fieldset').forEach(f => f.disabled = !!locked);
  for (const [kind, def] of Object.entries(definitions)) {
    const form = $(`form[data-kind="${kind}"]`);
    if (!form.dataset.dirty) {
      if (kind === 'event') fill(kind, state.event, state);
      else fill(kind, state[def.key].find(item => item.id === form.elements.namedItem('id').value), state);
    }
    if (def.key) $(`#list-${kind}`).innerHTML = state[def.key].map(i => `<button type="button" data-edit="${kind}" data-id="${e(i.id)}" ${kind === 'matches' && i.status !== 'scheduled' ? 'disabled' : ''}>${e(i.name || i.label || `${i.date} ${i.time.slice(0,5)} · ${i.round || i.id}`)}${i.status ? ' · ' + e(t({scheduled:'NÄCHSTES SPIEL',ready:'BEREIT',live:'LIVE',paused:'PAUSE',finished:'BEENDET'}[i.status])) : ''}</button>`).join('');
  }
}
function fill(kind, item, state = app.state) {
  const form = $(`form[data-kind="${kind}"]`);
  form.reset(); delete form.dataset.dirty; form.dataset.revision = state.revision;
  form.dataset.eventId = state.active_event_id; form.dataset.selectionToken = state.selection_token;
  form.elements.namedItem('id').value = item?.id || uuid();
  if (kind === 'matches') {
    const officials = item?.officials || [];
    // Imported assignments beyond three slots must remain visible and editable.
    $('#official-slots').innerHTML = Array.from({length:Math.max(3,officials.length)}, (_, index) => {
      const options = `<option value="">${t("Nicht besetzt")}</option>` + state.referees.map(referee => `<option value="${e(referee.id)}" ${referee.id === officials[index] ? 'selected' : ''}>${e(referee.name)}${referee.country_code ? ' (' + e(referee.country_code) + ')' : ''}</option>`).join('');
      return `<div><label for="official-${index}">${t("Official")} ${index+1} (${t("optional")})</label><select id="official-${index}" name="official_slot_${index}" data-official>${options}</select></div>`;
    }).join('');
  }
  for (const [key,,type] of definitions[kind].fields) {
    const input = form.elements.namedItem(key);
    if (['people','areas'].includes(type)) input.innerHTML = selectOptions(type,state);
    input.value = item?.[key] ?? (key === 'score_label' ? t('Score') : '');
  }
}
$('#forms').addEventListener('input', event => { const form = event.target.closest('form'); if (form) form.dataset.dirty = 'true'; });
$('#forms').addEventListener('click', event => {
  const target = event.target.closest('button'); if (!target) return;
  if (target.dataset.new) fill(target.dataset.new,target.dataset.new === 'event' ? app.state.event : null);
  if (target.dataset.edit) {
    const kind = target.dataset.edit;
    fill(kind,app.state[definitions[kind].key].find(i => i.id === target.dataset.id));
  }
});
$('#forms').addEventListener('submit', async event => {
  event.preventDefault(); const form = event.target, kind = form.dataset.kind;
  const data = Object.fromEntries(new FormData(form));
  if (kind === 'event') delete data.id;
  if (kind === 'matches') {
    data.participant_1 ||= null; data.participant_2 ||= null;
    data.officials = Array.from(form.querySelectorAll('[data-official]'), input => input.value).filter(Boolean);
    for (const key of Object.keys(data)) if (key.startsWith('official_slot_')) delete data[key];
  }
  const success = await app.send(`config/${kind}`,{data},Number(form.dataset.revision),{event_id:form.dataset.eventId,selection_token:form.dataset.selectionToken});
  if (success) { fill(kind,kind === 'event' ? app.state.event : null); render(app.state); app.controls(); message(t('Gespeichert.')); }
  else if (Number(form.dataset.revision) !== app.state.revision) message(t('Daten wurden zwischenzeitlich geändert. Eintrag erneut aus der Liste laden, Änderungen prüfen und speichern.'));
});
