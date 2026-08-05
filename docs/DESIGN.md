# DESIGN.md — AI漫剧 Web 前端

> 一张宣纸上的智能工具台：温暖克制，让创作素材自己说话。

## 1. Visual Theme & Atmosphere

**Style**: 中文温暖极简 (Chinese Warm Minimal)
**Keywords**: 明亮、温暖、留白、克制、呼吸、书卷气、精致
**Tone**: 安静优雅的工具箱 — NOT 炫酷黑暗科技风、NOT 花哨娱乐
**Feel**: 午后阳光透过百叶窗洒在白色台面上，你面前是一叠精心装裱的画稿

**Interaction Tier**: L1 精致静态
**Dependencies**: CSS only (no GSAP, no heavy libs)

---

## 2. Color Palette & Roles

```css
:root {
  /* Backgrounds */
  --bg: #FAFAF8;                          /* 页面背景 — 微暖白 */
  --surface: #FFFFFF;                     /* 卡片/容器 */
  --surface-alt: #F5F3F0;                 /* 交替 section / 侧边栏 */
  --surface-hover: #EEECE8;              /* 悬停态表面 */

  /* Borders */
  --border: #E6E3DE;                      /* 默认边框 — 暖灰 */
  --border-hover: #C5C0B8;               /* 悬停边框 */

  /* Text */
  --text: #1C1C1C;                        /* 标题、重要文字 */
  --text-secondary: #5C5A57;              /* 正文、描述 */
  --text-tertiary: #9C9994;               /* 标签、辅助信息 */

  /* Accent — 暖橙赭石系 */
  --accent: #D4794A;                      /* CTA、链接、活跃态 */
  --accent-hover: #C0683A;               /* 强调色 hover */
  --accent-light: #FDF0E8;               /* 强调色浅底 */
  --accent-border: #F0D0B8;              /* 强调色边框 */

  /* RGB variants for rgba() */
  --bg-rgb: 250, 250, 248;
  --surface-rgb: 255, 255, 255;
  --accent-rgb: 212, 121, 74;
  --text-rgb: 28, 28, 28;

  /* Semantic */
  --success: #5B8C5A;
  --success-bg: #EDF5EC;
  --error: #C45C4C;
  --error-bg: #FDF0ED;
  --warning: #D49B4A;
  --warning-bg: #FDF5E8;

  /* Shadows — 极轻克制 */
  --shadow-sm: 0 1px 3px rgba(0,0,0,0.04);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.06);
  --shadow-lg: 0 8px 24px rgba(0,0,0,0.08);
}
```

**Color Rules:**
- 所有颜色通过 CSS 变量引用，**禁止硬编码 hex/rgb**
- 同一区域最多出现一种强调色
- 卡片仅用 `--surface` + `--border`，不要给卡片加彩色边框
- 强调色 (`--accent`) 仅用于按钮、链接、活跃态指示器

---

## 3. Typography Rules

**Font Stack:**
```css
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+SC:wght@400;500;600;700&display=swap');
```

| Role | Font | Size | Weight | Line Height | Letter Spacing |
|------|------|------|--------|-------------|----------------|
| Page Title H1 | Noto Sans SC | 24px | 700 | 1.4 | — |
| Section H2 | Noto Sans SC | 18px | 600 | 1.4 | — |
| Card Title | Noto Sans SC | 14px | 600 | 1.5 | — |
| Body | Inter, Noto Sans SC | 14px | 400 | 1.7 | 0.01em |
| Body Small / Label | Inter, Noto Sans SC | 12px | 500 | 1.5 | 0.02em |
| Mono/Code | JetBrains Mono, monospace | 13px | 400 | 1.6 | — |
| Tiny / Badge | Inter | 11px | 600 | 1.3 | 0.03em |

**Typography Rules:**
- 中文用 Noto Sans SC，英文/数字用 Inter，`font-family: 'Noto Sans SC', 'Inter', -apple-system, sans-serif`
- 正文行高 ≥ 1.7，正文最小字号 14px
- **NEVER use**: 花体/手写体/Comic Sans/Impact，不用 Arial 兜底
- 标题不加渐变、不加投影（克制风格）

**Text Decoration:**
- Hero/Page 标题: 无渐变、无投影，用字号和留白建立层次
- 卡片标题: 纯色 `--text`
- 强调文字: 可用 `--accent` 着色，不加粗

---

## 4. Component Stylings

### Buttons

