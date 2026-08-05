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
  if (res.headers.get('content-type')?.includes('application/json')) {
    return res.json();
  }
  return {} as T;
}

export const chat = {
  send: (body: { message: string; chapter_id?: number; novel_id?: number }) =>
    request<{ reply: string; intent: string; task_id?: string }>('/chat/send', {
      method: 'POST', body: JSON.stringify(body),
    }),
  history: (chapter_id?: number) =>
    request<ChatMessage[]>(`/chat/history${chapter_id ? `?chapter_id=${chapter_id}` : ''}`),
};

export const pipeline = {
  run: (chapter_id: number, with_images = false, with_video = false) =>
    request<{ task_id: string; events_url: string }>('/pipeline/run', {
      method: 'POST', body: JSON.stringify({ chapter_id, with_images, with_video }),
    }),
  cancel: (task_id: string) =>
    request<{ status: string }>('/pipeline/cancel', {
      method: 'POST', body: JSON.stringify({ task_id }),
    }),
};

export const library = {
  novels: () => request<Novel[]>('/novels'),
  chapters: (novel_id: number) => request<Chapter[]>(`/novels/${novel_id}/chapters`),
  characters: (chapter_id: number) => request<Character[]>(`/chapters/${chapter_id}/characters`),
  scenes: (chapter_id: number) => request<Scene[]>(`/chapters/${chapter_id}/scenes`),
  script: (chapter_id: number) => request<Script>(`/chapters/${chapter_id}/script`),
  shots: (chapter_id: number) => request<Shot[]>(`/chapters/${chapter_id}/shots`),
};

export const agents = {
  run: (body: { agent: string; target_type: string; target_id: number; extra?: string; chapter_id?: number }) =>
    request<{ task_id: string; events_url: string }>('/agents/run', {
      method: 'POST', body: JSON.stringify(body),
    }),
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
  llm: () => request<any>('/settings/llm'),
};
