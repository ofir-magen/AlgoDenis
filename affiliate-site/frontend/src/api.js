const API = import.meta.env.VITE_API_URL;

export async function login(username, password) {
  const body = new URLSearchParams();
  body.append('username', username);
  body.append('password', password);
  const res = await fetch(`${API}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Login failed');
  localStorage.setItem('token', data.access_token);
  return data;
}

export async function getMe() {
  const token = localStorage.getItem('token');
  if (!token) throw new Error('No token');
  const res = await fetch(`${API}/me`, { headers: { 'Authorization': `Bearer ${token}` } });
  if (!res.ok) throw new Error('Unauthorized');
  return res.json();
}

export async function getDashboardData() {
  const token = localStorage.getItem('token');
  const res = await fetch(`${API}/dashboard/data`, { headers: { 'Authorization': `Bearer ${token}` } });
  if (!res.ok) throw new Error('Unauthorized');
  return res.json();
}

export function logout() { localStorage.removeItem('token'); }
