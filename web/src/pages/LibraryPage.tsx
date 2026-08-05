import { useState, useEffect } from 'react';
import { BookOpen, ChevronRight, FileText, Loader2, RefreshCw, X, Users, Image, Film } from 'lucide-react';
import { library } from '../api';
import { useAppStore } from '../stores/app';
import type { Novel, Chapter, Character, Scene, Shot } from '../types';

const mediaBase = 'http://localhost:8000/';

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
    if (selectedNovelId) library.chapters(selectedNovelId).then(setChapters).catch(console.error);
  }, [selectedNovelId]);
  useEffect(() => {
    if (selectedChapterId) {
      setLoading(true);
      Promise.all([
        library.characters(selectedChapterId), library.scenes(selectedChapterId), library.shots(selectedChapterId),
      ]).then(([c, s, sh]) => { setCharacters(c); setScenes(s); setShots(sh); })
        .catch(console.error).finally(() => setLoading(false));
    }
  }, [selectedChapterId]);

  const activeCh = chapters.find(c => c.id === selectedChapterId);

  return (
    <div style={{ height: '100%', display: 'flex', gap: 0 }}>
      {/* Left Panel */}
      <div style={{ width: 220, flexShrink: 0, padding: '0 24px 0 0', borderRight: '1px solid var(--border)', overflow: 'auto' }}>
        <h3 style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>小说</h3>
        {novels.map(n => (
          <div key={n.id} style={{ marginBottom: 2 }}>
            <button
              onClick={() => setSelectedNovelId(n.id === selectedNovelId ? null : n.id)}
              style={{
                width: '100%', display: 'flex', alignItems: 'center', gap: 8,
                padding: '8px 12px', borderRadius: 8,
                border: selectedNovelId === n.id ? '1px solid var(--accent-border)' : '1px solid transparent',
                background: selectedNovelId === n.id ? 'var(--accent-light)' : 'transparent',
                color: selectedNovelId === n.id ? 'var(--accent)' : 'var(--text-secondary)',
                fontFamily: 'inherit', fontSize: 13, fontWeight: 500, cursor: 'pointer',
                transition: 'all 0.12s',
              }}
            >
              <BookOpen size={15} style={{ opacity: 0.6 }} />
              <span style={{ flex: 1, textAlign: 'left', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{n.title}</span>
              <ChevronRight size={13} style={{ transform: selectedNovelId === n.id ? 'rotate(90deg)' : '', transition: 'transform 0.2s' }} />
            </button>
            {selectedNovelId === n.id && (
              <div style={{ marginTop: 2, marginBottom: 8 }}>
                {chapters.map(c => (
                  <button
                    key={c.id}
                    onClick={() => setSelectedChapterId(c.id === selectedChapterId ? null : c.id)}
                    style={{
                      width: '100%', display: 'flex', alignItems: 'center', gap: 8,
                      padding: '7px 12px 7px 28px', borderRadius: 8,
                      border: selectedChapterId === c.id ? '1px solid var(--accent-border)' : '1px solid transparent',
                      background: selectedChapterId === c.id ? 'var(--accent-light)' : 'transparent',
                      color: selectedChapterId === c.id ? 'var(--accent)' : 'var(--text-tertiary)',
                      fontFamily: 'inherit', fontSize: 13, cursor: 'pointer',
                      transition: 'all 0.12s',
                    }}
                  >
                    <FileText size={14} />
                    <span style={{ flex: 1, textAlign: 'left' }}>第{c.chapter_num}章</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Main */}
      <div style={{ flex: 1, overflow: 'auto', padding: '0 0 0 40px' }}>
        {!selectedNovelId && <EmptyState icon={BookOpen} text="选择一本小说开始浏览" />}
        {selectedNovelId && !selectedChapterId && <EmptyState icon={FileText} text="选择一个章节查看素材" />}
        {selectedChapterId && (
          <>
            {/* Header + Tabs */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 28 }}>
              <div>
                <h2 style={{ fontSize: 20, fontWeight: 700, color: 'var(--text)', lineHeight: 1.3 }}>
                  第{activeCh?.chapter_num}章 素材
                </h2>
                <p style={{ fontSize: 13, color: 'var(--text-tertiary)', marginTop: 4 }}>人物 · 场景 · 分镜</p>
              </div>
              <div style={{ display: 'flex', gap: 4, background: 'var(--surface-alt)', borderRadius: 12, padding: 4 }}>
                {([
                  { k: 'characters' as const, icon: Users, label: '人物', count: characters.length },
                  { k: 'scenes' as const, icon: Image, label: '场景', count: scenes.length },
                  { k: 'shots' as const, icon: Film, label: '分镜', count: shots.length },
                ]).map(({ k, icon: Ic, label, count }) => (
                  <button
                    key={k}
                    onClick={() => setTab(k)}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 7,
                      padding: '7px 18px', borderRadius: 9, border: 'none',
                      background: tab === k ? 'var(--surface)' : 'transparent',
                      color: tab === k ? 'var(--text)' : 'var(--text-tertiary)',
                      boxShadow: tab === k ? 'var(--shadow-sm)' : 'none',
                      fontFamily: 'inherit', fontSize: 13, fontWeight: 500,
                      cursor: 'pointer', transition: 'all 0.12s',
                    }}
                  >
                    <Ic size={15} />
                    <span>{label}</span>
                    <span style={{ fontSize: 11, opacity: 0.5 }}>{count}</span>
                  </button>
                ))}
              </div>
            </div>

            {loading ? (
              <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 60 }}>
                <Loader2 size={24} style={{ color: 'var(--accent)', animation: 'spin 0.7s linear infinite' }} />
              </div>
            ) : (
              <>
                {/* CHARACTERS — elegant portrait cards */}
                {tab === 'characters' && (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))', gap: 20 }}>
                    {characters.map(c => {
                      const mainOutfit = c.outfits.find(o => o.image_path) || c.outfits[0];
                      return (
                        <div key={c.id} style={{
                          background: 'var(--surface)', border: '1px solid var(--border)',
                          borderRadius: 16, overflow: 'hidden',
                          transition: 'box-shadow 0.25s, transform 0.2s',
                        }}
                          onMouseEnter={e => { e.currentTarget.style.boxShadow = 'var(--shadow-lg)'; e.currentTarget.style.transform = 'translateY(-2px)'; }}
                          onMouseLeave={e => { e.currentTarget.style.boxShadow = 'var(--shadow-sm)'; e.currentTarget.style.transform = 'translateY(0)'; }}
                        >
                          {/* Image */}
                          <div
                            style={{ aspectRatio: '3/4', background: '#e8e5e0', overflow: 'hidden', cursor: mainOutfit?.image_path ? 'pointer' : 'default', position: 'relative' }}
                            onClick={() => mainOutfit?.image_path && setPreviewImg(mediaBase + mainOutfit.image_path.replace(/\\/g, '/'))}
                          >
                            {mainOutfit?.image_path ? (
                              <img
                                src={mediaBase + mainOutfit.image_path.replace(/\\/g, '/')}
                                alt={c.name}
                                style={{ width: '100%', height: '100%', objectFit: 'cover', transition: 'transform 0.35s' }}
                                onMouseEnter={e => { e.currentTarget.style.transform = 'scale(1.04)'; }}
                                onMouseLeave={e => { e.currentTarget.style.transform = 'scale(1)'; }}
                              />
                            ) : (
                              <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-tertiary)' }}>
                                <Users size={36} style={{ opacity: 0.25 }} />
                              </div>
                            )}
                          </div>
                          {/* Info */}
                          <div style={{ padding: '16px 18px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
                              <h3 style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)' }}>{c.name}</h3>
                              <button style={{
                                width: 28, height: 28, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center',
                                border: '1px solid var(--border)', background: 'var(--surface)',
                                color: 'var(--text-tertiary)', cursor: 'pointer', opacity: 0, transition: 'all 0.15s',
                              }}
                                onMouseEnter={e => { e.currentTarget.style.color = 'var(--accent)'; e.currentTarget.style.borderColor = 'var(--accent-border)'; }}
                                onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-tertiary)'; e.currentTarget.style.borderColor = 'var(--border)'; }}
                              >
                                <RefreshCw size={13} />
                              </button>
                            </div>
                            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                              {c.outfits.map(o => (
                                <span key={o.id} style={{
                                  fontSize: 10, fontWeight: 500, padding: '2px 10px', borderRadius: 100,
                                  background: o.is_default ? 'var(--accent-light)' : 'var(--surface-alt)',
                                  color: o.is_default ? 'var(--accent)' : 'var(--text-tertiary)',
                                }}>{o.tag}</span>
                              ))}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* SCENES — atmospheric wide cards */}
                {tab === 'scenes' && (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 20 }}>
                    {scenes.map(s => (
                      <div key={s.id} style={{
                        background: 'var(--surface)', border: '1px solid var(--border)',
                        borderRadius: 16, overflow: 'hidden',
                        transition: 'box-shadow 0.25s, transform 0.2s',
                      }}
                        onMouseEnter={e => { e.currentTarget.style.boxShadow = 'var(--shadow-lg)'; e.currentTarget.style.transform = 'translateY(-2px)'; }}
                        onMouseLeave={e => { e.currentTarget.style.boxShadow = 'var(--shadow-sm)'; e.currentTarget.style.transform = 'translateY(0)'; }}
                      >
                        {/* Scene image — cinematic widescreen */}
                        <div
                          style={{ aspectRatio: '16/9', background: '#e8e5e0', overflow: 'hidden', cursor: s.multi_view_image ? 'pointer' : 'default', position: 'relative' }}
                          onClick={() => s.multi_view_image && setPreviewImg(mediaBase + s.multi_view_image.replace(/\\/g, '/'))}
                        >
                          {s.multi_view_image ? (
                            <img
                              src={mediaBase + s.multi_view_image.replace(/\\/g, '/')}
                              alt={s.name}
                              style={{ width: '100%', height: '100%', objectFit: 'cover', transition: 'transform 0.35s' }}
                              onMouseEnter={e => { e.currentTarget.style.transform = 'scale(1.03)'; }}
                              onMouseLeave={e => { e.currentTarget.style.transform = 'scale(1)'; }}
                            />
                          ) : (
                            <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-tertiary)' }}>
                              <Image size={36} style={{ opacity: 0.2 }} />
                            </div>
                          )}
                        </div>
                        <div style={{ padding: '16px 20px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                            <h3 style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)' }}>{s.name}</h3>
                            <button style={{
                              width: 28, height: 28, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center',
                              border: '1px solid var(--border)', background: 'var(--surface)',
                              color: 'var(--text-tertiary)', cursor: 'pointer', transition: 'all 0.15s',
                            }}>
                              <RefreshCw size={13} />
                            </button>
                          </div>
                          <p style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: 6 }}>
                            {s.description?.slice(0, 60)}{s.description?.length > 60 ? '…' : ''}
                          </p>
                          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                            <span style={{ fontSize: 10, fontWeight: 500, padding: '2px 10px', borderRadius: 100, background: 'var(--surface-alt)', color: 'var(--text-tertiary)' }}>
                              {s.lighting?.split('，')[0]?.slice(0, 20)}
                            </span>
                            {s.style && (
                              <span style={{ fontSize: 10, fontWeight: 500, padding: '2px 10px', borderRadius: 100, background: 'var(--accent-light)', color: 'var(--accent)' }}>
                                {s.style}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* SHOTS — timeline style */}
                {tab === 'shots' && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    {shots.map((s, idx) => (
                      <div key={s.id} style={{
                        display: 'flex', gap: 16, padding: '18px 22px',
                        background: 'var(--surface)', border: '1px solid var(--border)',
                        borderRadius: 14, transition: 'box-shadow 0.15s',
                      }}
                        onMouseEnter={e => { e.currentTarget.style.boxShadow = 'var(--shadow-md)'; }}
                        onMouseLeave={e => { e.currentTarget.style.boxShadow = 'var(--shadow-sm)'; }}
                      >
                        {/* Shot number + timeline connector */}
                        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flexShrink: 0, width: 36 }}>
                          <div style={{
                            width: 32, height: 32, borderRadius: 10,
                            background: 'var(--accent-light)', color: 'var(--accent)',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            fontSize: 13, fontWeight: 700,
                          }}>#{s.shot_num}</div>
                          {idx < shots.length - 1 && (
                            <div style={{ width: 1, flex: 1, minHeight: 12, marginTop: 4, background: 'var(--border)' }} />
                          )}
                        </div>
                        {/* Content */}
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <p style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', lineHeight: 1.5, marginBottom: 4 }}>
                            {s.narration || s.dialogue || '(无旁白/对白)'}
                          </p>
                          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginTop: 8 }}>
                            <span style={{ fontSize: 11, color: 'var(--text-tertiary)', display: 'flex', alignItems: 'center', gap: 4 }}>
                              🎥 {s.camera_movement}
                            </span>
                            <span style={{ fontSize: 11, color: 'var(--text-tertiary)', display: 'flex', alignItems: 'center', gap: 4 }}>
                              ⏱ {s.duration_sec}s
                            </span>
                            <span style={{
                              fontSize: 10, fontWeight: 600, padding: '2px 10px', borderRadius: 100,
                              ...(s.status === 'done' ? { background: 'var(--success-bg)', color: 'var(--success)' } : { background: 'var(--surface-alt)', color: 'var(--text-tertiary)' }),
                            }}>{s.status}</span>
                            {s.image_prompt && (
                              <span style={{ fontSize: 11, color: 'var(--text-tertiary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 200 }}>
                                📝 {s.image_prompt.slice(0, 40)}…
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </>
        )}
      </div>

      {/* Preview Modal */}
      {previewImg && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 50,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(8px)',
        }} onClick={() => setPreviewImg(null)}>
          <button style={{
            position: 'absolute', top: 24, right: 24, width: 40, height: 40, borderRadius: '50%',
            border: 'none', background: 'rgba(255,255,255,0.9)', color: '#333',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: 'pointer', fontSize: 18,
          }} onClick={() => setPreviewImg(null)}>
            <X size={20} />
          </button>
          <img src={previewImg} alt="preview" style={{ maxWidth: '82vw', maxHeight: '88vh', borderRadius: 16, boxShadow: '0 20px 60px rgba(0,0,0,0.3)' }} onClick={e => e.stopPropagation()} />
        </div>
      )}
    </div>
  );
}

function EmptyState({ icon: Icon, text }: { icon: any; text: string }) {
  return (
    <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ textAlign: 'center', color: 'var(--text-tertiary)' }}>
        <Icon size={44} style={{ marginBottom: 14, opacity: 0.3 }} />
        <p style={{ fontSize: 14 }}>{text}</p>
      </div>
    </div>
  );
}
