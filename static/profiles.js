import {t, profileText, errorText} from './i18n.js';
import {isAdmin} from './auth-client.js';
import {$, escape as e, uuid, message} from './common.js';

const languages = ['de','en','cs'];
let library = null, source = 'event', selection = null, dirty = false, loading = false;
let eventProfileSignature = null;
let draft = null, formRevision = null, formContext = null, formLibraryRevision = null;
const structure = p => [p?.periods || 1, (p?.counters || []).map(c => [c.id,c.reset_each_period]).sort(), p?.score_mode || 'total', p?.sets_enabled || false];
const sameStructure = (a,b) => JSON.stringify(structure(a)) === JSON.stringify(structure(b));
function fresh() {
  return {sport:'generic',ruleset:'',periods:1,period_label:'Abschnitt',counters:[],score_mode:'total',score_steps:[1],sets_enabled:false,roles:{},show_details:true,show_officials:true,
    translations:Object.fromEntries(languages.map(lang => [lang,{name:'',period_label:{de:'Abschnitt',en:'Period',cs:'Část'}[lang],break_label:{de:'Pause zwischen Abschnitten',en:'Break between periods',cs:'Přestávka mezi částmi'}[lang],hint:'',score_label:'',sets_label:{de:'Gewonnene Sätze',en:'Sets won',cs:'Vyhrané sety'}[lang]}]))};
}
function languageInputs(labels, fields, prefix) {
  return `<div class="profile-languages">${languages.map(lang => `<section><h3>${lang.toUpperCase()}</h3>${fields.map(([key,title,required]) => `<label for="${prefix}-${lang}-${key}">${t(title)}</label><input id="${prefix}-${lang}-${key}" data-profile-language="${lang}" data-text="${key}" value="${e(labels?.[lang]?.[key])}" ${required ? 'required' : ''} maxlength="${key === 'hint' ? 500 : 200}">`).join('')}</section>`).join('')}</div>`;
}
function read() {
  if (!draft) return;
  const form = $('#profile-form');
  draft.periods = Number(form.querySelector('[name=periods]').value);
  draft.score_mode = form.querySelector('[name=score_mode]').value;
  draft.score_steps = form.querySelector('[name=score_steps]').value.split(',').map(s => Number(s.trim()));
  for (const key of ['sets_enabled','show_details','show_officials']) draft[key] = form.querySelector(`[name=${key}]`).checked;
  draft.roles = form.querySelector('[name=roles_enabled]').checked ? Object.fromEntries(['participant_1','participant_2'].map((role,index) => [role,{id:draft.roles[role]?.id || uuid(),labels:Object.fromEntries(languages.map(lang => [lang,form.querySelector(`#role-${index}-${lang}-label`).value.trim()]))}])) : {};
  for (const input of form.querySelectorAll('#profile-texts input')) draft.translations[input.dataset.profileLanguage][input.dataset.text] = input.value.trim();
  draft.period_label = draft.translations.de.period_label || draft.period_label;
  for (const card of form.querySelectorAll('[data-counter-id]')) {
    const counter = draft.counters.find(c => c.id === card.dataset.counterId);
    counter.enabled = card.querySelector('[name=enabled]').checked;
    counter.reset_each_period = card.querySelector('[name=reset_each_period]').checked;
    for (const key of ['warning_at','critical_at']) counter[key] = card.querySelector(`[name=${key}]`).value === '' ? null : Number(card.querySelector(`[name=${key}]`).value);
    for (const input of card.querySelectorAll('[data-text]')) counter.translations[input.dataset.profileLanguage][input.dataset.text] = input.value.trim();
    for (const key of ['label','warning_label','critical_label']) counter[key] = counter.translations.de[key] || (key === 'label' ? counter.label : '');
  }
}
function editor(app) {
  const state = app.state;
  const used = state.matches.some(m => m.status !== 'scheduled');
  const structureLocked = source === 'event' && used;
  const selectedEntry = library?.profiles.find(p => 'library:'+p.id === source);
  $('#profile-management').innerHTML = `<details open><summary>${t('Sportprofile')}</summary>
    <p class="muted">${t('Die Bibliothek ist unabhängig von Veranstaltungen. Beim Übernehmen wird eine eigene Kopie gespeichert.')}</p>
    <label for="profile-source">${t('Profil auswählen')}</label><select id="profile-source">
      ${state.event ? `<option value="event">${t('Profil dieser Veranstaltung')}</option>` : ''}
      <option value="new">${t('Neues Profil')}</option><option value="none">${t('Ohne Sportprofil')}</option>
      ${(library?.profiles || []).map(p => `<option value="library:${e(p.id)}">${e(profileText(p.profile,'name'))}</option>`).join('')}
      ${(library?.event_profiles || []).filter(p => p.id !== state.active_event_id).map(p => `<option value="event:${e(p.id)}">${e(p.event_name)} · ${e(profileText(p.profile,'name'))}</option>`).join('')}</select>
    <p id="profile-status" class="muted">${used ? t('Erfassungsstruktur bereits verwendet. Bezeichnungen und Anzeigeoptionen bleiben bearbeitbar.') : t('Alle Profilfelder sind vor der Vorbereitung des ersten Spiels bearbeitbar.')}</p>
    <form id="profile-form"><fieldset id="profile-edit">
      ${draft ? `<fieldset data-profile-structure><label for="profile-periods">${t('Anzahl der Abschnitte')}</label><input id="profile-periods" name="periods" type="number" min="1" step="1" required value="${draft.periods}"></fieldset>
      <fieldset data-profile-structure><label for="profile-score-mode">${t('Punkteerfassung')}</label><select id="profile-score-mode" name="score_mode">${[['total','Fortlaufender Punktestand'],['period','Punkte je Abschnitt'],['none','Kein Punktestand']].map(([value,label]) => `<option value="${value}" ${draft.score_mode===value ? 'selected' : ''}>${t(label)}</option>`).join('')}</select>
      <label class="checkbox"><input name="sets_enabled" type="checkbox" ${draft.sets_enabled ? 'checked' : ''}>${t('Gewonnene Sätze manuell erfassen')}</label></fieldset>
      <label for="profile-score-steps">${t('Punkteschritte (z. B. 1, 2)')}</label><input id="profile-score-steps" name="score_steps" required pattern="[0-9]+([ ]*,[ ]*[0-9]+)*" value="${draft.score_steps.join(', ')}">
      <label class="checkbox"><input name="show_details" type="checkbox" ${draft.show_details ? 'checked' : ''}>${t('Spielplanangaben in der Bedienung anzeigen')}</label>
      <label class="checkbox"><input name="show_officials" type="checkbox" ${draft.show_officials ? 'checked' : ''}>${t('Officials in der Bedienung anzeigen')}</label>
      <label class="checkbox"><input name="roles_enabled" type="checkbox" ${Object.keys(draft.roles).length ? 'checked' : ''}>${t('Feste Rollen für Teilnehmer 1 und 2')}</label>
      <div id="profile-roles">${['participant_1','participant_2'].map((role,index) => `<h3>${t(index===0 ? 'Teilnehmer 1' : 'Teilnehmer 2')}</h3>${languageInputs(Object.fromEntries(languages.map(lang => [lang,{label:draft.roles[role]?.labels?.[lang] || ''}])),[['label','Rollenbezeichnung',false]],`role-${index}`)}`).join('')}</div>
      <div id="profile-texts">${languageInputs(draft.translations,[['name','Profilname',true],['period_label','Abschnittsbezeichnung',true],['break_label','Pausenbezeichnung',true],['hint','Hinweis (optional)',false],['score_label','Punktebezeichnung',false],['sets_label','Satzstandbezeichnung',false]],'profile')}</div>
      <h2>${t('Zähler')}</h2><p class="muted">${t('Anzeigegrenzen ändern nur die Hervorhebung. Werte werden nicht begrenzt und keine Regeln ausgewertet.')}</p>
      <div id="profile-counters">${draft.counters.map((counter,index) => `<article class="profile-counter" data-counter-id="${e(counter.id)}"><h3>${t('Zähler')} ${index+1}</h3>
        ${languageInputs(counter.translations,[['label','Bezeichnung',true],['warning_label','Warnhinweis',false],['critical_label','Kritischer Hinweis',false]],`counter-${index}`)}
        <div class="form-grid"><div><label for="counter-${index}-warning_at">${t('Warnschwelle (optional)')}</label><input id="counter-${index}-warning_at" name="warning_at" type="number" min="0" step="1" value="${counter.warning_at ?? ''}"></div><div><label for="counter-${index}-critical_at">${t('Kritische Schwelle (optional)')}</label><input id="counter-${index}-critical_at" name="critical_at" type="number" min="0" step="1" value="${counter.critical_at ?? ''}"></div></div>
        <label class="checkbox"><input name="enabled" type="checkbox" ${counter.enabled ? 'checked' : ''}>${t('Zähler anzeigen und bedienen')}</label>
        <fieldset data-profile-structure><label class="checkbox"><input name="reset_each_period" type="checkbox" ${counter.reset_each_period ? 'checked' : ''}>${t('Beim nächsten Abschnitt auf null setzen')}</label><button type="button" data-profile="remove-counter" data-id="${e(counter.id)}">${t('Zähler entfernen')}</button></fieldset></article>`).join('')}</div>
      <fieldset data-profile-structure><button type="button" data-profile="add-counter">${t('Zähler hinzufügen')}</button></fieldset>` : `<p>${t('Ohne Sportprofil wird ein Wettkampf ohne zusätzliche Abschnittssteuerung und Zähler erfasst.')}</p>`}
      <div class="stack profile-buttons"><button type="submit" class="primary" id="profile-apply" data-disabled="${!state.event}">${t('Für Veranstaltung übernehmen')}</button>
      ${draft ? `<button type="button" data-profile="save" data-action="profile-save">${selectedEntry ? t('Bibliotheksprofil speichern') : t('In Bibliothek speichern')}</button>` : ''}
      ${selectedEntry ? `<button type="button" data-profile="copy">${t('Als neues Profil bearbeiten')}</button><button type="button" data-profile="delete" data-action="profile-delete">${t('Aus Bibliothek löschen')}</button>` : ''}
      <button type="button" data-profile="reload">${t('Gespeicherten Stand laden')}</button></div></fieldset></form></details>`;
  $('#profile-source').value = source;
  $('#profile-form').querySelectorAll('[data-profile-structure]').forEach(f => f.disabled = structureLocked);
  const roleControls = () => {
    if (!draft) return;
    const enabled = $('#profile-form [name=roles_enabled]').checked;
    $('#profile-roles').hidden = !enabled;
    $('#profile-roles').querySelectorAll('input').forEach(input => input.required = enabled);
  };
  roleControls();
  $('#profile-form').oninput = () => { dirty = true; roleControls(); };
  $('#profile-source').onchange = event => {
    if (dirty && !confirm(t('Ungespeicherte Profiländerungen verwerfen?'))) { event.target.value = source; return; }
    source = event.target.value; load(app);
  };
  $('#profile-form').onsubmit = async event => {
    event.preventDefault(); read();
    if (used && !sameStructure(state.event.sport_profile,draft)) {
      message(t('Die Profilstruktur ist bereits verwendet. Nur Bezeichnungen und Anzeigeoptionen übernehmen.')); return;
    }
    if (await app.send('config/sport-profile',{data:{sport_profile:draft}},formRevision,formContext)) {
      source = 'event'; load(app); message(t('Sportprofil für diese Veranstaltung gespeichert. Die Bibliothek bleibt unverändert.'));
    }
  };
  $('#profile-form').onclick = async event => {
    const button = event.target.closest('[data-profile]'); if (!button || button.disabled) return;
    const action = button.dataset.profile;
    if (action === 'reload') { if (!dirty || confirm(t('Ungespeicherte Profiländerungen verwerfen?'))) load(app); return; }
    if (action === 'delete') {
      if (!confirm(t('Profil aus der Bibliothek löschen? Veranstaltungskopien bleiben erhalten.'))) return;
      if (await app.send('sport-profiles/delete',{id:selectedEntry.id},formLibraryRevision)) { source = 'new'; await fetchLibrary(); load(app); }
      return;
    }
    read();
    if (action === 'save') {
      if (!$('#profile-form').reportValidity()) return;
      const id = selectedEntry?.id || uuid();
      if (await app.send('sport-profiles/save',{id,profile:draft},formLibraryRevision)) {
        source = 'library:'+id; await fetchLibrary(); load(app); message(t('Bibliotheksprofil gespeichert. Veranstaltungskopien bleiben unverändert.'));
      }
      return;
    }
    if (action === 'copy') source = 'new';
    if (action === 'remove-counter') draft.counters = draft.counters.filter(c => c.id !== button.dataset.id);
    if (action === 'add-counter') draft.counters.push({id:uuid(),label:'Counter',scope:'participant',enabled:true,reset_each_period:true,warning_at:null,critical_at:null,warning_label:'',critical_label:'',translations:Object.fromEntries(languages.map(lang => [lang,{label:'',warning_label:'',critical_label:''}]))});
    dirty = true; editor(app); app.controls();
  };
}
function load(app) {
  const state = app.state;
  draft = source === 'none' ? null : source === 'event' ? state.live.sport_profile || fresh() : library?.profiles.find(p => 'library:'+p.id === source)?.profile || library?.event_profiles.find(p => 'event:'+p.id === source)?.profile || fresh();
  draft = draft ? structuredClone(draft) : null;
  formRevision = state.revision; formLibraryRevision = library.revision; formContext = {event_id:state.active_event_id,selection_token:state.selection_token};
  dirty = false; editor(app); app.controls();
}
async function fetchLibrary() {
  const response = await fetch('/api/v1/sport-profiles');
  if (!response.ok) { message(errorText((await response.json()).detail)); return; }
  library = await response.json();
}
export function renderProfiles(app, state) {
  if (!isAdmin()) {
    $('#profile-management').innerHTML = `<details><summary>${t('Sportprofil dieser Veranstaltung')}</summary><p>${e(profileText(state.live.sport_profile,'name') || t('Ohne Sportprofil'))}</p><p>${t('Sportprofile verwaltet der Administrator.')}</p></details>`;
    return;
  }
  const changedEvent = selection !== state.selection_token;
  if (changedEvent) {
    if (dirty) message(t('Veranstaltung wurde gewechselt. Ungespeicherte Formulare wurden geschlossen.'));
    selection = state.selection_token; source = state.event ? 'event' : 'new'; dirty = false;
  }
  const signature = JSON.stringify(state.catalog.items.map(item => [item.id,item.event?.sport_profile]));
  if ((!library || library.revision !== state.profile_library_revision || signature !== eventProfileSignature) && !loading) {
    loading = true;
    fetchLibrary().then(() => {
      if (library) {
        eventProfileSignature = signature;
        if (!dirty || !$('#profile-form')) load(app);
      }
    }).catch(() => message(t('Profilbibliothek konnte nicht geladen werden.'))).finally(() => { loading = false; });
  } else if (library && !dirty) load(app);
  // The form is not rebuilt during concurrent edits; its saved revision detects conflicts.
}
