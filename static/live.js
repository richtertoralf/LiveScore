import { t, periodAction } from './i18n.js';
import { $, escape as e, Connection, message } from './common.js';
let editPairing = false, finishRevision = null, periodRevision = null, selectionToken = null;
const button = (action, label, cls = '', disabled = false) => `<button data-action="${action}" class="${cls}" data-disabled="${disabled}">${label}</button>`;
const app = new Connection(render);
const name = (state, id, fallback = t('Noch offen')) => state.participants.find(p => p.id === id)?.name || t(fallback);
function matchInfo(state, match) {
  return `${e(match.date)} · ${e(match.time.slice(0,5))} · ${e(state.play_areas.find(a => a.id === match.play_area_id)?.label)}${match.round ? ' · ' + e(match.round) : ''}`;
}
function options(state, selected) {
  return `<option value="">${t("Bitte wählen")}</option>` + state.participants.map(p => `<option value="${e(p.id)}" ${p.id === selected ? 'selected' : ''}>${e(p.name)}</option>`).join('');
}
function render(state) {
  if (selectionToken !== state.selection_token) {
    editPairing = false; selectionToken = state.selection_token;
    $('#finish-dialog').close(); $('#period-dialog').close();
  }
  $('#event-name').textContent = state.event?.name || t('Veranstaltung noch nicht eingerichtet');
  const match = state.matches.find(m => m.id === state.active_match_id);
  $('#config-link').hidden = match && ['live','paused','ready'].includes(match.status);
  if ($('#finish-dialog').open && state.revision !== finishRevision) {
    $('#finish-dialog').close(); message(t('Spielstand wurde geändert. Bitte Ergebnis erneut prüfen.'));
  }
  if ($('#period-dialog').open && state.revision !== periodRevision) {
    $('#period-dialog').close(); message(t('Spielzustand wurde geändert. Bitte Abschnittswechsel erneut prüfen.'));
  }
  let html = '';
  if (!state.active_event_id) {
    $('#live').innerHTML = `<div class="panel"><h1>${t("Veranstaltung auswählen")}</h1><p>${t("Unter")} <a href="/events">${t("Veranstaltungen")}</a> ${t("eine Veranstaltung anlegen, importieren oder auswählen.")}</p></div>`;
    return;
  }
  if (match) {
    const profile = state.event?.sport_profile;
    const status = {scheduled:t('NÄCHSTES SPIEL'),ready:t('BEREIT'),live:t('LIVE'),paused:t('PAUSE'),finished:t('BEENDET')}[match.status];
    html += `<div class="panel"><span class="status ${match.status}">${status}</span><p class="muted">${matchInfo(state,match)}</p>`;
    if (profile) html += `<p id="period-label">${match.period}. ${e(t(profile.period_label))} · ${profile.periods} ${t("Abschnitte")}</p>`;
    if (match.status === 'scheduled') {
      html += `<div class="pairing-names">${e(name(state,match.participant_1,match.placeholder_1))}<span>${t("gegen")}</span>${e(name(state,match.participant_2,match.placeholder_2))}</div>`;
      if (editPairing || !match.participant_1 || !match.participant_2) {
        html += `<label for="pair-1">${t("Teilnehmer 1 / zunächst links")}</label><select id="pair-1">${options(state,match.participant_1)}</select><label for="pair-2">${t("Teilnehmer 2 / zunächst rechts")}</label><select id="pair-2">${options(state,match.participant_2)}</select>`;
      }
      html += `<div class="stack">${button('prepare',t('Paarung bestätigen'),'primary')}${button('edit-pair',t('Paarung ändern'))}</div>`;
    } else {
      html += `<p class="muted">${e(t(state.event?.score_label || 'Score'))}</p><div class="pair">`;
      for (const [side, key] of [['L','left'],['R','right']]) {
        const person = state.live[key];
        html += `<div><div class="side">${side === 'L' ? t('LINKS') : t('RECHTS')}</div><div class="name" id="name-${side}">${e(person.name)}</div>`;
        if (match.status !== 'ready') html += `<div class="score" id="score-${side}" aria-label="${t('Score')} ${side}">${person.score}</div>`;
        if (['live','paused'].includes(match.status)) html += button(`score-${side}-1`,'+1','add') + button(`score-${side}--1`,'−1','subtract',person.score === 0);
        for (const counter of profile?.counters || []) {
          const value = person.counters[counter.id], level = person.counter_states[counter.id];
          const notice = level === 'critical' ? (counter.critical_label || t('Kritische Schwelle erreicht')) : level === 'warning' ? (counter.warning_label || t('Warnschwelle erreicht')) : '';
          html += `<div class="counter ${level}" id="counter-${side}-${e(counter.id)}"><strong><span class="counter-value">${value}</span> ${e(t(counter.label))}</strong>`;
          if (notice) html += `<p class="counter-notice">${e(t(notice))}</p>`;
          if (['live','paused'].includes(match.status)) html += `<div class="counter-actions"><button data-action="counter" data-side="${side}" data-counter="${e(counter.id)}" data-delta="1" aria-label="${e(t(counter.label))} ${side} +1">+</button><button data-action="counter" data-side="${side}" data-counter="${e(counter.id)}" data-delta="-1" data-disabled="${value === 0}" aria-label="${e(t(counter.label))} ${side} −1">−</button></div>`;
          html += '</div>';
        }
        html += '</div>';
      }
      html += '</div>';
      if (match.status === 'ready') html += `<div class="stack">${button('switch-sides',t('Seiten tauschen'))}${button('start',t('Spiel starten'),'primary')}${button('unprepare',t('Paarung ändern / Vorbereitung zurücknehmen'))}</div>`;
      if (['live','paused'].includes(match.status)) {
        html += button('undo',t('UNDO · letzter Score'),'undo',!state.can_undo);
        html += `<div class="actions">${button(match.status === 'live' ? 'pause' : 'resume',match.status === 'live' ? t('Pause') : t('Fortsetzen'))}${button('switch-sides',t('Seitenwechsel'))}</div>${button('finish-dialog',t('Spiel Ende'),'danger')}`;
        if (profile && match.period < profile.periods) html += `<div class="period-action">${button('period-dialog',e(periodAction(match.period+1,profile.period_label)))}</div>`;
      }
      if (match.status === 'finished') html += `<p>${t("Ergebnis bestätigt. Nächstes Spiel auswählen.")}</p>`;
    }
    if (state.live.officials.length) html += `<p id="officials" class="muted officials">${t("Officials:")} ${state.live.officials.map(referee => e(referee.name) + (referee.country_code ? ' (' + e(referee.country_code) + ')' : '')).join(' · ')}</p>`;
    html += '</div>';
  }
  if (!match || ['scheduled','finished'].includes(match.status)) {
    const next = state.matches.filter(m => m.status === 'scheduled' && m.id !== match?.id).sort((a,b) => (a.date+a.time).localeCompare(b.date+b.time));
    html += `<h1>${t("Nächstes Spiel auswählen")}</h1>`;
    html += next.map(m => `<button class="match-item" data-action="select" data-id="${e(m.id)}"><small>${matchInfo(state,m)}</small>${e(name(state,m.participant_1,m.placeholder_1))} – ${e(name(state,m.participant_2,m.placeholder_2))}</button>`).join('');
    if (!next.length) html += `<p class="muted">${t("Keine weiteren geplanten Spiele. Veranstaltungsdaten und Spielplan lassen sich in der")} <a href="/config">${t("Konfiguration")}</a> ${t("erfassen.")}</p>`;
  }
  $('#live').innerHTML = html;
}
$('#live').addEventListener('click', async event => {
  const target = event.target.closest('button[data-action]');
  if (!target || target.disabled) return;
  const action = target.dataset.action, state = app.state;
  const match = state.matches.find(m => m.id === state.active_match_id);
  if (action === 'edit-pair') { editPairing = true; render(state); app.controls(); return; }
  if (action === 'finish-dialog') {
    finishRevision = state.revision;
    $('#final-result').textContent = `${state.live.left.name} ${state.live.left.score} : ${state.live.right.score} ${state.live.right.name}`;
    $('#finish-dialog').showModal(); return;
  }
  if (action === 'period-dialog') {
    periodRevision = state.revision;
    const label = periodAction(match.period+1,state.event.sport_profile.period_label);
    $('#period-question').textContent = label + '?';
    $('#period-confirm').textContent = label;
    $('#period-dialog').showModal(); return;
  }
  let payload = {match_id: action === 'select' ? target.dataset.id : match.id}, endpoint = action;
  if (action === 'prepare') {
    const p1 = $('#pair-1')?.value ?? match.participant_1, p2 = $('#pair-2')?.value ?? match.participant_2;
    if (!p1 || !p2 || p1 === p2) { message(t('Bitte zwei verschiedene Teilnehmer wählen.')); return; }
    Object.assign(payload, {participant_1:p1, participant_2:p2, side_l:p1, side_r:p2}); editPairing = false;
  }
  if (action.startsWith('score-')) {
    const [, side, delta] = action.match(/^score-([LR])-(-?1)$/);
    Object.assign(payload, {side,delta:Number(delta),participant_id:state.live[side === 'L' ? 'left' : 'right'].id,control_revision:match.control_revision}); endpoint = 'score';
  }
  if (action === 'counter') {
    Object.assign(payload, {participant_id:state.live[target.dataset.side === 'L' ? 'left' : 'right'].id,
      counter_id:target.dataset.counter, delta:Number(target.dataset.delta),
      control_revision:match.control_revision, period:match.period});
  }
  if (action === 'select') editPairing = false;
  await app.send(`live/${endpoint}`,payload);
});
$('#finish-cancel').onclick = () => $('#finish-dialog').close();
$('#finish-confirm').onclick = async () => {
  const revision = finishRevision;
  $('#finish-dialog').close();
  await app.send('live/finish',{match_id:app.state.active_match_id},revision);
};
$('#period-cancel').onclick = () => $('#period-dialog').close();
$('#period-confirm').onclick = async () => {
  const revision = periodRevision;
  $('#period-dialog').close();
  await app.send('live/period',{match_id:app.state.active_match_id, period:app.state.live.period+1},revision);
};
