import { useState, useEffect, useCallback } from 'react';
import { Film, Play, Download, Loader2, RefreshCw, X, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { library, videos, agents } from '../api';
import { useAppStore } from '../stores/app';
import type { Chapter, FinalVideo, VideoClip } from '../types';

const mediaBase = 'http://localhost:8000/';

function FinalVideoCard({ video, chapterNum, onCompose, composing }: {
  video: FinalVideo;
  chapterNum?: number;
  onCompose: () => void;
  composing: boolean;
}) {
  const [active, setActive] = useState(false);
  const isEmpty = (video.file_size ?? 0) === 0;
  const fileName = video.file_path?.split(/[\\/]/).pop() || video.file_path;
  const sizeStr = isEmpty ? '空文件' : (video.file_size > 1048576
    ? `${(video.file_size / 1048576).toFixed(1)} MB`
    : `${(video.file_size / 1024).toFixed(0)} KB`);

  if (isEmpty) {
    return (
      <div style={{ marginBottom: 40 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 20 }}>
          <h2 style={{ fontSize: 20, fontWeight: 700, color: 'var(--text)' }}>第{chapterNum}章 成品视频</h2>
          <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{fileName} · 空文件</span>
        </div>
        <div style={{ background: '#FDF5E8', border: '1px solid #F0D0A0', borderRadius: 18, padding: '40px 28px', maxWidth: 680, textAlign: 'center' }}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>⚠️</div>
          <div style={{ fontSize: 15, fontWeight: 600, color: '#8A6A30', marginBottom: 8 }}>视频文件为空（0 字节）</div>
          <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginBottom: 16, lineHeight: 1.6 }}>
            生成过程中可能出错了。建议重新生成视频。
          </div>
          <button onClick={onCompose} style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '9px 20px', borderRadius: 10, border: 'none', background: 'var(--accent)', color: '#fff', fontFamily: 'inherit', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>
            <Film size={15} /> 重新合成
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={{ marginBottom: 40 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 20 }}>
        <h2 style={{ fontSize: 20, fontWeight: 700, color: 'var(--text)' }}>第{chapterNum}章 成品视频</h2>
        <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{fileName} · {sizeStr}</span>
      </div>
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 18, overflow: 'hidden', maxWidth: 680, boxShadow: 'var(--shadow-md)' }}>
        {active ? (
          <video src={mediaBase + video.file_path.replace(/\\/g, '/')} controls autoPlay style={{ width: '100%', display: 'block' }} />
        ) : (
          <div onClick={() => setActive(true)} style={{ aspectRatio: '16/9', background: '#1a1a1a', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', position: 'relative' }}>
            <div style={{ width: 64, height: 64, borderRadius: '50%', background: 'rgba(255,255,255,0.15)', backdropFilter: 'blur(4px)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Play size={28} fill="#fff" color="#fff" style={{ marginLeft: 3 }} />
            </div>
            <div style={{ position: 'absolute', bottom: 16, right: 16, padding: '4px 12px', borderRadius: 8, background: 'rgba(0,0,0,0.55)', color: 'rgba(255,255,255,0.75)', fontSize: 12 }}>{fileName} · {sizeStr}</div>
          </div>
        )}
        <div style={{ display: 'flex', gap: 10, padding: 16 }}>
          <a href={mediaBase + video.file_path.replace(/\\/g, '/')} download style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '9px 20px', borderRadius: 10, background: 'var(--accent)', color: '#fff', fontSize: 13, fontWeight: 600, textDecoration: 'none' }}>
            <Download size={15} /> 下载成品
          </a>
          <button onClick={onCompose} disabled={composing} style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '9px 20px', borderRadius: 10, border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text-secondary)', fontFamily: 'inherit', fontSize: 13, fontWeight: 500, cursor: composing ? 'not-allowed' : 'pointer', opacity: composing ? 0.5 : 1 }}>
            {composing ? <Loader2 size={15} style={{ animation: 'spin 0.7s linear infinite' }} /> : <Film size={15} />} {composing ? '合成中…' : '重新合成'}
          </button>
        </div>
      </div>
    </div>
  );
}