```css
/* Primary Button */
.btn-primary {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 8px 18px;
  border-radius: 10px; border: none;
  background: var(--accent); color: #FFFFFF;
  font-family: inherit; font-size: 13px; font-weight: 600;
  cursor: pointer; transition: all 0.2s ease;
}
.btn-primary:hover { background: var(--accent-hover); transform: translateY(-1px); box-shadow: var(--shadow-md); }
.btn-primary:active { transform: translateY(0); box-shadow: var(--shadow-sm); }
.btn-primary:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.btn-primary:disabled { opacity: 0.35; cursor: not-allowed; transform: none; box-shadow: none; }

/* Secondary Button */
.btn-secondary {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 8px 18px;
  border-radius: 10px;
  background: var(--surface); color: var(--text-secondary);
  border: 1px solid var(--border);
  font-family: inherit; font-size: 13px; font-weight: 500;
  cursor: pointer; transition: all 0.2s ease;
}
.btn-secondary:hover { background: var(--surface-hover); border-color: var(--border-hover); color: var(--text); }
.btn-secondary:active { background: var(--surface-alt); }
.btn-secondary:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.btn-secondary:disabled { opacity: 0.35; cursor: not-allowed; }

/* Ghost Button (icon only) */
.btn-ghost {
  display: inline-flex; align-items: center; justify-content: center;
  width: 36px; height: 36px; border-radius: 8px;
  background: transparent; color: var(--text-tertiary);
  border: none; cursor: pointer; transition: all 0.15s ease;
}
.btn-ghost:hover { background: var(--surface-hover); color: var(--text); }
.btn-ghost:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
```

### Cards

```css
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 20px;
  transition: box-shadow 0.25s ease, border-color 0.25s ease;
}
.card:hover {
  box-shadow: var(--shadow-md);
  border-color: var(--border-hover);
}
.card.interactive { cursor: pointer; }
.card.interactive:hover { box-shadow: var(--shadow-lg); }
```

### Navigation (Sidebar)

```css
.sidebar {
  width: 240px; min-height: 100vh;
  background: var(--surface-alt);
  border-right: 1px solid var(--border);
  padding: 24px 16px;
  display: flex; flex-direction: column; gap: 4px;
}
.nav-item {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 14px; border-radius: 10px;
  font-size: 14px; font-weight: 500;
  color: var(--text-secondary);
  background: transparent; border: none;
  cursor: pointer; transition: all 0.15s ease;
  text-decoration: none;
}
.nav-item:hover { background: var(--surface-hover); color: var(--text); }
.nav-item.active {
  background: var(--accent-light); color: var(--accent);
  border: 1px solid var(--accent-border);
}
```

### Inputs

```css
.input {
  width: 100%; padding: 10px 14px;
  background: var(--surface); color: var(--text);
  border: 1px solid var(--border); border-radius: 10px;
  font-family: inherit; font-size: 14px;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.input::placeholder { color: var(--text-tertiary); }
.input:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-light); }
.input:disabled { opacity: 0.5; background: var(--surface-alt); cursor: not-allowed; }
```

### Tags / Badges

```css
.badge {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 2px 10px; border-radius: 100px;
  font-size: 11px; font-weight: 600; letter-spacing: 0.03em;
  background: var(--surface-alt); color: var(--text-secondary);
  border: 1px solid var(--border);
}
.badge-success { background: var(--success-bg); color: var(--success); border-color: transparent; }
.badge-error { background: var(--error-bg); color: var(--error); border-color: transparent; }
.badge-warning { background: var(--warning-bg); color: var(--warning); border-color: transparent; }
.badge-accent { background: var(--accent-light); color: var(--accent); border-color: var(--accent-border); }
```

### Tabs

```css
.tab-bar {
  display: flex; gap: 4px;
  background: var(--surface-alt); border-radius: 12px; padding: 4px;
}
.tab-item {
  flex: 1; padding: 6px 16px;
  border-radius: 9px; border: none;
  background: transparent; color: var(--text-tertiary);
  font-family: inherit; font-size: 13px; font-weight: 500;
  cursor: pointer; transition: all 0.15s ease;
}
.tab-item:hover { color: var(--text-secondary); }
.tab-item.active { background: var(--surface); color: var(--text); box-shadow: var(--shadow-sm); }
```

---

## 5. Layout Principles

**Container:**
- Max content width: 980px (narrow text areas: 680px)
- Page padding: 32px (desktop), 20px (mobile)
- Sidebar: 240px fixed

