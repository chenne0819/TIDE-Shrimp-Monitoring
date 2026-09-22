"use client";

import { useEffect, useRef, useState } from "react";
import type { CSSProperties, KeyboardEvent, PointerEvent } from "react";

const STORAGE_KEY = "tide.assistant.chat-width";
const DEFAULT_WIDTH = 440;
type PanelDrag = {
  pointerId: number;
  x: number;
  width: number;
  target: HTMLDivElement;
};
const releaseDragCapture = (drag: PanelDrag | null) => {
  if (drag?.target.hasPointerCapture(drag.pointerId))
    drag.target.releasePointerCapture(drag.pointerId);
};

export function panelBounds(containerWidth: number) {
  const available = Number.isFinite(containerWidth)
    ? Math.max(0, containerWidth)
    : 0;
  const max = Math.max(
    0,
    Math.min(760, available - Math.min(360, available / 2) - 8),
  );
  return { min: Math.min(320, max), max };
}

export function clampPanelWidth(value: number, containerWidth: number) {
  const { min, max } = panelBounds(containerWidth);
  return Math.round(
    Math.min(
      max,
      Math.max(min, Number.isFinite(value) ? value : DEFAULT_WIDTH),
    ),
  );
}

export function panelKeyboardWidth(
  key: string,
  current: number,
  containerWidth: number,
  shift = false,
) {
  const { min, max } = panelBounds(containerWidth);
  const step = shift ? 64 : 16;
  if (key === "Home") return min;
  if (key === "End") return max;
  // The handle moves left to make the right-hand panel wider.
  if (key === "ArrowLeft")
    return clampPanelWidth(current + step, containerWidth);
  if (key === "ArrowRight")
    return clampPanelWidth(current - step, containerWidth);
  return null;
}

export function useAssistantPanelResize() {
  const layoutRef = useRef<HTMLDivElement>(null);
  const widthRef = useRef(DEFAULT_WIDTH);
  const preferredWidth = useRef(DEFAULT_WIDTH);
  const drag = useRef<PanelDrag | null>(null);
  const [width, setWidth] = useState(DEFAULT_WIDTH);
  const [containerWidth, setContainerWidth] = useState(1000);
  const [dragging, setDragging] = useState(false);

  const persist = (value: number) => {
    try {
      window.localStorage.setItem(STORAGE_KEY, String(value));
    } catch {
      /* Storage may be unavailable. */
    }
  };
  const updateWidth = (value: number, remember: boolean) => {
    const size =
      layoutRef.current?.getBoundingClientRect().width ?? containerWidth;
    const next = clampPanelWidth(value, size);
    widthRef.current = next;
    setWidth(next);
    if (remember) {
      preferredWidth.current = next;
      persist(next);
    }
  };

  useEffect(() => {
    const element = layoutRef.current;
    if (!element) return;
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      if (
        saved !== null &&
        saved.trim() &&
        Number.isFinite(Number(saved)) &&
        Number(saved) > 0
      )
        preferredWidth.current = Number(saved);
    } catch {
      /* Width remains usable when storage is blocked. */
    }
    let measuredWidth: number | undefined;
    const measure = () => {
      const size = element.getBoundingClientRect().width;
      // Height-only/initial observer deliveries must not reset an active drag.
      if (size === measuredWidth) return;
      measuredWidth = size;
      // A viewport change invalidates the drag origin. Cancel before applying
      // its narrower bound, so lost capture cannot persist a mobile clamp.
      const interrupted = drag.current;
      if (interrupted) {
        drag.current = null;
        setDragging(false);
        releaseDragCapture(interrupted);
      }
      setContainerWidth(size);
      const next = clampPanelWidth(preferredWidth.current, size);
      widthRef.current = next;
      setWidth(next);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => {
      observer.disconnect();
      const interrupted = drag.current;
      drag.current = null;
      releaseDragCapture(interrupted);
    };
  }, []);

  const finish = (event: PointerEvent<HTMLDivElement>) => {
    if (drag.current?.pointerId !== event.pointerId) return;
    drag.current = null;
    setDragging(false);
    preferredWidth.current = widthRef.current;
    persist(widthRef.current);
    if (event.currentTarget.hasPointerCapture(event.pointerId))
      event.currentTarget.releasePointerCapture(event.pointerId);
  };
  const bounds = panelBounds(containerWidth);
  return {
    layoutRef,
    panelWidth: width,
    containerWidth,
    style: { "--ai-chat-width": `${width}px` } as CSSProperties,
    dragging,
    separatorProps: {
      role: "separator" as const,
      tabIndex: 0,
      "aria-label": "調整對話寬度",
      "aria-controls": "ai-chat-panel",
      "aria-orientation": "vertical" as const,
      "aria-valuemin": Math.round(bounds.min),
      "aria-valuemax": Math.round(bounds.max),
      "aria-valuenow": width,
      "aria-valuetext": `對話寬度 ${width} 像素`,
      onPointerDown(event: PointerEvent<HTMLDivElement>) {
        if (!event.isPrimary || event.button !== 0 || drag.current) return;
        event.preventDefault();
        event.currentTarget.focus();
        event.currentTarget.setPointerCapture(event.pointerId);
        drag.current = {
          pointerId: event.pointerId,
          x: event.clientX,
          width: widthRef.current,
          target: event.currentTarget,
        };
        setDragging(true);
      },
      onPointerMove(event: PointerEvent<HTMLDivElement>) {
        if (drag.current?.pointerId !== event.pointerId) return;
        updateWidth(drag.current.width + drag.current.x - event.clientX, false);
      },
      onPointerUp: finish,
      onPointerCancel: finish,
      onLostPointerCapture: finish,
      onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
        const size =
          layoutRef.current?.getBoundingClientRect().width ?? containerWidth;
        const next = panelKeyboardWidth(
          event.key,
          widthRef.current,
          size,
          event.shiftKey,
        );
        if (next === null) return;
        event.preventDefault();
        updateWidth(next, true);
      },
    },
  };
}
