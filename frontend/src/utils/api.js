/**
 * API utility functions for REST endpoints.
 */
const API_BASE = `http://${window.location.hostname}:8000/api`;

export async function fetchHistory(page = 1, perPage = 20, search = '') {
  const params = new URLSearchParams({ page, per_page: perPage });
  if (search) params.set('search', search);

  const res = await fetch(`${API_BASE}/history?${params}`);
  if (!res.ok) throw new Error('Failed to fetch history');
  return res.json();
}

export async function fetchStats() {
  const res = await fetch(`${API_BASE}/stats`);
  if (!res.ok) throw new Error('Failed to fetch stats');
  return res.json();
}

export async function fetchBlacklist() {
  const res = await fetch(`${API_BASE}/blacklist`);
  if (!res.ok) throw new Error('Failed to fetch blacklist');
  return res.json();
}

export async function addToBlacklist(plateText, description = '') {
  const res = await fetch(`${API_BASE}/blacklist`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ plate_text: plateText, description }),
  });
  if (!res.ok) throw new Error('Failed to add to blacklist');
  return res.json();
}

export async function removeFromBlacklist(plateText) {
  const res = await fetch(`${API_BASE}/blacklist/${plateText}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to remove from blacklist');
  return res.json();
}

export function getExportUrl() {
  return `${API_BASE}/history/export`;
}

export function getPlateImageUrl(imagePath) {
  if (!imagePath) return null;
  // Handle both "/plates/xxx.jpg" and "xxx.jpg" formats
  const path = imagePath.startsWith('/') ? imagePath : `/plates/${imagePath}`;
  return `http://${window.location.hostname}:8000${path}`;
}
