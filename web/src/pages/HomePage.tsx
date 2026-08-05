import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { ArrowRight, Sparkles } from 'lucide-react';
import { useAppStore } from '../stores/app';

// ── 你的封面素材 (不够就循环) ──
const COVER_IMAGES = [
  '/OIP-C.webp',
  '/OIP-C%20(1).webp',
  '/OIP-C%20(2).webp',
  '/77d01fd797f5f0c3735c3aa4f7f10c81.jpg',
  '/dedeaf9e9c9c0a2ce9c169220f69d6a71753346503145.jpeg',
  '/phpK4eqjo1693217726.jfif',
  '/canva-oFLgs-SjRas.jpg',
];

const SPHERE_RADIUS = 2.2;
const CARD_COUNT = 16;
const CARD_W = 0.55;
const CARD_H = 0.75;

// ── 创建带圆角 + 内阴影的卡片纹理 ──
function makeCardTexture(imgSrc: string): Promise<THREE.CanvasTexture> {
  return new Promise((resolve) => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      const w = 256, h = 349; // ~3:4 ratio
      const canvas = document.createElement('canvas');
      canvas.width = w; canvas.height = h;
      const ctx = canvas.getContext('2d')!;

      // 圆角矩形裁剪
      const r = 14;
      ctx.beginPath();
      ctx.moveTo(r, 0);
      ctx.lineTo(w - r, 0); ctx.arcTo(w, 0, w, r, r);
      ctx.lineTo(w, h - r); ctx.arcTo(w, h, w - r, h, r);
      ctx.lineTo(r, h); ctx.arcTo(0, h, 0, h - r, r);
      ctx.lineTo(0, r); ctx.arcTo(0, 0, r, 0, r);
      ctx.clip();

      // 绘制图片：cover 填满
      const scale = Math.max(w / img.width, h / img.height);
      const iw = img.width * scale, ih = img.height * scale;
      const dx = (w - iw) / 2, dy = (h - ih) / 2;
      ctx.drawImage(img, dx, dy, iw, ih);

      // 微妙内发光边框
      ctx.strokeStyle = 'rgba(255,255,255,0.25)';
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(r, 0); ctx.lineTo(w - r, 0); ctx.arcTo(w, 0, w, r, r);
      ctx.lineTo(w, h - r); ctx.arcTo(w, h, w - r, h, r);
      ctx.lineTo(r, h); ctx.arcTo(0, h, 0, h - r, r);
      ctx.lineTo(0, r); ctx.arcTo(0, 0, r, 0, r);
      ctx.closePath();
      ctx.stroke();

      const tex = new THREE.CanvasTexture(canvas);
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.minFilter = THREE.LinearMipmapLinearFilter;
      tex.magFilter = THREE.LinearFilter;
      tex.generateMipmaps = true;
      resolve(tex);
    };
    img.onerror = () => resolve(new THREE.CanvasTexture(document.createElement('canvas')));
    img.src = imgSrc;
  });
}

