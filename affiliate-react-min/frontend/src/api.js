// Minimal API client — computes backend base by swapping port 5180 -> 8020
function apiBase(){
  const url = new URL(window.location.href);
  if (url.port === '5180') url.port = '8020';
  return url.origin.replace(':5180', ':8020');
}

export async function login(username, password) {
  const body = new URLSearchParams();
  body.append('username', username);
  body.append('password', password);
  const res = await fetch(`${apiBase()}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Login failed');
  localStorage.setItem('token', data.access_token);
  return data;
}

export async function authedGet(path) {
  const token = localStorage.getItem('token');
  if(!token) throw new Error('no token');
  const res = await fetch(`${apiBase()}${path}`, { headers: { 'Authorization': `Bearer ${token}` } });
  if (!res.ok) throw new Error('Unauthorized');
  return res.json();
}

export function logout(){ localStorage.removeItem('token'); }
