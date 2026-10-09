/**
 * Chart maths, shared by every visualisation.
 *
 * Hand-rolled SVG rather than a charting library, for three reasons that matter
 * at this size: the charts here are simple (a line, a radar, a bar row), a
 * library would add ~50-100 KB to render them, and — most importantly — every
 * chart has to honour the product's "unmeasured is not zero" rule. Off-the-shelf
 * charts plot a gap as 0 or silently drop the point; here a null is a documented
 * case that renders as an explicit hole in the series.
 */

export interface Point {
  x: number;
  y: number;
}

/** Maps a value from one range to another, clamped to the output range. */
export function scale(value: number, inMin: number, inMax: number, outMin: number, outMax: number): number {
  if (inMax === inMin) return outMin;
  const t = (value - inMin) / (inMax - inMin);
  return outMin + Math.max(0, Math.min(1, t)) * (outMax - outMin);
}

/**
 * A smooth path through points, using Catmull-Rom converted to cubic béziers.
 *
 * A polyline through 4-6 sparse data points reads as jagged and makes small
 * differences look like dramatic swings. The tension is kept low (0.2) so the
 * curve stays honest — high tension invents overshoot between points, implying
 * values that were never measured.
 */
export function smoothPath(points: Point[], tension = 0.2): string {
  if (points.length === 0) return "";
  if (points.length === 1) return `M ${points[0].x} ${points[0].y}`;

  let path = `M ${points[0].x} ${points[0].y}`;
  for (let i = 0; i < points.length - 1; i += 1) {
    const p0 = points[i - 1] ?? points[i];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[i + 2] ?? p2;

    const cp1x = p1.x + ((p2.x - p0.x) / 6) * tension * 3;
    const cp1y = p1.y + ((p2.y - p0.y) / 6) * tension * 3;
    const cp2x = p2.x - ((p3.x - p1.x) / 6) * tension * 3;
    const cp2y = p2.y - ((p3.y - p1.y) / 6) * tension * 3;

    path += ` C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${p2.x} ${p2.y}`;
  }
  return path;
}

/** Closes a line path down to a baseline, producing the area beneath it. */
export function areaPath(points: Point[], baselineY: number, tension = 0.2): string {
  if (points.length === 0) return "";
  const line = smoothPath(points, tension);
  const last = points[points.length - 1];
  const first = points[0];
  return `${line} L ${last.x} ${baselineY} L ${first.x} ${baselineY} Z`;
}

/** Vertex positions for an n-sided radar polygon at a given radius fraction. */
export function radarPoints(
  values: number[],
  radius: number,
  cx: number,
  cy: number,
  max = 100,
): Point[] {
  const count = values.length;
  return values.map((value, index) => {
    // Start at 12 o'clock and go clockwise, which is how people read a dial.
    const angle = (index / count) * Math.PI * 2 - Math.PI / 2;
    const r = (Math.max(0, Math.min(max, value)) / max) * radius;
    return { x: cx + Math.cos(angle) * r, y: cy + Math.sin(angle) * r };
  });
}

/** Axis endpoints for an n-sided radar web. */
export function radarAxis(count: number, radius: number, cx: number, cy: number): Point[] {
  return Array.from({ length: count }, (_, index) => {
    const angle = (index / count) * Math.PI * 2 - Math.PI / 2;
    return { x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius };
  });
}

export function toPolygon(points: Point[]): string {
  return points.map((p) => `${p.x},${p.y}`).join(" ");
}

/** Short date for an axis tick — "12 Aug", never a full timestamp. */
export function shortDate(iso: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}
