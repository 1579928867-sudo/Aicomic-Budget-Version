import { useState, useRef, useEffect } from 'react';
import { Send, Loader2, Bot, User, Sparkles, Paperclip, CheckCircle2, Play, SkipForward, ChevronDown } from 'lucide-react';
import { chat, pipeline, settings } from '../api';
import { useAppStore } from '../stores/app';

interface EnvStatus {
  llm_ready: boolean; llm_detail: string;
  cookie_ready: boolean; cookie_detail: string;
  all_ready: boolean; novel_count: number; chapter_count: number;
  next_step: string;
}

interface PhaseInfo {
  phase?: string; label?: string; description?: string;
  has_next?: boolean; next_phase?: string; mode?: string;
  summary?: Record<string, any>;
  estimate?: { text: string; detail?: string };
}

interface Message {
  id: number;
  role: 'user' | 'assistant' | 'system';
  content: string;
  taskId?: string;
  phase?: PhaseInfo;
  phaseStatus?: 'starting' | 'running' | 'complete';
}

function buildWelcome(env: EnvStatus | null): string {
  const checking = !env;
  const check = (ok: boolean) => checking ? '⏳' : (ok ? '✅' : '❌');

  let msg = '你好！我是 AI漫剧助手 🎬\n\n';
  msg += '📋 **环境检测**：\n';
  msg += `${check(env?.llm_ready ?? false)} LLM API Key：${env?.llm_detail || '检测中…'}\n`;
  msg += `${check(env?.cookie_ready ?? false)} 豆包 Cookie：${env?.cookie_detail || '检测中…'}\n`;

  if (env?.novel_count) {
    msg += `\n📚 已导入 ${env.novel_count} 本小说，${env.chapter_count} 个章节`;
  }

  if (checking) {
    msg += '\n⏳ 正在检测环境配置…';
  } else if (env.all_ready) {
    msg += '\n🎉 环境就绪！上传小说后说「生成第X章」即可开始制作漫剧。';
    msg += '\n\n---\n\n';
    msg += '💡 **温馨提醒**：\n';
    msg += '• 视频额度：Mini 每天 5 次，Fast 每天 3 次，可在输入框上方切换模型\n';
    msg += '• AI 生成素材像抽卡一样，质量和审核结果不稳定，请留意额度消耗\n';
    msg += '• 如果生成效果不理想，试试对我说「重新生成角色图 / 镜头N」或微调提示词再试';
  } else {
    msg += `\n\n⚡ **下一步**：${env.next_step}`;
  }

  return msg;
}

