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
  const mediaBase = 'http://localhost:8000/';

  return (
    <div style={{ height: '100%', display: 'flex', gap: 0 }}>
      {/* Side Panel */}
      <div style={{ width: 220, flexShrink: 0, padding: '0 24px 0 0', borderRight: '1px solid var(--border)', overflow: 'auto' }}>
        <h3 style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12 }}>
          选择章节
        </h3>
        {novels.map(n => (
          <div key={n.id} style={{ marginBottom: 4 }}>
            <button
              onClick={() => setSelectedNovelId(n.id === selectedNovelId ? null : n.id)}
              style={{
                width: '100%', textAlign: 'left', padding: '8px 12px', borderRadius: 8,
                border: 'none', background: 'transparent', fontFamily: 'inherit', fontSize: 13, fontWeight: 600,
                color: selectedNovelId === n.id ? 'var(--accent)' : 'var(--text-secondary)',
                cursor: 'pointer', transition: 'all 0.12s',
              }}
            >{n.title}</button>
            {selectedNovelId === n.id && chapters.map(c => (
              <button
                key={c.id}
                onClick={() => setSelectedChapterId(c.id)}
                style={{
                  width: '100%', textAlign: 'left', padding: '7px 12px 7px 24px', borderRadius: 8,
                  border: selectedChapterId === c.id ? '1px solid var(--accent-border)' : '1px solid transparent',
                  background: selectedChapterId === c.id ? 'var(--accent-light)' : 'transparent',
                  fontFamily: 'inherit', fontSize: 13, cursor: 'pointer',
                  color: selectedChapterId === c.id ? 'var(--accent)' : 'var(--text-tertiary)',
                  transition: 'all 0.12s',
                }}
              >第{c.chapter_num}章</button>
            ))}
          </div>
        ))}
      </div>

      {/* Main */}
      <div style={{ flex: 1, overflow: 'auto', padding: '0 0 0 40px' }}>
        {!selectedChapterId ? (
          <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ textAlign: 'center', color: 'var(--text-tertiary)' }}>
              <Film size={44} style={{ marginBottom: 12, opacity: 0.35 }} />
              <p style={{ fontSize: 14 }}>选择章节查看视频</p>
            </div>
          </div>
        ) : loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 60 }}>
            <Loader2 size={24} style={{ color: 'var(--accent)', animation: 'spin 0.7s linear infinite' }} />
          </div>
        ) : (
          <>
            {/* Final Video — hero treatment */}
            {finals.length > 0 && (
              <div style={{ marginBottom: 40 }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 20 }}>
                  <h2 style={{ fontSize: 20, fontWeight: 700, color: 'var(--text)' }}>
                    第{activeChapter?.chapter_num}章 成品视频
                  </h2>
                  <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
                    {finals[0].file_path?.split(/[\\/]/).pop()}
                  </span>
                </div>

                {/* Hero Video Card */}
                <div style={{
                  background: 'var(--surface)', border: '1px solid var(--border)',
                  borderRadius: 18, overflow: 'hidden', maxWidth: 680,
                  boxShadow: 'var(--shadow-md)',
                }}>
                  {activeVideo === finals[0].file_path ? (
                    <video
                      src={mediaBase + finals[0].file_path.replace(/\\/g, '/')}
                      controls autoPlay
                      style={{ width: '100%', display: 'block' }}
                    />
                  ) : (
                    <div
                      onClick={() => setActiveVideo(finals[0].file_path)}
                      style={{
                        aspectRatio: '16/9', background: '#1a1a1a',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        cursor: 'pointer', position: 'relative',
                      }}
                    >
                      <div style={{
                        width: 64, height: 64, borderRadius: '50%',
                        background: 'rgba(255,255,255,0.15)', backdropFilter: 'blur(4px)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        transition: 'transform 0.2s',
                      }}
                        onMouseEnter={e => { e.currentTarget.style.transform = 'scale(1.1)'; }}
                        onMouseLeave={e => { e.currentTarget.style.transform = 'scale(1)'; }}
                      >
                        <Play size={28} fill="#fff" color="#fff" style={{ marginLeft: 3 }} />
                      </div>
                      <div style={{
                        position: 'absolute', bottom: 16, right: 16,
                        padding: '4px 12px', borderRadius: 8,
                        background: 'rgba(0,0,0,0.55)', color: 'rgba(255,255,255,0.75)',
                        fontSize: 12,
                      }}>{finals[0].file_path?.split(/[\\/]/).pop()}</div>
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: 10, padding: 16 }}>
                    <a
                      href={mediaBase + finals[0].file_path.replace(/\\/g, '/')}
                      download
                      style={{
                        display: 'inline-flex', alignItems: 'center', gap: 8,
                        padding: '9px 20px', borderRadius: 10,
                        background: 'var(--accent)', color: '#fff',
                        fontSize: 13, fontWeight: 600, textDecoration: 'none',
                        transition: 'all 0.15s',
                      }}
                      onMouseEnter={e => { e.currentTarget.style.background = 'var(--accent-hover)'; }}
                      onMouseLeave={e => { e.currentTarget.style.background = 'var(--accent)'; }}
                    >
                      <Download size={15} /> 下载成品
                    </a>
                    <button style={{
                      display: 'inline-flex', alignItems: 'center', gap: 8,
                      padding: '9px 20px', borderRadius: 10,
                      border: '1px solid var(--border)', background: 'var(--surface)',
                      color: 'var(--text-secondary)', fontFamily: 'inherit', fontSize: 13, fontWeight: 500,
                      cursor: 'pointer', transition: 'all 0.15s',
                    }}
                      onMouseEnter={e => { e.currentTarget.style.background = 'var(--surface-hover)'; }}
                      onMouseLeave={e => { e.currentTarget.style.background = 'var(--surface)'; }}
                    >
                      <RefreshCw size={15} /> 重新生成
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Shot Clips Grid */}
            {clips.length > 0 && (
              <div>
                <h3 style={{ fontSize: 16, fontWeight: 600, color: 'var(--text)', marginBottom: 18 }}>
                  分镜片段 · {clips.length} 个
                </h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 16 }}>
                  {clips.map(c => (
                    <div key={c.id} style={{
                      background: 'var(--surface)', border: '1px solid var(--border)',
                      borderRadius: 14, padding: 14,
                      transition: 'box-shadow 0.2s',
                    }}
                      onMouseEnter={e => { e.currentTarget.style.boxShadow = 'var(--shadow-md)'; }}
                      onMouseLeave={e => { e.currentTarget.style.boxShadow = 'var(--shadow-sm)'; }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <span style={{
                            width: 28, height: 28, borderRadius: 8,
                            background: 'var(--accent-light)', color: 'var(--accent)',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            fontSize: 12, fontWeight: 700,
                          }}>{c.shot_num}</span>
                          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{c.duration_sec}s</span>
                        </div>
                        <span style={{
                          fontSize: 10, fontWeight: 600, padding: '2px 10px', borderRadius: 100,
                          ...(c.status === 'done'
                            ? { background: 'var(--success-bg)', color: 'var(--success)' }
                            : { background: 'var(--surface-alt)', color: 'var(--text-tertiary)' }),
                        }}>{c.status}</span>
                      </div>
                      <video
                        src={mediaBase + c.file_path.replace(/\\/g, '/')}
                        controls
                        style={{ width: '100%', borderRadius: 10, display: 'block' }}
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}

            {clips.length === 0 && finals.length === 0 && (
              <div style={{ textAlign: 'center', paddingTop: 60, color: 'var(--text-tertiary)' }}>
                <Film size={36} style={{ marginBottom: 10, opacity: 0.3 }} />
                <p style={{ fontSize: 14 }}>暂无视频，先生成章节后再来查看</p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
