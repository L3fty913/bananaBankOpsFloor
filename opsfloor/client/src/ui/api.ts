// Default to same-origin so VPS deployments work from any client device.
// Override with VITE_OPSFLOOR_API only for local dev/proxy scenarios.
export const API_BASE = (import.meta as any).env?.VITE_OPSFLOOR_API || '';

export async function jget<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`);
  if (!r.ok) throw new Error(`${r.status}`);
  return (await r.json()) as T;
}

export async function jpost<T>(path: string, body: any): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status}`);
  return (await r.json()) as T;
}
