// frontend/src/api.js
// עדכון: קודם כל נשתמש במשתנה סביבה VITE_API_URL אם מוגדר, אחרת fallback להחלפת פורט 5180→8020
function baseUrl() {
  const fromEnv = import.meta?.env?.VITE_API_URL;
  if (fromEnv) return fromEnv.replace(/\/+$/, '');
  const url = new URL(window.location.href);
  if (url.port === '5180') url.port = '8020';
  return url.origin.replace(':5180', ':8020');
}

export async function login(username, password) {
  const body = new URLSearchParams();
  body.append('username', username);
  body.append('password', password);
  const res = await fetch(`${baseUrl()}/login`, {
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
  if (!token) throw new Error('no token');
  const res = await fetch(`${baseUrl()}${path}`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Unauthorized');
  }
  return res.json();
}

export function logout() {
  localStorage.removeItem('token');
}

// ---- פונקציות חדשות לנתוני הגרפים ----
export function getMonthlySummary() {
  return authedGet('/dashboard/monthly-summary');
}

export function getUsersByMonth(month) {
  return authedGet(`/dashboard/users-by-month?month=${encodeURIComponent(month)}`);
}

export function getCouponStats() {
  return authedGet('/dashboard/coupon-stats');
}

export function getStatusStats() {
  return authedGet('/dashboard/status-stats');
}
