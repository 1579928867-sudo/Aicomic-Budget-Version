import type { Novel, Chapter, Character, Scene, Script, Shot, Task, ChatMessage, VideoClip, FinalVideo } from './types';

const BASE = '/api';

async function request<T>(url: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json', ...opts?.headers },
    ...opts,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  if (res.headers.get('content-type')?.includes('application/json')) return res.json();
  return {} as T;
}

export const chat = {
  send: (body: { message: string; chapter_id?: number; novel_id?: number }) =>
    request<{ reply: string; intent: string; task_id?: string }>('/chat/send', { method: 'POST', body: JSON.stringify(body) }),
  history: (chapter_id?: number) =>
    request<ChatMessage[]>(`/chat/history${chapter_id ? `?chapter_id=${chapter_id}` : ''}`),
  status: () =>
    request<{
      llm_ready: boolean; llm_detail: string;
      cookie_ready: boolean; cookie_detail: string;
      all_ready: boolean; novel_count: number; chapter_count: number;
      next_step: string;
    }>('/chat/status'),
};

export const pipeline = {
  run: (chapter_id: number, with_images = true, with_video = true, mode: 'interactive' | 'auto' = 'interactive') =>
    request<{ task_id: string; events_url: string; mode: string }>('/pipeline/run', { method: 'POST', body: JSON.stringify({ chapter_id, with_images, with_video, mode }) }),
  continue: (task_id: string) =>
    request<{ status: string }>('/pipeline/continue', { method: 'POST', body: JSON.stringify({ task_id }) }),
  cancel: (task_id: string) =>
    request<{ status: string }>('/pipeline/cancel', { method: 'POST', body: JSON.stringify({ task_id }) }),
};

export const library = {
  novels: () => request<Novel[]>('/novels'),
  chapters: (novel_id: number) => request<Chapter[]>(`/novels/${novel_id}/chapters`),
  characters: (chapter_id: number) => request<Character[]>(`/chapters/${chapter_id}/characters`),
  scenes: (chapter_id: number) => request<Scene[]>(`/chapters/${chapter_id}/scenes`),
  script: (chapter_id: number) => request<Script>(`/chapters/${chapter_id}/script`),
  shots: (chapter_id: number) => request<Shot[]>(`/chapters/${chapter_id}/shots`),
  deleteNovel: (novel_id: number) =>
    request<{ status: string; deleted_novel: { id: number; title: string }; deleted_chapters: number; deleted_files: number }>(`/novels/${novel_id}`, { method: 'DELETE' }),
  deleteChapter: (chapter_id: number) =>
    request<{ status: string; deleted_chapter: { id: number; chapter_num: number }; deleted_files: number }>(`/chapters/${chapter_id}`, { method: 'DELETE' }),
};

export const agents = {
  run: (body: { agent: string; target_type: string; target_id: number; extra?: string; chapter_id?: number; shot_num?: number }) =>
    request<{ task_id: string; events_url: string }>('/agents/run', { method: 'POST', body: JSON.stringify(body) }),
};

export const videos = {
  list: (chapter_id: number) =>
    request<{ clips: VideoClip[]; finals: FinalVideo[] }>(`/chapters/${chapter_id}/videos`),
};

export const tasks = {
  list: () => request<Task[]>('/tasks'),
  get: (id: string) => request<Task>(`/tasks/${id}`),
  cancel: (id: string) => request<{ status: string }>(`/tasks/${id}/cancel`, { method: 'POST' }),
  retry: (id: string) => request<{ new_task_id: string }>(`/tasks/${id}/retry`, { method: 'POST' }),
};

export const settings = {
  cookieStatus: () => request<{ valid: boolean }>('/settings/cookie-status'),
  cookieAuto: () => request<{ status: string; message: string }>('/settings/cookie-auto', { method: 'POST' }),
  cookieAutoConfirm: () => request<{ status: string; cookie_count: number; message: string }>('/settings/cookie-auto-confirm', { method: 'POST' }),
  cookieAutoCancel: () => request<{ status: string }>('/settings/cookie-auto-cancel', { method: 'POST' }),
  cookieAutoStatus: () => request<{ running: boolean; error: string | null }>('/settings/cookie-auto-status'),
  llm: () => request<{ backend: string; model: string; api_key_masked: string; has_key: boolean; base_url: string }>('/settings/llm'),
  saveLlm: (body: { backend: string; api_key: string; model: string; base_url: string }) =>
    request<{ status: string; api_key_masked: string }>('/settings/llm', { method: 'POST', body: JSON.stringify(body) }),
  videoModel: () => request<{ model: string }>('/settings/video-model'),
  saveVideoModel: (model: 'mini' | 'fast') =>
    request<{ status: string; model: string }>('/settings/video-model', { method: 'POST', body: JSON.stringify({ model }) }),
};

// ── SSE 事件流 ──

export type SSEEvent = { step?: string; status: string; pct?: number; message?: string; error?: string; data?: any };

export function subscribeEvents(
  taskId: string,
  onProgress: (data: SSEEvent) => void,
  onComplete: (data: SSEEvent) => void,
  onError: (data: SSEEvent) => void,
): EventSource {
  const es = new EventSource(`${BASE}/events/${taskId}`);
  es.addEventListener('progress', (e: MessageEvent) => {
    try { onProgress(JSON.parse(e.data)); } catch {}
  });
  es.addEventListener('complete', (e: MessageEvent) => {
    try { onComplete(JSON.parse(e.data)); } catch {}
    es.close();
  });
  es.addEventListener('error', (e: MessageEvent) => {
    if (e.data) { try { onError(JSON.parse(e.data)); } catch {} }
    else { onError({ status: 'connection_error', message: 'SSE 连接中断' }); }
    es.close();
  });
  return es;
}
