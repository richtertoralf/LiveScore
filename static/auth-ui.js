import {t, errorText} from './i18n.js';
import {auth, csrfHeaders} from './auth-client.js';
const message = text => { document.querySelector('#message').textContent = text; };
const login = document.querySelector('#login-form');
if (login) login.onsubmit = async event => {
  event.preventDefault(); const button = login.querySelector('button'); button.disabled = true; message('');
  try {
    const response = await fetch('/login',{method:'POST',headers:csrfHeaders(),body:JSON.stringify(Object.fromEntries(new FormData(login)))});
    const data = await response.json();
    if (response.ok) location.assign(data.redirect); else message(errorText(data.detail));
  } catch { message(t('Verbindung unterbrochen. Aktion möglicherweise gespeichert; aktuellen Stand prüfen, bevor erneut gebucht wird.')); }
  finally { button.disabled = false; login.password.value = ''; }
};
const users = document.querySelector('#users-list');
if (users && auth.authenticated && auth.role === 'admin') {
  const form = document.querySelector('#password-form');
  const response = await fetch('/api/auth/users');
  const data = await response.json();
  if (!response.ok) message(errorText(data.detail));
  else for (const user of data.users) {
    const article = document.createElement('article'); article.className = 'panel';
    const name = document.createElement('h2'); name.textContent = user.username;
    const role = document.createElement('p'); role.textContent = t(user.role);
    article.append(name,role);
    if (user.default_password) { const warn = document.createElement('p'); warn.className = 'security-warning'; warn.textContent = t('Standardpasswort aktiv'); article.append(warn); }
    const button = document.createElement('button'); button.textContent = t('Passwort ändern'); button.dataset.user = user.username;
    button.disabled = auth.must_change_password && user.username !== 'admin';
    button.onclick = () => { form.reset(); form.hidden = false; form.username.value = user.username; document.querySelector('#password-user').textContent = user.username; form.password.focus(); };
    article.append(button); users.append(article);
  }
  if (auth.must_change_password) users.querySelector('[data-user="admin"]')?.click();
  form.onsubmit = async event => {
    event.preventDefault(); const button = form.querySelector('button'); button.disabled = true; message('');
    try {
      const response = await fetch('/api/auth/password',{method:'POST',headers:csrfHeaders(),body:JSON.stringify(Object.fromEntries(new FormData(form)))});
      const data = await response.json();
      if (response.ok) {
        form.reset();
        if (data.reauthenticate) location.replace('/login');
        else location.reload();
      } else if (response.status === 401) location.replace('/login');
      else message(errorText(data.detail));
    } catch { message(t('Verbindung unterbrochen. Aktion möglicherweise gespeichert; aktuellen Stand prüfen, bevor erneut gebucht wird.')); }
    finally { button.disabled = false; form.password.value = ''; form.repeat.value = ''; }
  };
}
