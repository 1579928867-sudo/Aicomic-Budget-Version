import { useState, useEffect } from 'react';
import { BookOpen, ChevronRight, User, Image, FileText, Film, Loader2, RefreshCw, Eye, X } from 'lucide-react';
import { library } from '../api';
import { useAppStore } from '../stores/app';
import type { Novel, Chapter, Character, Scene, Shot } from '../types';

export function LibraryPage() {
  const { selectedNovelId, setSelectedNovelId, selectedChapterId, setSelectedChapterId } = useAppStore();
  const [novels, setNovels] = useState<Novel[]>([]);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [tab, setTab] = useState<'characters' | 'scenes' | 'shots'>('characters');
  const [characters, setCharacters] = useState<Character[]>([]);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [shots, setShots] = useState<Shot[]>([]);
  const [loading, setLoading] = useState(false);
  const [previewImg, setPreviewImg] = useState<string | null>(null);

  useEffect(() => { library.novels().then(setNovels).catch(console.error); }, []);
  useEffect(() => {
    if (selectedNovelId) {
      library.chapters(selectedNovelId).then(setChapters).catch(console.error);
    }
  }, [selectedNovelId]);
  useEffect(() => {
    if (selectedChapterId) {
      setLoading(true);
      Promise.all([
        library.characters(selectedChapterId),
        library.scenes(selectedChapterId),
        library.shots(selectedChapterId),
      ]).then(([c, s, sh]) => {
        setCharacters(c); setScenes(s); setShots(sh);
      }).catch(console.error).finally(() => setLoading(false));
    }
  }, [selectedChapterId]);

  const NovelList = () => (
    <div className="space-y-1">
      <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider px-1 mb-2">小说</h3>
      {novels.map(n => (
        <button
          key={n.id}
          onClick={() => setSelectedNovelId(n.id === selectedNovelId ? null : n.id)}
          className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-all ${
            selectedNovelId === n.id ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20' : 'text-zinc-400 hover:bg-zinc-800/50 border border-transparent'
          }`}
        >
          <BookOpen size={15} />
          <span className="truncate flex-1 text-left">{n.title}</span>
          <ChevronRight size={14} className={`transition-transform ${selectedNovelId === n.id ? 'rotate-90' : ''}`} />
        </button>
      ))}
    </div>
  );

  const ChapterList = () => {
    if (!selectedNovelId) return null;
    return (
      <div className="space-y-1">
        <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider px-1 mt-3 mb-2">章节</h3>
        {chapters.map(c => (
          <button
            key={c.id}
            onClick={() => setSelectedChapterId(c.id === selectedChapterId ? null : c.id)}
            className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-all ${
              selectedChapterId === c.id ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'text-zinc-400 hover:bg-zinc-800/50 border border-transparent'
            }`}
          >
            <FileText size={15} />
            <span className="flex-1 text-left">第{c.chapter_num}章</span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded ${c.status === 'done' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-zinc-700/30 text-zinc-500'}`}>{c.status}</span>
          </button>
        ))}
      </div>
    );
  };

  const Tabs = () => (
    <div className="flex gap-1 bg-zinc-800/50 rounded-lg p-1">
      {(['characters', 'scenes', 'shots'] as const).map(t => (
        <button
          key={t}
          onClick={() => setTab(t)}
          className={`flex-1 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
            tab === t ? 'bg-zinc-700 text-white shadow-sm' : 'text-zinc-500 hover:text-zinc-300'
          }`}
        >
          {{ characters: `人物 (${characters.length})`, scenes: `场景 (${scenes.length})`, shots: `分镜 (${shots.length})` }[t]}
        </button>
      ))}
    </div>
  );

  const CharacterCards = () => (
    <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
      {characters.map(c => (
        <div key={c.id} className="glass-card p-3 group">
          <div className="flex items-start justify-between mb-2">
            <div>
              <div className="text-sm font-semibold text-white">{c.name}</div>
              <div className="text-[11px] text-zinc-500">{c.outfits.length} 套装扮</div>
            </div>
            <button className="p-1 rounded-md bg-zinc-700/50 text-zinc-500 hover:text-indigo-400 opacity-0 group-hover:opacity-100 transition-all">
              <RefreshCw size={13} />
            </button>
          </div>
          {c.outfits.filter(o => o.image_path).slice(0, 1).map(o => (
            <div
              key={o.id}
              className="relative aspect-[3/4] rounded-lg overflow-hidden bg-zinc-800 cursor-pointer"
              onClick={() => setPreviewImg(`http://localhost:8000/${o.image_path.replace(/\\/g, '/')}`)}
            >
              <img
                src={`http://localhost:8000/${o.image_path.replace(/\\/g, '/')}`}
                alt={o.tag}
                className="w-full h-full object-cover hover:scale-105 transition-transform duration-300"
              />
              <div className="absolute bottom-0 left-0 right-0 p-2 bg-gradient-to-t from-black/70 to-transparent">
                <span className="text-[11px] text-white font-medium">{o.tag}</span>
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  );

  const SceneCards = () => (
    <div className="grid grid-cols-2 gap-3">
      {scenes.map(s => (
        <div key={s.id} className="glass-card p-3 group">
          <div className="flex items-start justify-between mb-2">
            <div>
              <div className="text-sm font-semibold text-white">{s.name}</div>
              <div className="text-[11px] text-zinc-500">{s.lighting?.slice(0, 30)}...</div>
            </div>
            <button className="p-1 rounded-md bg-zinc-700/50 text-zinc-500 hover:text-indigo-400 opacity-0 group-hover:opacity-100 transition-all">
              <RefreshCw size={13} />
            </button>
          </div>
          {s.multi_view_image && (
            <div
              className="aspect-video rounded-lg overflow-hidden bg-zinc-800 cursor-pointer"
              onClick={() => setPreviewImg(`http://localhost:8000/${s.multi_view_image.replace(/\\/g, '/')}`)}
            >
              <img
                src={`http://localhost:8000/${s.multi_view_image.replace(/\\/g, '/')}`}
                alt={s.name}
                className="w-full h-full object-cover hover:scale-105 transition-transform duration-300"
              />
            </div>
          )}
        </div>
      ))}
    </div>
  );

  const ShotList = () => (
    <div className="space-y-2">
      {shots.map(s => (
        <div key={s.id} className="glass-card p-3 flex gap-4 items-start">
          <div className="w-10 h-10 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center shrink-0">
            <span className="text-sm font-bold text-indigo-400">#{s.shot_num}</span>
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm text-white font-medium line-clamp-1">{s.narration || s.dialogue || '(无旁白)'}</div>
            <div className="flex gap-3 mt-1 text-[11px] text-zinc-500">
              <span>🎥 {s.camera_movement}</span>
              <span>⏱ {s.duration_sec}s</span>
              <span className={`px-1.5 py-0.5 rounded text-[10px] ${s.status === 'done' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-zinc-700/30 text-zinc-500'}`}>{s.status}</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );

  return (
    <div className="flex h-full">
      {/* Left Panel */}
      <div className="w-56 border-r border-zinc-800 p-4 space-y-2 overflow-auto shrink-0 bg-zinc-950/50">
        <NovelList />
        <ChapterList />
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-auto">
        {!selectedNovelId && (
          <div className="h-full flex items-center justify-center text-zinc-600">
            <div className="text-center">
              <BookOpen size={48} className="mx-auto mb-3 opacity-30" />
              <p className="text-sm">选择一本小说开始浏览</p>
            </div>
          </div>
        )}
        {selectedNovelId && !selectedChapterId && (
          <div className="h-full flex items-center justify-center text-zinc-600">
            <div className="text-center">
              <FileText size={48} className="mx-auto mb-3 opacity-30" />
              <p className="text-sm">选择一个章节查看素材</p>
            </div>
          </div>
        )}
        {selectedChapterId && (
          <div className="p-5">
            <div className="flex items-center gap-4 mb-4">
              <h2 className="text-lg font-bold text-white">
                第{chapters.find(c => c.id === selectedChapterId)?.chapter_num}章 素材
              </h2>
              <Tabs />
            </div>
            {loading ? (
              <div className="flex items-center justify-center py-12"><Loader2 className="animate-spin text-indigo-400" size={24} /></div>
            ) : (
              <>
                {tab === 'characters' && <CharacterCards />}
                {tab === 'scenes' && <SceneCards />}
                {tab === 'shots' && <ShotList />}
              </>
            )}
          </div>
        )}
      </div>

      {/* Preview Modal */}
      {previewImg && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm" onClick={() => setPreviewImg(null)}>
          <button className="absolute top-4 right-4 p-2 rounded-full bg-zinc-800 text-zinc-400 hover:text-white" onClick={() => setPreviewImg(null)}>
            <X size={20} />
          </button>
          <img src={previewImg} alt="preview" className="max-w-[80vw] max-h-[85vh] rounded-xl shadow-2xl" onClick={e => e.stopPropagation()} />
        </div>
      )}
    </div>
  );
}
