# DESIGN.md — AI漫剧 Web 前端 v2

> 宣纸上浮着一颗旋转的星球：温暖克制遇见未来科技。

## 1. Visual Theme & Atmosphere

**Style**: 温暖科技 (Warm Tech) — 中文优雅 × 科技亮点融合
**Keywords**: 明亮、温暖、3D球体、轨道、透明深度、纹理、高级感
**Tone**: 安静优雅的工具箱，封面页像进入一个微缩宇宙 — NOT 花哨游戏感、NOT 纯黑科技风
**Feel**: 午后的阳光穿过白色窗帘，桌面上有一颗悬浮旋转的水晶球，球面映着漫画封面的倒影

**Interaction Tier**: 封面页 L2（流畅交互 + 1个WebGL球体），功能页 L1（精致静态）
**Dependencies**: Cover page: Three.js (CDN) | Inner pages: CSS only
**WebGL Budget**: 封面页 1 个 Three.js sphere，IntersectionObserver 可见时渲染、不可见时暂停

---

## 2. Color Palette & Roles

The same CSS variable palette as v1, with v2 additions:

```css
:root {
  /* Backgrounds */
  --bg: #FAFAF8;
  --surface: #FFFFFF;
  --surface-alt: #F5F3F0;
  --surface-hover: #EEECE8;

  /* Borders */
  --border: #E6E3DE;
  --border-hover: #C5C0B8;

  /* Text */
  --text: #1C1C1C;
  --text-secondary: #5C5A57;
  --text-tertiary: #9C9994;

  /* Accent — warm amber-orange */
  --accent: #D4794A;
  --accent-hover: #C0683A;
  --accent-light: #FDF0E8;
  --accent-border: #F0D0B8;

  /* NEW v2: tech accent for landing page sphere effects */
  --tech-glow: #8B5CF6;
  --tech-glow-light: rgba(139, 92, 246, 0.12);

  /* RGB variants */
  --bg-rgb: 250, 250, 248;
  --surface-rgb: 255, 255, 255;
  --accent-rgb: 212, 121, 74;

  /* Semantic */
  --success: #5B8C5A; --success-bg: #EDF5EC;
  --error: #C45C4C;   --error-bg: #FDF0ED;
  --warning: #D49B4A; --warning-bg: #FDF5E8;

  /* Shadows */
  --shadow-sm: 0 1px 3px rgba(0,0,0,0.04);
  --shadow-md: 0 4px 16px rgba(0,0,0,0.06);
  --shadow-lg: 0 8px 28px rgba(0,0,0,0.09);
}
```

**Navigation-specific colors (overlaid on texture):**
- Sidebar background: the texture image, overlaid with `linear-gradient(180deg, rgba(250,248,245,0.92) 0%, rgba(245,243,240,0.95) 100%)`
- Nav items on texture: slightly increased contrast for readability

**Color Rules:** same as v1 + 紫色辉光仅用于封面页球体周边

---

## 3. Typography Rules

Same as v1, plus additions for landing page:

| Role | Font | Size | Weight | Line Height |
|------|------|------|--------|-------------|
| Hero Title (Landing) | Noto Sans SC | 48px | 800 | 1.2 |
| Hero Subtitle (Landing) | Inter, Noto Sans SC | 18px | 400 | 1.6 |
| Page Title H1 | Noto Sans SC | 24px | 700 | 1.4 |
| Body | Inter, Noto Sans SC | 14px | 400 | 1.7 |
| ... (rest same as v1) | | | | |

**Font Stack:** `@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Noto+Sans+SC:wght@400;500;600;700;800&display=swap');`

---

## 4. Component Stylings

### Landing Page Sphere Area
```css
.landing-hero {
  height: 100vh;
  display: flex; align-items: center; justify-content: center;
  background: radial-gradient(ellipse at center, var(--bg) 40%, rgba(139,92,246,0.04) 100%);
  position: relative; overflow: hidden;
}
.sphere-container { width: 520px; height: 520px; position: relative; }
```