export function VideosPage() {
  const { selectedNovelId, setSelectedNovelId, selectedChapterId, setSelectedChapterId } = useAppStore();
  const [novels, setNovels] = useState<any[]>([]);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [clips, setClips] = useState<VideoClip[]>([]);
  const [finals, setFinals] = useState<FinalVideo[]>([]);
  const [loading, setLoading] = useState(false);
  const [composing, setComposing] = useState(false);
  const [toast, setToast] = useState<{ msg: string; type: 'success' | 'error' | 'loading' } | null>(null);

  const showToast = useCallback((msg: string, type: 'success' | 'error' | 'loading') => {
    setToast({ msg, type });
    if (type !== 'loading') setTimeout(() => setToast(null), 3000);
  }, []);

  // ── 单镜头视频重生成 ──
  const handleClipRegen = useCallback(async (shotNum: number) => {
    if (!selectedChapterId) return;
    try {
      showToast(`正在重新生成镜头 ${shotNum} 的视频…`, 'loading');
      const res = await agents.run({
        agent: 'shot-video-generator',
        target_type: 'shot',
        target_id: 0,
        chapter_id: selectedChapterId,
        shot_num: shotNum,
      });
      let attempts = 0;
      const check = setInterval(async () => {
        try {
          const t = await (await fetch(`/api/tasks/${res.task_id}`)).json();
          if (t.status === 'done') {
            clearInterval(check);
            showToast(`✅ 镜头 ${shotNum} 视频生成完成`, 'success');
            videos.list(selectedChapterId).then(({ clips, finals }) => { setClips(clips); setFinals(finals); }).catch(console.error);
          } else if (t.status === 'failed') {
            clearInterval(check);
            showToast(`❌ 镜头 ${shotNum} 视频生成失败: ${t.error || '未知错误'}`, 'error');
          }
        } catch {}
        attempts++;
        if (attempts > 300) { clearInterval(check); showToast(`⏰ 镜头 ${shotNum} 视频生成超时`, 'error'); }
      }, 3000);
    } catch (e: any) {
      showToast(`❌ 镜头 ${shotNum} 启动失败: ${e.message}`, 'error');
    }
  }, [selectedChapterId, showToast]);

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
            {/* Final Video */}
            {finals.length > 0 && (
              <FinalVideoCard
                video={finals[0]}
                chapterNum={activeChapter?.chapter_num}
                composing={composing}
                onCompose={async () => {
                  if (!selectedChapterId || composing) return;
                  setComposing(true);
                  try {
                    const { task_id } = await agents.run({ agent: 'video-composer', target_type: 'chapter', target_id: selectedChapterId, chapter_id: selectedChapterId });
                    const poll = setInterval(async () => {
                      try {
                        const res = await fetch(`/api/tasks/${task_id}`);
                        const t = await res.json();
                        if (t.status === 'done' || t.status === 'failed') {
                          clearInterval(poll);
                          setComposing(false);
                          videos.list(selectedChapterId).then(({ clips, finals }) => { setClips(clips); setFinals(finals); }).catch(console.error);
                        }
                      } catch {}
                    }, 2000);
                  } catch (e) { console.error(e); setComposing(false); }
                }}
              />
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
                            padding: '2px 12px', height: 28, borderRadius: 8,
                            background: 'var(--accent-light)', color: 'var(--accent)',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            fontSize: 12, fontWeight: 700,
                          }}>镜头{c.shot_num}</span>
                          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{c.duration_sec}s</span>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <span style={{
                            fontSize: 10, fontWeight: 600, padding: '2px 10px', borderRadius: 100,
                            ...(c.status === 'done'
                              ? { background: 'var(--success-bg)', color: 'var(--success)' }
                              : { background: 'var(--surface-alt)', color: 'var(--text-tertiary)' }),
                          }}>{c.status}</span>
                          <button
                            onClick={() => handleClipRegen(c.shot_num)}
                            title={`重新生成镜头 ${c.shot_num} 的视频`}
                            style={{
                              width: 28, height: 28, borderRadius: 7,
                              border: '1px solid var(--border)',
                              background: 'var(--surface)',
                              color: 'var(--text-secondary)',
                              display: 'flex', alignItems: 'center', justifyContent: 'center',
                              cursor: 'pointer', transition: 'all 0.15s',
                            }}
                            onMouseEnter={e => {
                              e.currentTarget.style.background = 'var(--accent-light)';
                              e.currentTarget.style.color = 'var(--accent)';
                              e.currentTarget.style.borderColor = 'var(--accent)';
                            }}
                            onMouseLeave={e => {
                              e.currentTarget.style.background = 'var(--surface)';
                              e.currentTarget.style.color = 'var(--text-secondary)';
                              e.currentTarget.style.borderColor = 'var(--border)';
                            }}
                          >
                            <RefreshCw size={12} />
                          </button>
                        </div>
                      </div>
                      <video
                        src={mediaBase + c.file_path.replace(/\\/g, '/')}
                        controls
                        style={{ width: '100%', borderRadius: 10, display: 'block' }}
                      />
                      <a
                        href={mediaBase + c.file_path.replace(/\\/g, '/')}
                        download
                        style={{
                          display: 'inline-flex', alignItems: 'center', gap: 6,
                          marginTop: 8, padding: '5px 12px', borderRadius: 7,
                          background: 'var(--surface-alt)', color: 'var(--text-secondary)',
                          fontSize: 11, fontWeight: 500, textDecoration: 'none',
                          transition: 'all 0.15s',
                        }}
                        onMouseEnter={e => { e.currentTarget.style.background = 'var(--accent-light)'; e.currentTarget.style.color = 'var(--accent)'; }}
                        onMouseLeave={e => { e.currentTarget.style.background = 'var(--surface-alt)'; e.currentTarget.style.color = 'var(--text-secondary)'; }}
                      >
                        <Download size={12} /> 下载片段
                      </a>
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
      {/* Toast */}
      {toast && (
        <div style={{ position: 'fixed', bottom: 32, right: 32, zIndex: 100, padding: '12px 20px', borderRadius: 12, background: toast.type === 'success' ? 'var(--success-bg)' : toast.type === 'error' ? 'var(--error-bg)' : '#E8F2FD', border: `1px solid ${toast.type === 'success' ? 'var(--success)40' : toast.type === 'error' ? 'var(--error)40' : '#B8D8F0'}`, display: 'flex', alignItems: 'center', gap: 10, boxShadow: 'var(--shadow-lg)', maxWidth: 360 }}>
          {toast.type === 'loading' ? <Loader2 size={16} style={{ color: '#3B82C0', animation: 'spin 0.7s linear infinite' }} /> : toast.type === 'error' ? <AlertTriangle size={16} style={{ color: 'var(--error)' }} /> : <CheckCircle2 size={16} style={{ color: 'var(--success)' }} />}
          <span style={{ fontSize: 13, color: 'var(--text)', lineHeight: 1.4 }}>{toast.msg}</span>
          <button onClick={() => setToast(null)} style={{ marginLeft: 'auto', background: 'none', border: 'none', color: 'var(--text-tertiary)', cursor: 'pointer', padding: 2 }}><X size={14} /></button>
        </div>
      )}
    </div>
  );
}
