import { useState, useEffect, useCallback } from 'react';
import { BookOpen, ChevronRight, FileText, Loader2, RefreshCw, X, Users, Image, Film, CheckCircle2, AlertTriangle, Trash2 } from 'lucide-react';
import { library, agents } from '../api';
import { useAppStore } from '../stores/app';
import type { Novel, Chapter, Character, Scene, Shot } from '../types';

const mediaBase = 'http://localhost:8000/';

// Toast notification
function Toast({ msg, type, onClose }: { msg: string; type: 'success' | 'error' | 'loading'; onClose: () => void }) {
  const bg = type === 'success' ? 'var(--success-bg)' : type === 'error' ? 'var(--error-bg)' : '#E8F2FD';
  const border = type === 'success' ? 'var(--success)40' : type === 'error' ? 'var(--error)40' : '#B8D8F0';
  const color = type === 'success' ? 'var(--success)' : type === 'error' ? 'var(--error)' : '#3B82C0';
  const Icon = type === 'success' ? CheckCircle2 : type === 'error' ? AlertTriangle : Loader2;
  return (
    <div style={{ position: 'fixed', bottom: 32, right: 32, zIndex: 100, padding: '12px 20px', borderRadius: 12, background: bg, border: `1px solid ${border}`, display: 'flex', alignItems: 'center', gap: 10, boxShadow: 'var(--shadow-lg)', maxWidth: 360 }}>
      <Icon size={16} style={{ color, flexShrink: 0, ...(type === 'loading' ? { animation: 'spin 0.7s linear infinite' } : {}) }} />
      <span style={{ fontSize: 13, color: 'var(--text)', lineHeight: 1.4 }}>{msg}</span>
      <button onClick={onClose} style={{ marginLeft: 'auto', background: 'none', border: 'none', color: 'var(--text-tertiary)', cursor: 'pointer', padding: 2 }}><X size={14} /></button>
    </div>
  );
}

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
  const [toast, setToast] = useState<{ msg: string; type: 'success' | 'error' | 'loading' } | null>(null);

  const showToast = useCallback((msg: string, type: 'success' | 'error' | 'loading') => {
    setToast({ msg, type });
    if (type !== 'loading') setTimeout(() => setToast(null), 3000);
  }, []);

  const handleRegen = useCallback(async (targetType: string, targetId: number, name: string) => {
    if (!selectedChapterId) return;
    try {
      if (targetType === 'character') {
        // ── 角色重生成：先通过 char-designer 重写设计提示词（统一CG风格），再生成图片 ──
        showToast(`正在重新设计 ${name} 的形象…`, 'loading');
        const designRes = await agents.run({
          agent: 'char-designer',
          target_type: targetType,
          target_id: targetId,
          chapter_id: selectedChapterId,
        });
        // Poll for char-designer completion
        await new Promise<void>((resolve, reject) => {
          let attempts = 0;
          const check = setInterval(async () => {
            try {
              const t = await (await fetch(`/api/tasks/${designRes.task_id}`)).json();
              if (t.status === 'done') {
                clearInterval(check);
                resolve();
              } else if (t.status === 'failed') {
                clearInterval(check);
                reject(new Error(t.error || '设计失败'));
              }
            } catch {}
            attempts++;
            if (attempts > 90) { clearInterval(check); reject(new Error('设计超时')); }
          }, 2000);
        });
        // ── 设计完成，自动生成图片 ──
        showToast(`正在生成 ${name} 的新图片…`, 'loading');
        const imgRes = await agents.run({
          agent: 'image-generator',
          target_type: targetType,
          target_id: targetId,
          chapter_id: selectedChapterId,
        });
        let imgAttempts = 0;
        const imgCheck = setInterval(async () => {
          try {
            const t = await (await fetch(`/api/tasks/${imgRes.task_id}`)).json();
            if (t.status === 'done') {
              clearInterval(imgCheck);
              showToast(`✅ ${name} 重新生成完成（统一 CG 风格）`, 'success');
              library.characters(selectedChapterId).then(setCharacters).catch(console.error);
            } else if (t.status === 'failed') {
              clearInterval(imgCheck);
              showToast(`❌ ${name} 图片生成失败: ${t.error || '未知错误'}。设计提示词已更新，可稍后重试`, 'error');
            }
          } catch {}
          imgAttempts++;
          if (imgAttempts > 120) { clearInterval(imgCheck); showToast(`⏰ ${name} 图片生成超时`, 'error'); }
        }, 2000);
      } else {
        // ── 场景重生成：直接调 image-generator（场景提示词不受风格影响）──
        showToast(`正在重新生成 ${name}…`, 'loading');
        const res = await agents.run({
          agent: 'image-generator',
          target_type: targetType,
          target_id: targetId,
          chapter_id: selectedChapterId,
        });
        let attempts = 0;
        const check = setInterval(async () => {
          try {
            const t = await (await fetch(`/api/tasks/${res.task_id}`)).json();
            if (t.status === 'done') {
              clearInterval(check);
              showToast(`✅ ${name} 重新生成完成`, 'success');
              library.scenes(selectedChapterId).then(setScenes).catch(console.error);
            } else if (t.status === 'failed') {
              clearInterval(check);
              showToast(`❌ ${name} 重新生成失败: ${t.error || '未知错误'}`, 'error');
            }
          } catch {}
          attempts++;
          if (attempts > 60) { clearInterval(check); showToast(`⏰ ${name} 生成超时`, 'error'); }
        }, 2000);
      }
    } catch (e: any) {
      showToast(`❌ ${name} 启动失败: ${e.message}`, 'error');
    }
  }, [selectedChapterId, showToast]);

  // ── 单镜头视频重生成 ──
  const handleShotRegen = useCallback(async (shotId: number, shotNum: number) => {
    if (!selectedChapterId) return;
    try {
      showToast(`正在生成镜头 ${shotNum} 的视频…`, 'loading');
      const res = await agents.run({
        agent: 'shot-video-generator',
        target_type: 'shot',
        target_id: shotId,
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
            library.shots(selectedChapterId).then(setShots).catch(console.error);
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

  const handleDeleteChapter = useCallback(async (chapterId: number, chapterNum: number) => {
    if (!window.confirm(`确定删除第${chapterNum}章及其所有素材（角色/场景/分镜/视频）？\n此操作不可撤销。`)) return;
    try {
      const res = await library.deleteChapter(chapterId);
      showToast(`已删除第${chapterNum}章（${res.deleted_files} 个文件）`, 'success');
      if (selectedChapterId === chapterId) {
        setSelectedChapterId(null);
        setCharacters([]); setScenes([]); setShots([]);
      }
      if (selectedNovelId) library.chapters(selectedNovelId).then(setChapters).catch(console.error);
    } catch (e: any) {
      showToast(`删除失败: ${e.message}`, 'error');
    }
  }, [selectedNovelId, selectedChapterId, setSelectedChapterId, showToast]);

  const handleDeleteNovel = useCallback(async (novelId: number, title: string) => {
    if (!window.confirm(`确定删除「${title}」及其所有章节和素材？\n此操作不可撤销。`)) return;
    try {
      const res = await library.deleteNovel(novelId);
      showToast(`已删除「${title}」（${res.deleted_chapters} 章, ${res.deleted_files} 个文件）`, 'success');
      if (selectedNovelId === novelId) {
        setSelectedNovelId(null); setSelectedChapterId(null);
        setChapters([]); setCharacters([]); setScenes([]); setShots([]);
      }
      library.novels().then(setNovels).catch(console.error);
    } catch (e: any) {
      showToast(`删除失败: ${e.message}`, 'error');
    }
  }, [selectedNovelId, setSelectedNovelId, setSelectedChapterId, showToast]);

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
          <div key={n.id} style={{ marginBottom: 2, position: 'relative' }}>
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
            <button
              onClick={(e) => { e.stopPropagation(); handleDeleteNovel(n.id, n.title); }}
              title="删除小说及其所有章节"
              style={{
                position: 'absolute', right: 0, top: 8,
                width: 22, height: 22, borderRadius: 5,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                border: 'none', background: 'transparent', color: 'var(--text-tertiary)',
                cursor: 'pointer', opacity: 0, transition: 'opacity 0.15s',
              }}
              onMouseEnter={e => { e.currentTarget.style.opacity = '1'; }}
              onMouseLeave={e => { e.currentTarget.style.opacity = '0'; }}
            >
              <Trash2 size={12} />
            </button>
            {selectedNovelId === n.id && (
              <div style={{ marginTop: 2, marginBottom: 8 }}>
                {chapters.map(c => (
                  <div key={c.id} style={{ position: 'relative' }}>
                    <button
                      onClick={() => setSelectedChapterId(c.id === selectedChapterId ? null : c.id)}
                      style={{
                        width: '100%', display: 'flex', alignItems: 'center', gap: 8,
                        padding: '7px 28px 7px 28px', borderRadius: 8,
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
                    <button
                      onClick={(e) => { e.stopPropagation(); handleDeleteChapter(c.id, c.chapter_num); }}
                      title={`删除第${c.chapter_num}章`}
                      style={{
                        position: 'absolute', right: 2, top: 7,
                        width: 20, height: 20, borderRadius: 5,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        border: 'none', background: 'transparent', color: 'var(--text-tertiary)',
                        cursor: 'pointer', opacity: 0, transition: 'opacity 0.15s',
                      }}
                      onMouseEnter={e => { e.currentTarget.style.opacity = '1'; }}
                      onMouseLeave={e => { e.currentTarget.style.opacity = '0'; }}
                    >
                      <Trash2 size={11} />
                    </button>
                  </div>
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
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
                    {characters.map(c => {
                      const mainOutfit = c.outfits.find(o => o.image_path) || c.outfits[0];
                      return (
                        <div key={c.id} style={{
                          background: 'var(--surface)', border: '1px solid var(--border)',
                          borderRadius: 12, overflow: 'hidden',
                          transition: 'box-shadow 0.25s, transform 0.2s',
                        }}
                          onMouseEnter={e => { e.currentTarget.style.boxShadow = 'var(--shadow-md)'; e.currentTarget.style.transform = 'translateY(-2px)'; }}
                          onMouseLeave={e => { e.currentTarget.style.boxShadow = 'var(--shadow-sm)'; e.currentTarget.style.transform = 'translateY(0)'; }}
                        >
                          {/* Image */}
                          <div
                            style={{ aspectRatio: '2/3', background: '#e8e5e0', overflow: 'hidden', cursor: mainOutfit?.image_path ? 'pointer' : 'default', position: 'relative' }}
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
                          <div style={{ padding: '10px 12px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 2 }}>
                              <h3 style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>{c.name}</h3>
                              <button
                                onClick={() => handleRegen('character', c.id, c.name)}
                                title={`重新生成 ${c.name} 的角色图`}
                                style={{
                                width: 22, height: 22, borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center',
                                border: '1px solid var(--border)', background: 'var(--surface)',
                                color: 'var(--text-tertiary)', cursor: 'pointer', transition: 'all 0.15s',
                              }}
                                onMouseEnter={e => { e.currentTarget.style.color = 'var(--accent)'; e.currentTarget.style.borderColor = 'var(--accent-border)'; }}
                                onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-tertiary)'; e.currentTarget.style.borderColor = 'var(--border)'; }}
                              >
                                <RefreshCw size={11} />
                              </button>
                            </div>
                            {c.outfits.length > 1 && (
                              <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 4 }}>
                                {c.outfits.filter(o => !o.is_default).slice(0, 2).map(o => (
                                  <span key={o.id} style={{
                                    fontSize: 9, fontWeight: 500, padding: '1px 8px', borderRadius: 100,
                                    background: 'var(--surface-alt)', color: 'var(--text-tertiary)',
                                  }}>{o.tag}</span>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* SCENES — atmospheric wide cards */}
                {tab === 'scenes' && (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
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
                            <button
                              onClick={() => handleRegen('scene', s.id, s.name)}
                              title={`重新生成 ${s.name} 的场景图`}
                              style={{
                              width: 28, height: 28, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center',
                              border: '1px solid var(--border)', background: 'var(--surface)',
                              color: 'var(--text-tertiary)', cursor: 'pointer', transition: 'all 0.15s',
                            }}
                              onMouseEnter={e => { e.currentTarget.style.color = 'var(--accent)'; e.currentTarget.style.borderColor = 'var(--accent-border)'; }}
                              onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-tertiary)'; e.currentTarget.style.borderColor = 'var(--border)'; }}
                            >
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
                    {shots.map((s, idx) => {
                      const hasPrompt = !!s.image_prompt;
                      const isPending = !hasPrompt;
                      return (
                      <div key={s.id} style={{
                        display: 'flex', gap: 16, padding: '18px 22px',
                        background: isPending ? 'var(--surface-alt)' : 'var(--surface)',
                        border: isPending ? '1px dashed var(--border)' : '1px solid var(--border)',
                        borderRadius: 14, transition: 'box-shadow 0.15s',
                        opacity: isPending ? 0.7 : undefined,
                      }}
                        onMouseEnter={e => { e.currentTarget.style.boxShadow = 'var(--shadow-md)'; }}
                        onMouseLeave={e => { e.currentTarget.style.boxShadow = 'var(--shadow-sm)'; }}
                      >
                        {/* Shot number + timeline connector */}
                        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flexShrink: 0, width: 52 }}>
                          <div style={{
                            width: 52, height: 28, borderRadius: 8,
                            background: isPending ? 'var(--surface)' : 'var(--accent-light)',
                            color: isPending ? 'var(--text-tertiary)' : 'var(--accent)',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            fontSize: 12, fontWeight: 700, border: isPending ? '1px solid var(--border)' : 'none',
                          }}>镜头{s.shot_num}</div>
                          {idx < shots.length - 1 && (
                            <div style={{ width: 1, flex: 1, minHeight: 12, marginTop: 4, background: 'var(--border)' }} />
                          )}
                        </div>
                        {/* Content */}
                        <div style={{ flex: 1, minWidth: 0 }}>
                          {isPending ? (
                            <p style={{ fontSize: 14, color: 'var(--text-tertiary)', fontStyle: 'italic', lineHeight: 1.5, marginBottom: 4 }}>
                              等待图片生成阶段完成…
                            </p>
                          ) : (
                            <p style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', lineHeight: 1.5, marginBottom: 4 }}>
                              {s.narration || s.dialogue || '(无旁白/对白)'}
                            </p>
                          )}
                          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginTop: 8 }}>
                            {!isPending && (
                              <>
                              <span style={{ fontSize: 11, color: 'var(--text-tertiary)', display: 'flex', alignItems: 'center', gap: 4 }}>
                                🎥 {s.camera_movement}
                              </span>
                              <span style={{ fontSize: 11, color: 'var(--text-tertiary)', display: 'flex', alignItems: 'center', gap: 4 }}>
                                ⏱ {s.duration_sec}s
                              </span>
                              </>
                            )}
                            <span style={{
                              fontSize: 10, fontWeight: 600, padding: '2px 10px', borderRadius: 100,
                              ...(isPending
                                ? { background: 'var(--surface)', color: 'var(--text-tertiary)' }
                                : s.status === 'done'
                                ? { background: 'var(--success-bg)', color: 'var(--success)' }
                                : { background: 'var(--surface-alt)', color: 'var(--text-tertiary)' }
                              ),
                            }}>{isPending ? '未就绪' : s.status}</span>
                            {hasPrompt && (
                              <span style={{ fontSize: 11, color: 'var(--text-tertiary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 200 }}>
                                📝 {s.image_prompt.slice(0, 40)}…
                              </span>
                            )}
                          </div>
                        </div>
                        {/* Regenerate video button */}
                        {hasPrompt && (
                          <button
                            onClick={() => handleShotRegen(s.id, s.shot_num)}
                            title={`重新生成镜头 ${s.shot_num} 的视频`}
                            style={{
                              alignSelf: 'center', flexShrink: 0,
                              width: 34, height: 34, borderRadius: 10,
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
                            <RefreshCw size={15} />
                          </button>
                        )}
                      </div>
                    )})}
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
      {/* Toast */}
      {toast && <Toast msg={toast.msg} type={toast.type} onClose={() => setToast(null)} />}
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