**Spacing Scale:**
- Section padding: 28px
- Component gap (vertical/horizontal between cards): 16px
- Card internal padding: 20px
- Sidebar-service gap: 0 (sidebar border is the separator, content starts immediately)
- **Key: main area has generous 40px padding on all sides**

**Grid:**
```css
/* Character/Scene cards */
.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px; }
/* Shot list single column */
.shot-list { display: flex; flex-direction: column; gap: 10px; }
```

**Layout Structure:**
```
┌──────────────┬────────────────────────────────────────┐
│   Sidebar    │   Header: Page Title + Controls         │
│   240px      ├────────────────────────────────────────┤
│              │                                        │
│   Nav Items  │   Content Area                         │
│              │   padding: 40px                        │
│              │   gap: 24px between sections            │
│              │                                        │
│   Footer     │                                        │
└──────────────┴────────────────────────────────────────┘
```

---

## 6. Depth & Elevation

| Level | Treatment | Use |
|-------|-----------|-----|
| Flat | `border: 1px solid var(--border)` only | 列表项、消息气泡 |
| Subtle | `box-shadow: var(--shadow-sm)` | 普通卡片 |
| Elevated | `box-shadow: var(--shadow-md)` | 悬停卡片、下拉菜单 |
| High | `box-shadow: var(--shadow-lg)` | 弹窗/Modal |

**Rules:**
- 不使用 backdrop-filter blur（L1 克制风格）
- 不使用 box-shadow glow 效果
- 卡片默认 Flat + border，hover 才 Elevated

---

## 7. Animation & Interaction

**Motion Philosophy**: 安静优雅，只用 opacity 和 transform。工具型应用不需要炫技。

**Tier**: L1 — 精致静态

### Entrance Animation
```css
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}
.reveal {
  opacity: 0;
  transition: opacity 0.5s cubic-bezier(0.16, 1, 0.3, 1),
              transform 0.5s cubic-bezier(0.16, 1, 0.3, 1);
}
.reveal.in-view { opacity: 1; transform: translateY(0); }
```

### Hover & Focus States
```css
/* All interactive elements must have: */
/* - hover: visual indicator (bg change / border change / slight lift) */
/* - focus-visible: 2px outline, offset 2px */
/* - active: pressed state (scale down or darker) */
/* Transition duration: 0.15s-0.25s, ease or cubic-bezier(0.16,1,0.3,1) */
```

### Loading States
```css
.loading-spinner {
  width: 24px; height: 24px;
  border: 2.5px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.loading-skeleton {
  background: linear-gradient(90deg, var(--surface-alt) 25%, var(--surface-hover) 50%, var(--surface-alt) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 8px;
}
@keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
```

### Reduced Motion
```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

## 8. Do's and Don'ts

### Do
- ✅ 大量留白，让内容呼吸
- ✅ 橙色暖调仅用于按钮、链接、活跃指示器
- ✅ 间距统一为 4 的倍数（4/8/12/16/20/24/28/32/40）
- ✅ 每个交互元素必须有 hover + focus-visible 态
- ✅ 图片预览使用 Modal 遮罩，深色半透明盖背景
- ✅ 消息气泡区分 user（暖色实心）和 assistant（浅色边框）

### Don't
- ❌ 禁止使用暗色背景（`#09090b`, `#1a1a2e` 等）
- ❌ 禁止 backdrop-filter: blur() 毛玻璃效果
- ❌ 禁止 box-shadow glow / neon 发光
- ❌ 禁止渐变色文字（heading 纯色即可）
- ❌ 禁止 emoji 作为图标（用 lucide-react 图标）
- ❌ 禁止纯黑/纯白文字（用 `--text` / `--text-secondary`）
- ❌ 禁止元素紧贴在一起 —— 相邻块之间最少 16px
- ❌ 禁止 API Key 明文完整展示在前端
- ❌ 禁止在代码中硬编码 hex 颜色值

---

## 9. Responsive Behavior

**Breakpoints:**
| Name | Width | Key Changes |
|------|-------|-------------|
| Desktop | > 1024px | 侧边栏 240px + 内容区 flex-1 |
| Tablet | 768-1024px | 侧边栏折叠为图标模式 56px |
| Mobile | < 768px | 侧边栏变底部 Tab Bar，内容区全宽 |

**Touch Targets:** minimum 44×44px for all interactive elements
**Collapsing Strategy:** 侧边栏在 tablet 下折叠为仅图标，mobile 下移到底部
