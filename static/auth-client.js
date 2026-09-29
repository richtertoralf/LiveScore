import {t, errorText} from './i18n.js';
export const auth = await fetch('/api/auth/session').then(r => r.json());
export const csrfHeaders = () => ({'Content-Type':'application/json','X-CSRF-Token':auth.csrf_token || ''});
export const canOperate = () => auth.role === 'admin' || auth.role === 'operator';
export const isAdmin = () => auth.role === 'admin';
if (!auth.authenticated && location.pathname !== '/login') location.replace('/login');
if (auth.must_change_password && !['/users','/login'].includes(location.pathname)) location.replace('/users');
if (auth.authenticated && location.pathname === '/login') location.replace(auth.must_change_password ? '/users' : '/');
if (auth.authenticated && auth.enabled) {
  const header = document.querySelector('header');
  const account = document.createElement('span'); account.className = 'account'; account.textContent = `${auth.username} · ${t(auth.role)}`; header.append(account);
  if (isAdmin()) {
    const link = document.createElement('a'); link.href = '/users'; link.textContent = t('Benutzer'); header.append(link);
    if (auth.defaults.length) {
      const warning = document.createElement('p'); warning.id = 'default-warning'; warning.className = 'security-warning';
      warning.textContent = t(auth.must_change_password ? 'Das Standardpasswort ist noch aktiv. Vor Internetfreigabe ändern.' : 'Standardpasswörter sind aktiv. Diese LiveScore-Instanz nicht im Internet freigeben.');
      document.querySelector('main').prepend(warning);
    }
  }
  const logout = document.createElement('button'); logout.id = 'logout'; logout.textContent = t('Abmelden');
  logout.onclick = async () => {
    const response = await fetch('/logout',{method:'POST',headers:csrfHeaders()});
    if (response.ok || response.status === 401) location.replace('/login');
    else document.querySelector('#message').textContent = errorText((await response.json()).detail);
  };
  header.append(logout);
}
