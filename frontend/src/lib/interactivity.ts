import { useEffect, useRef, useState, type CSSProperties, type MouseEvent as ReactMouseEvent, type RefObject } from "react";

function prefersReducedMotion() {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export interface TypewriterDemoItem {
  question: string;
  answer: string;
  citation: string;
  pill: string;
}

export type TypewriterPhase = "typing" | "thinking" | "answered";

/** Cycles through demo Q&A pairs: types the question, "thinks", reveals the answer, holds, then advances. */
export function useTypewriterDemo(demos: TypewriterDemoItem[], options?: { typeSpeed?: number; thinkDelay?: number; answerHold?: number }) {
  const { typeSpeed = 38, thinkDelay = 550, answerHold = 3200 } = options ?? {};
  const [demoIndex, setDemoIndex] = useState(0);
  const [typed, setTyped] = useState("");
  const [phase, setPhase] = useState<TypewriterPhase>("typing");
  const reduced = prefersReducedMotion();

  useEffect(() => {
    if (reduced) {
      setTyped(demos[demoIndex].question);
      setPhase("answered");
      return;
    }
    let cancelled = false;
    const question = demos[demoIndex].question;
    setPhase("typing");
    setTyped("");
    let i = 0;
    const timer = window.setInterval(() => {
      i++;
      setTyped(question.slice(0, i));
      if (i >= question.length) {
        window.clearInterval(timer);
        window.setTimeout(() => { if (!cancelled) setPhase("thinking"); }, 300);
      }
    }, typeSpeed);
    return () => { cancelled = true; window.clearInterval(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [demoIndex]);

  useEffect(() => {
    if (reduced || phase !== "thinking") return;
    const t = window.setTimeout(() => setPhase("answered"), thinkDelay);
    return () => window.clearTimeout(t);
  }, [phase, reduced, thinkDelay]);

  useEffect(() => {
    if (reduced || phase !== "answered") return;
    const t = window.setTimeout(() => setDemoIndex((i) => (i + 1) % demos.length), answerHold);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, reduced, answerHold, demos.length]);

  return { demo: demos[demoIndex], typed, phase };
}

/** True once the element has scrolled into view; stays true after (no re-hide on scroll-out). */
export function useInView<T extends HTMLElement>(options?: IntersectionObserverInit): [RefObject<T | null>, boolean] {
  const ref = useRef<T | null>(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (prefersReducedMotion()) {
      setInView(true);
      return;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true);
          observer.disconnect();
        }
      },
      { threshold: 0.15, rootMargin: "0px 0px -60px 0px", ...options },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return [ref, inView];
}

/** Eases a number from 0 to target once `active` flips true. */
export function useCountUp(target: number, active: boolean, duration = 1100) {
  const [value, setValue] = useState(prefersReducedMotion() ? target : 0);

  useEffect(() => {
    if (!active || prefersReducedMotion()) {
      if (active) setValue(target);
      return;
    }
    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(target * eased);
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [active, target, duration]);

  return value;
}

/** Throttled (rAF) window scrollY. */
export function useScrollY() {
  const [y, setY] = useState(() => (typeof window === "undefined" ? 0 : window.scrollY));
  useEffect(() => {
    let ticking = false;
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(() => {
        setY(window.scrollY);
        ticking = false;
      });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  return y;
}

/** Highlights whichever section id is currently most visible near the top of the viewport. */
export function useActiveSection(ids: string[]) {
  const [active, setActive] = useState<string | null>(null);
  useEffect(() => {
    const elements = ids.map((id) => document.getElementById(id)).filter((el): el is HTMLElement => !!el);
    if (elements.length === 0) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        if (visible.length > 0) setActive(visible[0].target.id);
      },
      { rootMargin: "-45% 0px -45% 0px", threshold: [0, 0.25, 0.5, 0.75, 1] },
    );
    elements.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [ids.join(",")]);
  return active;
}

/** Subtle pointer-follow 3D tilt for cards/panels. Attach ref + handlers to the element. */
export function useTilt<T extends HTMLElement>(strength = 8) {
  const ref = useRef<T | null>(null);
  const [style, setStyle] = useState<CSSProperties>({});

  const onMouseMove = (event: ReactMouseEvent) => {
    if (prefersReducedMotion()) return;
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const px = (event.clientX - rect.left) / rect.width - 0.5;
    const py = (event.clientY - rect.top) / rect.height - 0.5;
    setStyle({
      transform: `perspective(1000px) rotateX(${(-py * strength).toFixed(2)}deg) rotateY(${(px * strength).toFixed(2)}deg) translateZ(0)`,
    });
  };
  const onMouseLeave = () => setStyle({});

  return { ref, style, onMouseMove, onMouseLeave };
}

/** Cycles through a fixed list of step indices on an interval; holds on step 0 if reduced motion is preferred. */
export function useCycle(steps: number, intervalMs: number) {
  const [index, setIndex] = useState(0);
  useEffect(() => {
    if (prefersReducedMotion() || steps <= 1) return;
    const timer = window.setInterval(() => setIndex((i) => (i + 1) % steps), intervalMs);
    return () => window.clearInterval(timer);
  }, [steps, intervalMs]);
  return index;
}

/** Pointer-follow parallax offset for decorative elements (e.g. hero blobs). */
export function useParallax<T extends HTMLElement>(strength = 18) {
  const ref = useRef<T | null>(null);
  const [offset, setOffset] = useState({ x: 0, y: 0 });

  const onMouseMove = (event: ReactMouseEvent) => {
    if (prefersReducedMotion()) return;
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const px = (event.clientX - rect.left) / rect.width - 0.5;
    const py = (event.clientY - rect.top) / rect.height - 0.5;
    setOffset({ x: px * strength, y: py * strength });
  };
  const onMouseLeave = () => setOffset({ x: 0, y: 0 });

  return { ref, offset, onMouseMove, onMouseLeave };
}