### Navigation with Texture Background
```css
.sidebar-v2 {
  background-image: url('/nav-bg.webp');
  background-size: cover; background-position: center;
  position: relative;
}
.sidebar-v2::before {
  content: ''; position: absolute; inset: 0;
  background: linear-gradient(180deg, rgba(250,248,245,0.92) 0%, rgba(245,243,240,0.95) 100%);
  z-index: 0;
}
.sidebar-v2 > * { position: relative; z-index: 1; }
```

### ... (buttons, cards, inputs, badges, tabs remain same as v1)

---

## 5. Layout Principles

**v2 addition — Landing page sections sequence:**
```
Hero (100vh, 3D sphere + title + CTA)
  ↓
Quick Nav (bento grid: 3 feature cards linking to Chat/Library/Videos)
  ↓
Stats / Info bar
```

**Inner pages layout (unchanged):**
```
┌──────────┬─────────────────────────────────────────┐
│ Sidebar  │ Content Area (padding: 40px)             │
│ 240px    │                                          │
│ texture  │                                          │
│ bg       │                                          │
└──────────┴─────────────────────────────────────────┘
```

Container max 980px for text, sidebar fixed 240px. Section spacing 28px.

---

## 6. Depth & Elevation

Same as v1, plus:
- **Sphere glow**: the 3D sphere has a soft radial-gradient aura behind it (CSS, not WebGL)

---

## 7. Animation & Interaction

**Motion Philosophy**: 封面页「可控的惊艳」——球体自转丝滑、卡片淡入优雅；功能页「克制的安静」

### Cover Page: L2
**Landing page-specific animations:**

#### Entrance
```css
.hero-title { animation: fadeInUp 0.8s cubic-bezier(0.16,1,0.3,1) forwards; }
.hero-subtitle { animation: fadeInUp 0.8s 0.2s cubic-bezier(0.16,1,0.3,1) both; }
.hero-cta { animation: fadeInUp 0.8s 0.4s cubic-bezier(0.16,1,0.3,1) both; }
```

#### 3D Sphere
- Three.js scene: sphere rotating slowly on Y axis (0.003 rad/frame)
- Cover cards: distributed on spherical coordinates, opacity = 1 - |z| / (radius * 1.2), clamped to [0, 1]
- Cards facing the camera always (billboard effect via plane.lookAt)
- Particle field: 200 tiny dots drifting slowly around the sphere

#### Scroll
- Feature cards section: IntersectionObserver fadeInUp stagger
- No scroll-jacking, native smooth scroll

#### Hover
- CTA button: Magnet effect (subtle, 8px max pull)

### Inner Pages: L1 (unchanged from v1)

### Reduced Motion
```css
@media (prefers-reduced-motion: reduce) {
  .hero-title, .hero-subtitle, .hero-cta { animation: none; }
  canvas#sphere-canvas { display: none; } /* replace with static PNG fallback */
}
```

---

## 8. Do's and Don'ts

Same as v1, plus:

### v2 Additions
- ✅ 封面页是用户的「第一印象」——3秒内传达"这是做什么的"
- ✅ 球体旋转速度宜慢 (约 30s 一圈)，让人看清每张封面
- ✅ 导航栏纹理做半透明覆盖，保留纹理质感但不抢内容
- ❌ 封面页不要自动播放音乐或强制视频
- ❌ 球体旋转不要快于一分钟两圈（太快头晕）

---

## 9. Responsive Behavior

| Name | Width | Key Changes |
|------|-------|-------------|
| Desktop | > 1024px | Full sphere (520px), sidebar 240px |
| Tablet | 768-1024px | Sphere scales to 380px, sidebar collapses to icons |
| Mobile | < 768px | Sphere scales to 280px, sidebar becomes bottom tab bar |

Touch targets minimum 44×44px.
