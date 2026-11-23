export type Point = { x: number; y: number };

export function clampPosition(
  x: number,
  y: number,
  width: number,
  height: number,
  margin = 8,
): Point {
  const maxX = Math.max(margin, window.innerWidth - width - margin);
  const maxY = Math.max(margin, window.innerHeight - height - margin);
  return {
    x: Math.min(Math.max(margin, x), maxX),
    y: Math.min(Math.max(margin, y), maxY),
  };
}

/** Default lower-right placement, offset upward from typical Meet bottom controls. */
export function defaultLauncherPosition(size: number): Point {
  const margin = 16;
  const bottomOffset = 88;
  return clampPosition(
    window.innerWidth - size - margin,
    window.innerHeight - size - bottomOffset,
    size,
    size,
    margin,
  );
}
