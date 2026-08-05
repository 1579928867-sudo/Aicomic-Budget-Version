import { create } from 'zustand';

interface AppState {
  activePage: string;         // 'home' | 'chat' | 'library' | 'videos' | 'cookie' | 'tasks' | 'settings'
  setActivePage: (page: string) => void;
  selectedNovelId: number | null;
  setSelectedNovelId: (id: number | null) => void;
  selectedChapterId: number | null;
  setSelectedChapterId: (id: number | null) => void;
}

export const useAppStore = create<AppState>((set) => ({
  activePage: 'home',
  setActivePage: (page) => set({ activePage: page }),
  selectedNovelId: null,
  setSelectedNovelId: (id) => set({ selectedNovelId: id, selectedChapterId: null }),
  selectedChapterId: null,
  setSelectedChapterId: (id) => set({ selectedChapterId: id }),
}));
