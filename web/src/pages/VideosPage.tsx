import { useState, useEffect } from 'react';
import { Film, Play, Download, Loader2, RefreshCw } from 'lucide-react';
import { library, videos } from '../api';
import { useAppStore } from '../stores/app';
import type { Chapter, FinalVideo, VideoClip } from '../types';

export function VideosPage() {
  const { selectedNovelId, setSelectedNovelId, selectedChapterId, setSelectedChapterId } = useAppStore();
  const [novels, setNovels] = useState<any[]>([]);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [clips, setClips] = useState<VideoClip[]>([]);
  const [finals, setFinals] = useState<FinalVideo[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeVideo, setActiveVideo] = useState<string | null>(null);

  useEffect(() => { library.novels().then(setNovels).catch(console.error); }, []);
  useEffect(() => {
    if (selectedNovelId) library.chapters(selectedNovelId).then(setChapters).catch(console.error);
  }, [selectedNovelId]);
  useEffect(() => {
    if (selectedChapterId) {
      setLoading(true);
      videos.list(selectedChapterId).then(({ clips, finals }) => {
        setClips(clips); setFinals(finals);
      }).catch(console.error).finally(() => setLoading(false));
    }
  }, [selectedChapterId]);

  const activeChapter = chapters.find(c => c.id === selectedChapterId);

  return (
    <div className="flex h-full">
      {/* Side Panel */}
      <div className="w-56 border-r border-zinc-800 p-4 space-y-2 overflow-auto shrink-0 bg-zinc-950/50">
        <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider px-1 mb-2">选择章节</h3>
        {novels.map(n => (
          <div key={n.id}>
            <button
              onClick={() => setSelectedNovelId(n.id === selectedNovelId ? null : n.id)}
              className={`w-full text-left px-2 py-1.5 rounded text-xs font-medium ${selectedNovelId === n.id ? 'text-indigo-400' : 'text-zinc-500'}`}
            >{n.title}</button>
            {selectedNovelId === n.id && chapters.map(c => (
              <button
                key={c.id}
                onClick={() => setSelectedChapterId(c.id)}
                className={`w-full text-left pl-4 pr-2 py-1.5 rounded text-xs ${selectedChapterId === c.id ? 'bg-emerald-500/10 text-emerald-400' : 'text-zinc-400 hover:bg-zinc-800/50'}`}
              >第{c.chapter_num}章</button>
            ))}
          </div>
        ))}
      </div>

      {/* Main */}
      <div className="flex-1 overflow-auto p-6">
        {!selectedChapterId ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-center text-zinc-600">
              <Film size={48} className="mx-auto mb-3 opacity-30" />
              <p className="text-sm">选择章节查看视频</p>
            </div>
          </div>
        ) : loading ? (
          <div className="flex justify-center py-12"><Loader2 className="animate-spin text-indigo-400" size={24} /></div>
        ) : (
          <>
            {/* Final Video */}
            {finals.length > 0 && (
              <div className="mb-6">
                <h2 className="text-lg font-bold text-white mb-3">
                  🎞️ 第{activeChapter?.chapter_num}章 成品视频
                </h2>
                <div className="glass-card p-1 overflow-hidden max-w-2xl">
                  {activeVideo === finals[0].file_path ? (
                    <video
                      src={`http://localhost:8000/${finals[0].file_path.replace(/\\/g, '/')}`}
                      controls
                      autoPlay
                      className="w-full rounded-lg"
                      style={{ maxHeight: 400 }}
                    />
                  ) : (
                    <div
                      className="aspect-video bg-zinc-900 rounded-lg flex items-center justify-center cursor-pointer group relative"
                      onClick={() => setActiveVideo(finals[0].file_path)}
                    >
                      <div className="w-16 h-16 rounded-full bg-indigo-500/20 flex items-center justify-center group-hover:bg-indigo-500/40 transition-all">
                        <Play size={28} className="text-indigo-400 ml-1" />
                      </div>
                      <div className="absolute bottom-3 right-3 px-2 py-1 rounded bg-black/60 text-xs text-zinc-300">
                        {finals[0].file_path}
                      </div>
                    </div>
                  )}
                  <div className="flex gap-2 p-3">
                    <a
                      href={`http://localhost:8000/${finals[0].file_path.replace(/\\/g, '/')}`}
                      download
                      className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-indigo-500 text-white text-xs font-medium hover:bg-indigo-400 transition-colors"
                    >
                      <Download size={14} /> 下载
                    </a>
                    <button className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-zinc-700 text-zinc-300 text-xs hover:bg-zinc-600 transition-colors">
                      <RefreshCw size={14} /> 重新生成
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Shot Clips */}
            {clips.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-zinc-400 mb-3">
                  📹 分镜片段 ({clips.length})
                </h3>
                <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
                  {clips.map(c => (
                    <div key={c.id} className="glass-card p-3 group">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <span className="w-6 h-6 rounded bg-indigo-500/10 text-[11px] font-bold text-indigo-400 flex items-center justify-center">
                            {c.shot_num}
                          </span>
                          <span className="text-xs text-zinc-400">{c.duration_sec}s</span>
                        </div>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded ${c.status === 'done' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-zinc-700/30 text-zinc-500'}`}>
                          {c.status}
                        </span>
                      </div>
                      <video
                        src={`http://localhost:8000/${c.file_path.replace(/\\/g, '/')}`}
                        controls
                        className="w-full rounded-lg"
                        style={{ maxHeight: 160 }}
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}

            {clips.length === 0 && finals.length === 0 && (
              <div className="text-center py-12 text-zinc-600">
                <Film size={32} className="mx-auto mb-2 opacity-30" />
                <p className="text-sm">暂无视频</p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
