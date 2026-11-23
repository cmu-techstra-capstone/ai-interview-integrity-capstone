import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { clampPosition, type Point } from "./clamp";

type Size = { width: number; height: number };

/**
 * Pointer-based drag that ignores tiny movements so clicks still activate controls.
 */
export function useDraggable(initial: Point, size: Size) {
  const [position, setPosition] = useState<Point>(initial);
  const dragging = useRef(false);
  const moved = useRef(false);
  const origin = useRef({ pointerX: 0, pointerY: 0, startX: 0, startY: 0 });

  const reclamp = useCallback(() => {
    setPosition((prev) => clampPosition(prev.x, prev.y, size.width, size.height));
  }, [size.height, size.width]);

  useEffect(() => {
    reclamp();
    window.addEventListener("resize", reclamp);
    return () => window.removeEventListener("resize", reclamp);
  }, [reclamp]);

  const onPointerDown = useCallback(
    (event: ReactPointerEvent<HTMLElement>) => {
      if (event.button !== 0) return;
      dragging.current = true;
      moved.current = false;
      origin.current = {
        pointerX: event.clientX,
        pointerY: event.clientY,
        startX: position.x,
        startY: position.y,
      };
      event.currentTarget.setPointerCapture(event.pointerId);
    },
    [position.x, position.y],
  );

  const onPointerMove = useCallback(
    (event: ReactPointerEvent<HTMLElement>) => {
      if (!dragging.current) return;
      const dx = event.clientX - origin.current.pointerX;
      const dy = event.clientY - origin.current.pointerY;
      if (!moved.current && dx * dx + dy * dy < 16) return;
      moved.current = true;
      setPosition(
        clampPosition(
          origin.current.startX + dx,
          origin.current.startY + dy,
          size.width,
          size.height,
        ),
      );
    },
    [size.height, size.width],
  );

  const onPointerUp = useCallback((event: ReactPointerEvent<HTMLElement>) => {
    if (!dragging.current) return;
    dragging.current = false;
    try {
      event.currentTarget.releasePointerCapture(event.pointerId);
    } catch {
      /* already released */
    }
  }, []);

  const didDrag = useCallback(() => moved.current, []);

  return {
    position,
    setPosition,
    didDrag,
    dragHandlers: {
      onPointerDown,
      onPointerMove,
      onPointerUp,
      onPointerCancel: onPointerUp,
    },
  };
}
