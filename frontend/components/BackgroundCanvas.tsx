"use client";
import { useEffect, useRef } from "react";

interface Blob {
  x: number;
  y: number;
  vx: number;
  vy: number;
  r: number;
  magnetic: boolean;
}

export default function BackgroundCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let mouse = { x: window.innerWidth / 2, y: window.innerHeight / 2 };
    let animId = 0;

    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    resize();
    window.addEventListener("resize", resize);

    const blobs: Blob[] = Array.from({ length: 5 }, (_, i) => ({
      x: Math.random() * window.innerWidth,
      y: Math.random() * window.innerHeight,
      vx: (Math.random() - 0.5) * 0.3,
      vy: (Math.random() - 0.5) * 0.3,
      r: 200 + Math.random() * 200,
      magnetic: i === 0,
    }));

    const onMouse = (e: MouseEvent) => {
      mouse = { x: e.clientX, y: e.clientY };
    };
    window.addEventListener("mousemove", onMouse);

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      blobs.forEach((b) => {
        // Magnetic blob follows mouse
        if (b.magnetic) {
          b.x += (mouse.x - b.x) * 0.05;
          b.y += (mouse.y - b.y) * 0.05;
        } else {
          // Repel from cursor within 300px
          const dx = b.x - mouse.x;
          const dy = b.y - mouse.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 300 && dist > 0) {
            const force = (300 - dist) / 300;
            b.vx += (dx / dist) * force * 0.4;
            b.vy += (dy / dist) * force * 0.4;
          }

          // Friction + drift
          b.vx *= 0.98;
          b.vy *= 0.98;
          b.x += b.vx;
          b.y += b.vy;

          // Wrap edges
          if (b.x < -b.r) b.x = canvas.width + b.r;
          if (b.x > canvas.width + b.r) b.x = -b.r;
          if (b.y < -b.r) b.y = canvas.height + b.r;
          if (b.y > canvas.height + b.r) b.y = -b.r;
        }

        const grad = ctx.createRadialGradient(b.x, b.y, 0, b.x, b.y, b.r);
        grad.addColorStop(0, "rgba(4,8,14,0.55)");
        grad.addColorStop(1, "transparent");

        ctx.beginPath();
        ctx.arc(b.x, b.y, b.r, 0, Math.PI * 2);
        ctx.fillStyle = grad;
        ctx.fill();
      });

      animId = requestAnimationFrame(draw);
    };
    draw();

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener("resize", resize);
      window.removeEventListener("mousemove", onMouse);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 0,
        pointerEvents: "none",
      }}
    />
  );
}
