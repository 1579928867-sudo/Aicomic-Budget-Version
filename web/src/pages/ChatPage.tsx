import { useState, useRef, useEffect } from 'react';
import { Send, Loader2, Bot, User, Sparkles, Paperclip } from 'lucide-react';
import { chat } from '../api';
import { useAppStore } from '../stores/app';

interface Message {
  id: number;
  role: 'user' | 'assistant';
  content: string;
}

export function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([
    { id: 0, role: 'assistant', content:  '你好！我是 AI漫剧助手 🎬\n\n我可以帮你：\n• 上传小说文件（.txt / .docx / .pdf）自动入库\n• 在素材库浏览角色、场景、分镜\n• 在视频页播放和下载成品视频\n• 在设置页配置你自己的 LLM API Key\n• 在 Cookie 页配置豆包账号\n\n💡 开始方式：\n1. 先到「豆包Cookie」页配置你的豆包账号\n2. 再到「系统设置」页填入你的 LLM API Key\n3. 在素材库左侧上传小说文件，即可开始生成\n\n有什么我可以帮你的？' },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const chapterId = useAppStore(s => s.selectedChapterId);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;
    const msg = input.trim();
    setInput('');
    setMessages(prev => [...prev, { id: Date.now(), role: 'user', content: msg }]);
    setLoading(true);
    try {
      const res = await chat.send({ message: msg, chapter_id: chapterId ?? undefined });
      setMessages(prev => [...prev, { id: Date.now() + 1, role: 'assistant', content: res.reply }]);
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