export default function HomePage() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const setActivePage = useAppStore(s => s.setActivePage);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    // ── Three.js setup ──
    const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(canvas.clientWidth, canvas.clientHeight);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(60, canvas.clientWidth / canvas.clientHeight, 0.5, 12);
    camera.position.z = 5.5;

    // ── Lighting ──
    scene.add(new THREE.AmbientLight(0xffffff, 0.6));
    const key = new THREE.DirectionalLight(0xffffff, 1.2);
    key.position.set(3, 2, 4);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0xaaccff, 0.4);
    fill.position.set(-2, -1, -1);
    scene.add(fill);

    // ── Particles ──
    const pGeom = new THREE.BufferGeometry();
    const pCount = 300;
    const pPos = new Float32Array(pCount * 3);
    for (let i = 0; i < pCount; i++) {
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      const r = SPHERE_RADIUS + 0.3 + Math.random() * 1.5;
      pPos[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      pPos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
      pPos[i * 3 + 2] = r * Math.cos(phi);
    }
    pGeom.setAttribute('position', new THREE.BufferAttribute(pPos, 3));
    const pMat = new THREE.PointsMaterial({ color: 0x8b5cf6, size: 0.015, transparent: true, opacity: 0.5 });
    const particles = new THREE.Points(pGeom, pMat);
    scene.add(particles);

    // ── Cover cards orbiting sphere ──
    const cards: THREE.Mesh[] = [];

    // Fibonacci sphere distribution
    const phi_golden = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < CARD_COUNT; i++) {
      const y = 1 - (i / (CARD_COUNT - 1)) * 2;
      const radiusAtY = Math.sqrt(1 - y * y);
      const theta = phi_golden * i;

      const x = Math.cos(theta) * radiusAtY;
      const z = Math.sin(theta) * radiusAtY;

      const geometry = new THREE.PlaneGeometry(CARD_W, CARD_H);
      const material = new THREE.MeshStandardMaterial({
        color: 0xd5c8b8,
        roughness: 0.35,
        metalness: 0.02,
        transparent: true,
        opacity: 1,
        side: THREE.DoubleSide,
      });
      const card = new THREE.Mesh(geometry, material);

      // Position on sphere surface
      card.position.set(x * SPHERE_RADIUS, y * SPHERE_RADIUS, z * SPHERE_RADIUS);
      // Face outward from sphere center (so texture reads correctly from outside)
      card.lookAt(x * SPHERE_RADIUS * 3, y * SPHERE_RADIUS * 3, z * SPHERE_RADIUS * 3);

      scene.add(card);
      cards.push(card);

      // Load texture with rounded corners → assign to this card's material
      const imgSrc = COVER_IMAGES[i % COVER_IMAGES.length];
      const matRef = material; // capture per-card reference
      makeCardTexture(imgSrc).then((tex) => {
        matRef.map = tex;
        matRef.color.set(0xffffff);
        matRef.needsUpdate = true;
      });
    }

    // ── Handle resize ──
    const onResize = () => {
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      renderer.setSize(w, h);
      camera.aspect = w / Math.max(h, 1);
      camera.updateProjectionMatrix();
    };
    window.addEventListener('resize', onResize);

    // ── Animation loop ──
    let animId: number;
    const timer = new THREE.Timer();
    const animate = (ts: number) => {
      animId = requestAnimationFrame(animate);
      timer.update(ts);
      const dt = Math.min(timer.getDelta(), 0.1);
      const rotSpeed = 0.25; // radians per second

      // Rotate the whole group: rotate each card around Y axis
      for (const card of cards) {
        // Rotate position around Y
        const p = card.position;
        const cosA = Math.cos(rotSpeed * dt);
        const sinA = Math.sin(rotSpeed * dt);
        const nx = p.x * cosA - p.z * sinA;
        const nz = p.x * sinA + p.z * cosA;
        p.set(nx, p.y, nz);

        // Face outward so texture reads correctly
        const op = card.position;
        card.lookAt(op.x * 3, op.y * 3, op.z * 3);

        // Opacity based on z-depth: closer to camera = more opaque
        const zNorm = (p.z + SPHERE_RADIUS) / (2 * SPHERE_RADIUS); // 0 (back) to 1 (front)
        const opacity = 0.15 + zNorm * 0.85;
        (card.material as THREE.MeshStandardMaterial).opacity = opacity;
      }

      // Subtle particle rotation
      particles.rotation.y += rotSpeed * dt * 0.3;
      particles.rotation.x += rotSpeed * dt * 0.1;

      renderer.render(scene, camera);
    };
    animate();

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', onResize);
      renderer.dispose();
      scene.clear();
    };
  }, []);

  const handleEnter = () => {
    setActivePage('chat');
  };

  return (
    <div style={{
      height: '100vh', display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      background: 'radial-gradient(ellipse at center, var(--bg) 30%, rgba(139,92,246,0.05) 70%, rgba(139,92,246,0.10) 100%)',
      position: 'relative', overflow: 'hidden',
      fontFamily: '"Noto Sans SC", "Inter", sans-serif',
    }}>
      {/* Canvas */}
      <canvas
        ref={canvasRef}
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
      />

      {/* Welcome text */}
      <div style={{ position: 'relative', zIndex: 1, textAlign: 'center', marginBottom: 40 }}>
        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: 8,
          padding: '5px 16px', borderRadius: 100,
          background: 'var(--accent-light)', border: '1px solid var(--accent-border)',
          color: 'var(--accent)', fontSize: 12, fontWeight: 600,
          marginBottom: 20, letterSpacing: '0.04em',
          animation: 'fadeInUp 0.8s cubic-bezier(0.16,1,0.3,1) both',
        }}>
          <Sparkles size={14} /> AI COMIC STUDIO
        </div>
        <h1 style={{
          fontSize: 48, fontWeight: 800, color: 'var(--text)',
          lineHeight: 1.2, letterSpacing: '-0.02em',
          maxWidth: 580, margin: '0 auto 12px',
          animation: 'fadeInUp 0.8s 0.15s cubic-bezier(0.16,1,0.3,1) both',
        }}>
          用 AI 将小说变成
          <span style={{ color: 'var(--accent)' }}>漫剧视频</span>
        </h1>
        <p style={{
          fontSize: 17, color: 'var(--text-tertiary)',
          lineHeight: 1.6, maxWidth: 460, margin: '0 auto',
          animation: 'fadeInUp 0.8s 0.3s cubic-bezier(0.16,1,0.3,1) both',
        }}>
          上传小说，AI 自动生成剧本、角色、场景和视频
        </p>
      </div>

      {/* 3D CTA button */}
      <button
        onClick={handleEnter}
        style={{
          position: 'relative', zIndex: 1,
          display: 'inline-flex', alignItems: 'center', gap: 12,
          padding: '16px 40px',
          borderRadius: 16,
          border: 'none',
          background: 'linear-gradient(135deg, var(--accent) 0%, #e68a5a 50%, var(--accent) 100%)',
          backgroundSize: '200% 200%',
          color: '#fff',
          fontFamily: 'inherit', fontSize: 17, fontWeight: 700,
          cursor: 'pointer',
          boxShadow: '0 8px 32px rgba(212,121,74,0.35), 0 2px 8px rgba(212,121,74,0.2)',
          transform: 'translateY(0)',
          transition: 'all 0.25s cubic-bezier(0.16,1,0.3,1)',
          animation: 'fadeInUp 0.8s 0.5s cubic-bezier(0.16,1,0.3,1) both',
        }}
        onMouseEnter={e => {
          e.currentTarget.style.transform = 'translateY(-3px) scale(1.03)';
          e.currentTarget.style.boxShadow = '0 14px 40px rgba(212,121,74,0.45), 0 4px 12px rgba(212,121,74,0.25)';
        }}
        onMouseLeave={e => {
          e.currentTarget.style.transform = 'translateY(0) scale(1)';
          e.currentTarget.style.boxShadow = '0 8px 32px rgba(212,121,74,0.35), 0 2px 8px rgba(212,121,74,0.2)';
        }}
        onMouseDown={e => {
          e.currentTarget.style.transform = 'translateY(0) scale(0.98)';
        }}
        onMouseUp={e => {
          e.currentTarget.style.transform = 'translateY(-3px) scale(1.03)';
        }}
      >
        开始使用
        <ArrowRight size={20} />
      </button>

      {/* Style keyframes */}
      <style>{`
        @keyframes fadeInUp {
          from { opacity: 0; transform: translateY(20px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}