export function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([
    { id: 0, role: 'assistant', content: buildWelcome(null) },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const autoContinueRef = useRef<Set<string>>(new Set()); // taskIds to auto-continue
  const esRef = useRef<EventSource | null>(null);
  const chapterId = useAppStore(s => s.selectedChapterId);
  const novelId = useAppStore(s => s.selectedNovelId);
  const videoModel = useAppStore(s => s.videoModel);
  const setVideoModel = useAppStore(s => s.setVideoModel);
  const [modelOpen, setModelOpen] = useState(false);

  // Load env status + model preference on mount
  useEffect(() => {
    chat.status().then(s => {
      setMessages(prev => prev.map(m => m.id === 0 ? { ...m, content: buildWelcome(s) } : m));
    }).catch(() => {
      const fallback: EnvStatus = {
        llm_ready: false, llm_detail: '无法检测',
        cookie_ready: false, cookie_detail: '无法检测',
        all_ready: false, novel_count: 0, chapter_count: 0,
        next_step: '请确保服务器已启动，然后刷新页面',
      };
      setMessages(prev => prev.map(m => m.id === 0 ? { ...m, content: buildWelcome(fallback) } : m));
    });
    settings.videoModel().then(r => setVideoModel(r.model as 'mini' | 'fast')).catch(() => {});
  }, []);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  // Cleanup SSE on unmount
  useEffect(() => () => esRef.current?.close(), []);

  const startSSE = (taskId: string, msgId: number) => {
    esRef.current?.close();
    const es = new EventSource(`/api/events/${taskId}`);

    es.addEventListener('phase_start', (e: MessageEvent) => {
      try {
        const d = JSON.parse(e.data);
        setMessages(prev => prev.map(m =>
          m.id === msgId ? {
            ...m,
            phase: { ...m.phase, ...d, mode: d.mode },
            phaseStatus: 'running',
            content: `${m.content}\n\n🔹 ${d.label}: ${d.description}`,
          } : m
        ));
      } catch {}
    });

    es.addEventListener('phase_complete', (e: MessageEvent) => {
      try {
        const d = JSON.parse(e.data);
        const isAuto = d.mode === 'auto';
        const summaryLines = d.summary ? Object.entries(d.summary)
          .map(([k, v]) => `  • ${k}: ${v}`).join('\n') : '';
        const warnLine = d.warning ? `\n\n⚠️ ${d.warning}` : '';
        setMessages(prev => prev.map(m =>
          m.id === msgId ? {
            ...m,
            phase: { ...m.phase, ...d, has_next: d.has_next, next_phase: d.next_phase },
            phaseStatus: 'complete',
            content: `${m.content}\n\n✅ ${d.label}完成！\n${summaryLines}${warnLine}`,
          } : m
        ));
        // Auto-continue if in auto mode or user set auto-continue flag
        if (isAuto || autoContinueRef.current.has(taskId)) {
          if (d.has_next && d.next_phase) {
            setTimeout(() => {
              pipeline.continue(taskId).catch(() => {});
            }, 500);
          }
        }
      } catch {}
    });

    es.addEventListener('budget_checkpoint', (e: MessageEvent) => {
      try {
        const d = JSON.parse(e.data);
        const summaryLines = d.summary ? Object.entries(d.summary)
          .map(([k, v]) => `  • ${k}: ${v}`).join('\n') : '';
        const clipInfo = d.clips_done && d.clips_total
          ? `\n\n🎞️ 本批次: ${d.clips_done}/${d.clips_total} 个分镜视频`
          : '';
        const remainInfo = d.remaining > 0
          ? `\n📋 剩余: ${d.remaining} 个镜头（继续将消耗${d.budget_per_run}次额度/批次）`
          : '';
        const budgetPrefix = d.message
          ? `\n\n⏸ ${d.message}`
          : `\n\n⏸ 视频额度检查点 — 本批次已完成${clipInfo}${remainInfo}`;
        setMessages(prev => prev.map(m =>
          m.id === msgId ? {
            ...m,
            phase: {
              ...m.phase,
              phase: d.phase,
              label: d.label + '（额度检查点）',
              has_next: d.remaining > 0,
              next_phase: d.phase,
              mode: d.mode,
            },
            phaseStatus: 'complete',
            content: `${m.content}${budgetPrefix}\n\n${summaryLines}`,
          } : m
        ));
      } catch {}
    });

    es.addEventListener('progress', (e: MessageEvent) => {
      try {
        const d = JSON.parse(e.data);
        setMessages(prev => prev.map(m =>
          m.id === msgId
            ? { ...m, content: `${m.content}\n⏳ ${d.step || ''}: ${d.message || ''}` }
            : m
        ));
      } catch {}
    });

    es.addEventListener('complete', (e: MessageEvent) => {
      try {
        const d = JSON.parse(e.data);
        let statusLine = '';
        if (d.message) {
          // Agent tasks (video-composer, image-generator regen, etc.)
          statusLine = `\n\n${d.message}`;
        } else if (d.skipped) {
          statusLine = `\n\n⏭ 已完成（无需重复运行）`;
        } else if (d.audit) {
          // Pipeline complete
          const summaryLines = d.audit.summary ? Object.entries(d.audit.summary)
            .map(([k, v]) => `  • ${k}: ${v}`).join('\n') : '';
          const warnLine = d.warning ? `\n\n⚠️ ${d.warning}` : '';
          statusLine = `\n\n🎉 全部完成！\n${summaryLines}${warnLine}`;
        } else {
          statusLine = `\n\n✅ 任务完成！`;
        }
        setMessages(prev => prev.map(m =>
          m.id === msgId
            ? { ...m, content: m.content + statusLine, phaseStatus: 'complete' }
            : m
        ));
      } catch {}
      es.close();
      esRef.current = null;
    });

    es.addEventListener('error', (e: MessageEvent) => {
      try {
        if (e.data) {
          const d = JSON.parse(e.data);
          const friendly = d.error || '未知错误';
          setMessages(prev => prev.map(m =>
            m.id === msgId
              ? { ...m, content: m.content + `\n\n---\n\n${friendly}`, phaseStatus: undefined }
              : m
          ));
        }
      } catch {}
      es.close();
      esRef.current = null;
    });

    esRef.current = es;
  };

  const handleContinue = async (msg: Message) => {
    if (!msg.taskId || !msg.phase?.next_phase) return;
    try {
      await pipeline.continue(msg.taskId);
      setMessages(prev => prev.map(m =>
        m.id === msg.id
          ? { ...m, content: m.content, phaseStatus: 'running' }
          : m
      ));
    } catch (e: any) {
      setMessages(prev => prev.map(m =>
        m.id === msg.id
          ? { ...m, content: m.content + `\n\n❌ 继续失败: ${e.message}` }
          : m
      ));
    }
  };

  const handleContinueAuto = async (msg: Message) => {
    if (!msg.taskId) return;
    // Set auto-continue flag - SSE handler will auto-call continue on each phase_complete
    autoContinueRef.current.add(msg.taskId);
    setMessages(prev => prev.map(m =>
      m.id === msg.id
        ? { ...m, phase: { ...m.phase, mode: 'auto' }, phaseStatus: 'running' }
        : m
    ));
    handleContinue(msg);
  };

  const handleSend = async () => {
    if (!input.trim() || loading) return;
    const msgBody = input.trim();
    setInput('');
    const userMsgId = Date.now();
    setMessages(prev => [...prev, { id: userMsgId, role: 'user', content: msgBody }]);
    setLoading(true);
    try {
      const res = await chat.send({ message: msgBody, chapter_id: chapterId ?? undefined, novel_id: novelId ?? undefined });
      const replyId = Date.now() + 1;
      const replyMsg: Message = { id: replyId, role: 'assistant', content: res.reply, taskId: res.task_id ?? undefined };
      setMessages(prev => [...prev, replyMsg]);
      if (res.task_id) {
        startSSE(res.task_id, replyId);
      }
    } catch (e: any) {
      setMessages(prev => [...prev, { id: Date.now() + 1, role: 'assistant', content: `抱歉，出错了: ${e.message}` }]);
    } finally { setLoading(false); }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', maxWidth: 780, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: 24, flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ width: 40, height: 40, borderRadius: 12, background: 'var(--accent)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Sparkles size={20} />
          </div>
          <div>
            <h1 style={{ fontSize: 20, fontWeight: 700, color: 'var(--text)', lineHeight: 1.3 }}>AI漫剧助手</h1>
            <p style={{ fontSize: 13, color: 'var(--text-tertiary)', marginTop: 2 }}>智能对话 · 意图识别 · 一键生成</p>
          </div>
          {chapterId && (
            <span style={{ marginLeft: 'auto', padding: '4px 14px', borderRadius: 100, background: 'var(--accent-light)', color: 'var(--accent)', fontSize: 12, fontWeight: 600, border: '1px solid var(--accent-border)' }}>
              当前章节 #{chapterId}
            </span>
          )}
        </div>
      </div>

      {/* Messages — flex:1 fills available space, messages overflow scroll internally */}
      <div style={{ flex: 1, overflow: 'auto', paddingBottom: 12, display: 'flex', flexDirection: 'column', gap: 20, minHeight: 0 }}>
        {messages.map(msg => (
          <div key={msg.id} style={{ display: 'flex', gap: 12, justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
            {msg.role === 'assistant' && (
              <div style={{ width: 34, height: 34, borderRadius: 10, background: 'var(--accent-light)', border: '1px solid var(--accent-border)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, marginTop: 2 }}>
                <Bot size={17} style={{ color: 'var(--accent)' }} />
              </div>
            )}
            <div style={{
              maxWidth: '72%', borderRadius: 16, padding: '14px 18px',
              fontSize: 14, lineHeight: 1.7, whiteSpace: 'pre-wrap',
              ...(msg.role === 'user' ? {
                background: 'var(--accent)', color: '#fff', borderBottomRightRadius: 6,
              } : {
                background: 'var(--surface)', color: 'var(--text-secondary)',
                border: '1px solid var(--border)', borderBottomLeftRadius: 6,
              }),
            }}>
              {msg.content}
              {/* Phase progress card */}
              {msg.phase && msg.phaseStatus && (
                <div style={{
                  marginTop: 12, padding: '12px 16px', borderRadius: 10,
                  background: msg.phaseStatus === 'complete'
                    ? 'var(--success-bg)'
                    : msg.phaseStatus === 'running'
                    ? '#E8F2FD'
                    : 'var(--surface-alt)',
                  border: `1px solid ${msg.phaseStatus === 'complete'
                    ? 'var(--success)40'
                    : msg.phaseStatus === 'running'
                    ? '#B8D8F0'
                    : 'var(--border)'}`,
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <CheckCircle2 size={14} style={{
                      color: msg.phaseStatus === 'complete' ? 'var(--success)' : msg.phaseStatus === 'running' ? '#3B82C0' : 'var(--text-tertiary)',
                      ...(msg.phaseStatus === 'running' ? { animation: 'spin 0.7s linear infinite' } : {}),
                    }} />
                    <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>
                      {msg.phase.label || msg.phase.phase}
                    </span>
                    <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                      {msg.phaseStatus === 'running' ? '进行中…' : msg.phaseStatus === 'complete' ? '已完成' : ''}
                    </span>
                  </div>
                  {msg.phase.description && (
                    <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 4 }}>
                      {msg.phase.description}
                    </div>
                  )}
                  {msg.phaseStatus === 'running' && msg.phase.estimate && (
                    <div style={{ fontSize: 11, color: '#3B82C0', marginTop: 4, fontStyle: 'italic' }}>
                      ⏱ 预计耗时: {msg.phase.estimate.text}
                      {msg.phase.estimate.detail && (
                        <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 2 }}>
                          💡 {msg.phase.estimate.detail}
                        </div>
                      )}
                    </div>
                  )}
                  {/* Confirm buttons — only in interactive mode when phase is complete and has next */}
                  {msg.phaseStatus === 'complete' && msg.phase.has_next && msg.phase.mode !== 'auto' && (
                    <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                      <button
                        onClick={() => handleContinue(msg)}
                        style={{
                          display: 'inline-flex', alignItems: 'center', gap: 6,
                          padding: '7px 16px', borderRadius: 8, border: 'none',
                          background: 'var(--accent)', color: '#fff',
                          fontFamily: 'inherit', fontSize: 12, fontWeight: 600,
                          cursor: 'pointer', transition: 'all 0.15s',
                        }}
                        onMouseEnter={e => { e.currentTarget.style.background = 'var(--accent-hover)'; }}
                        onMouseLeave={e => { e.currentTarget.style.background = 'var(--accent)'; }}
                      >
                        <Play size={13} /> 继续下一步
                      </button>
                      <button
                        onClick={() => handleContinueAuto(msg)}
                        style={{
                          display: 'inline-flex', alignItems: 'center', gap: 6,
                          padding: '7px 16px', borderRadius: 8,
                          border: '1px solid var(--border)', background: 'var(--surface)',
                          color: 'var(--text-secondary)', fontFamily: 'inherit',
                          fontSize: 12, fontWeight: 500, cursor: 'pointer',
                          transition: 'all 0.15s',
                        }}
                        onMouseEnter={e => { e.currentTarget.style.background = 'var(--surface-hover)'; }}
                        onMouseLeave={e => { e.currentTarget.style.background = 'var(--surface)'; }}
                      >
                        <SkipForward size={13} /> 全部自动完成
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
            {msg.role === 'user' && (
              <div style={{ width: 34, height: 34, borderRadius: 10, background: 'var(--surface-alt)', border: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, marginTop: 2 }}>
                <User size={17} style={{ color: 'var(--text-secondary)' }} />
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div style={{ display: 'flex', gap: 12 }}>
            <div style={{ width: 34, height: 34, borderRadius: 10, background: 'var(--accent-light)', border: '1px solid var(--accent-border)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Bot size={17} style={{ color: 'var(--accent)' }} />
            </div>
            <div style={{ padding: '14px 18px', borderRadius: 16, borderBottomLeftRadius: 6, background: 'var(--surface)', border: '1px solid var(--border)' }}>
              <Loader2 size={18} style={{ color: 'var(--accent)', animation: 'spin 0.7s linear infinite' }} />
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {/* Input — sits just below messages, not pushed to very bottom */}
      <div style={{ paddingTop: 16, flexShrink: 0 }}>
        {/* ── Model selector: collapsible dropdown ── */}
        <div style={{ marginBottom: 8, position: 'relative' }}>
          <button
            onClick={() => setModelOpen(!modelOpen)}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '5px 12px', borderRadius: 8,
              border: '1px solid var(--border)', background: 'var(--surface)',
              color: 'var(--text-secondary)', fontFamily: 'inherit',
              fontSize: 12, fontWeight: 500, cursor: 'pointer',
              transition: 'all 0.15s',
            }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent)'; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; }}
          >
            🎬 视频模型：{videoModel === 'fast' ? 'Seedance 2.0 Fast ⚡' : 'Seedance 2.0 Mini'}
            <ChevronDown size={12} style={{ transform: modelOpen ? 'rotate(180deg)' : undefined, transition: 'transform 0.15s' }} />
          </button>
          {modelOpen && (
            <>
              <div style={{ position: 'fixed', inset: 0, zIndex: 9 }} onClick={() => setModelOpen(false)} />
              <div style={{
                position: 'absolute', top: '100%', left: 0, zIndex: 10,
                marginTop: 4, borderRadius: 10, background: 'var(--surface)',
                border: '1px solid var(--border)', boxShadow: 'var(--shadow-lg)',
                overflow: 'hidden', minWidth: 200,
              }}>
                {(['mini', 'fast'] as const).map(m => (
                  <button
                    key={m}
                    onClick={() => { setVideoModel(m); setModelOpen(false); settings.saveVideoModel(m).catch(() => {}); }}
                    style={{
                      width: '100%', textAlign: 'left', padding: '9px 16px',
                      border: 'none', background: videoModel === m ? 'var(--accent-light)' : 'transparent',
                      color: videoModel === m ? 'var(--accent)' : 'var(--text-secondary)',
                      fontFamily: 'inherit', fontSize: 12, fontWeight: videoModel === m ? 600 : 400,
                      cursor: 'pointer', transition: 'all 0.1s',
                      display: 'flex', alignItems: 'center', gap: 8,
                    }}
                    onMouseEnter={e => { if (videoModel !== m) e.currentTarget.style.background = 'var(--surface-hover)'; }}
                    onMouseLeave={e => { if (videoModel !== m) e.currentTarget.style.background = 'transparent'; }}
                  >
                    <span style={{ color: videoModel === m ? 'var(--accent)' : 'var(--text-tertiary)', fontSize: 14 }}>
                      {videoModel === m ? '●' : '○'}
                    </span>
                    {m === 'fast' ? 'Seedance 2.0 Fast ⚡' : 'Seedance 2.0 Mini'}
                    {m === 'mini' && <span style={{ fontSize: 10, color: 'var(--text-tertiary)', marginLeft: 'auto' }}>默认</span>}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file" accept=".txt,.docx,.pdf"
            style={{ display: 'none' }}
            onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              setUploading(true);
              const fd = new FormData();
              fd.append('file', file);
              try {
                const res = await fetch('/api/upload', { method: 'POST', body: fd });
                const data = await res.json();
                setMessages(prev => [...prev, {
                  id: Date.now(),
                  role: 'assistant',
                  content: `✅ 上传成功！\n\n📖 小说：${data.title}\n📄 章节：第${data.chapter_num}章\n📝 字数：${data.char_count}\n\n你现在可以在素材库里看到它了。`,
                }]);
              } catch (e: any) {
                setMessages(prev => [...prev, {
                  id: Date.now(),
                  role: 'assistant',
                  content: `❌ 上传失败：${e.message}`,
                }]);
              } finally {
                setUploading(false);
                // 重置 input 以允许重复上传同一文件
                e.target.value = '';
              }
            }}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            style={{
              width: 42, height: 42, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center',
              border: '1px solid var(--border)', background: 'var(--surface)',
              color: 'var(--text-tertiary)', cursor: uploading ? 'not-allowed' : 'pointer',
              opacity: uploading ? 0.5 : 1, transition: 'all 0.15s',
            }}
            onMouseEnter={e => { if (!uploading) { e.currentTarget.style.background = 'var(--surface-hover)'; e.currentTarget.style.color = 'var(--text)'; }}}
            onMouseLeave={e => { if (!uploading) { e.currentTarget.style.background = 'var(--surface)'; e.currentTarget.style.color = 'var(--text-tertiary)'; }}}
            title="上传小说文件 (.txt .docx .pdf)"
          >
            {uploading ? <Loader2 size={18} style={{ animation: 'spin 0.7s linear infinite' }} /> : <Paperclip size={18} />}
          </button>
          <div style={{ flex: 1, position: 'relative' }}>
            <input
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入消息，Enter 发送…"
              style={{
                width: '100%', padding: '11px 48px 11px 16px',
                borderRadius: 12, border: '1px solid var(--border)',
                background: 'var(--surface)', color: 'var(--text)',
                fontFamily: 'inherit', fontSize: 14,
                outline: 'none', transition: 'border-color 0.15s, box-shadow 0.15s',
              }}
              onFocus={e => { e.currentTarget.style.borderColor = 'var(--accent)'; e.currentTarget.style.boxShadow = '0 0 0 3px var(--accent-light)'; }}
              onBlur={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.boxShadow = 'none'; }}
            />
            <span style={{ position: 'absolute', right: 14, top: '50%', transform: 'translateY(-50%)', fontSize: 10, color: 'var(--text-tertiary)', pointerEvents: 'none' }}>
              Enter ↵
            </span>
          </div>
          <button
            onClick={handleSend}
            disabled={!input.trim() || loading}
            style={{
              width: 42, height: 42, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center',
              border: 'none', background: 'var(--accent)', color: '#fff',
              cursor: !input.trim() || loading ? 'not-allowed' : 'pointer',
              opacity: !input.trim() || loading ? 0.4 : 1,
              transition: 'all 0.15s',
            }}
            onMouseEnter={e => { if (!(!input.trim() || loading)) e.currentTarget.style.background = 'var(--accent-hover)'; }}
            onMouseLeave={e => { if (!(!input.trim() || loading)) e.currentTarget.style.background = 'var(--accent)'; }}
          >
            <Send size={18} />
          </button>
        </div>
      </div>
    </div>
  );
}
