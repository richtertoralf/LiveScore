// The same public version source is used on every page, including login.
fetch('/api/version').then(response => {
  if (!response.ok) throw new Error('Version unavailable');
  return response.json();
}).then(({version}) => {
  const footer = document.createElement('footer');
  footer.className = 'app-version';
  footer.textContent = `LiveScore v${version}`;
  document.body.append(footer);
}).catch(() => { /* Offline mode must not interrupt live controls. */ });
