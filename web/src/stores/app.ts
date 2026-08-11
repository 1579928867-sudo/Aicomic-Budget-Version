import { create } from 'zustand';

interface AppState {
  selectedNovelId: number | null;
  setSelectedNovelId: (id: number | null) => void;
  selectedChapterId: number | null;
  setSelectedChapterId: (id: number | null) => void;
  videoModel: 'mini' | 'fast';
  setVideoModel: (m: 'mini' | 'fast') => void;
}

export const useAppStore = create<AppState>((set) => ({
  selectedNovelId: null,
  setSelectedNovelId: (id) => set({ selectedNovelId: id, selectedChapterId: null }),
  selectedChapterId: null,
  setSelectedChapterId: (id) => set({ selectedChapterId: id }),
  videoModel: 'mini',
  setVideoModel: (m) => set({ videoModel: m }),
}));
