import { request } from './api';
import type { Gap, GapsAnswer, HideReason, Wish } from './shopping';

const gapPath = (id: string) => `/api/gaps/${encodeURIComponent(id)}/hidden`;
const wishPath = (id: string) => `/api/wishlist/${encodeURIComponent(id)}`;

export const shoppingApi = {
  gaps: (signal?: AbortSignal) => request<GapsAnswer>('/api/gaps', { signal }),
  hidden: (signal?: AbortSignal) => request<{ gaps: Gap[] }>('/api/gaps/hidden', { signal }).then((r) => r.gaps),
  wishes: (signal?: AbortSignal) => request<{ wishes: Wish[] }>('/api/wishlist', { signal }).then((r) => r.wishes),
  hide: (id: string, reason: HideReason | null) => request<void>(gapPath(id), { method: 'PUT', body: { reason } }),
  unhide: (id: string) => request<void>(gapPath(id), { method: 'DELETE' }),
  add: (body: { gap_id: string } | { name: string; details: string; note: string }) =>
    request<Wish>('/api/wishlist', { method: 'POST', body }),
  note: (id: string, note: string) => request<Wish>(wishPath(id), { method: 'PATCH', body: { note } }),
  bought: (id: string) => request<void>(`${wishPath(id)}/bought`, { method: 'POST' }),
  remove: (id: string) => request<void>(wishPath(id), { method: 'DELETE' }),
};
