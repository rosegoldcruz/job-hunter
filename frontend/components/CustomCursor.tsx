"use client";
import { useEffect, useRef, useState } from "react";

export default function CustomCursor() {
  const outerRef = useRef<HTMLDivElement>(null);
  const dotRef = useRef<HTMLDivElement>(null);
  const [isTouch, setIsTouch] = useState(true); // default hidden until we confirm pointer device

  useEffect(() => {
    // Only show custom cursor on fine-pointer (mouse) devices
    const mq = window.matchMedia("(pointer: fine)");
    setIsTouch(!mq.matches);

    const onChange = (e: MediaQueryListEvent) => setIsTouch(!e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    if (isTouch) return;

    const outer = outerRef.current;
    const dot = dotRef.current;
    if (!outer || !dot) return;

    let ox = window.innerWidth / 2;
    let oy = window.innerHeight / 2;
    let tx = ox;
    let ty = oy;
    let animId = 0;

    const onMove = (e: MouseEvent) => {
      tx = e.clientX;
      ty = e.clientY;
      dot.style.left = `${tx}px`;
      dot.style.top = `${ty}px`;
    };

    const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

    const animate = () => {
      ox = lerp(ox, tx, 0.12);
      oy = lerp(oy, ty, 0.12);
      outer.style.left = `${ox}px`;
      outer.style.top = `${oy}px`;
      animId = requestAnimationFrame(animate);
    };
    animate();

    const onOver = (e: MouseEvent) => {
      const el = e.target as HTMLElement;
      const interactive = el.closest("a, button, [data-interactive]");
      if (interactive) {
        outer.classList.add("hover");
      } else {
        outer.classList.remove("hover");
      }
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseover", onOver);

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseover", onOver);
    };
  }, [isTouch]);

  if (isTouch) return null;

  return (
    <>
      <div ref={outerRef} className="cursor-outer" />
      <div ref={dotRef} className="cursor-dot" />
    </>
  );
}
