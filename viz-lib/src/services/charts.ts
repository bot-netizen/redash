/*
  How many charts are on the page, and how many have finished drawing.

  A page being photographed has to say when it is ready, and "the layout
  stopped moving" turned out to be a guess rather than an answer: between the
  tiles being laid out and ECharts putting a canvas in them, the document is
  genuinely still. Measured on a dashboard of eighty widgets, the same URL
  came back 3.1 MB or 1.7 MB depending on which side of that gap the capture
  landed -- the smaller one a grid of five charts and seventy-five empty
  rectangles, about one capture in four.

  This is the positive signal instead: a chart says it exists when its
  container mounts, and says it has drawn when ECharts reports `finished`.
  Nothing has to infer anything from pixels.

  Counted rather than listed, because the question is only ever "are we
  waiting for any of them".
*/

/** Every chart that has mounted, and whether it has drawn yet. */
const charts = new Map<symbol, boolean>();

/**
 * Say a chart now exists on the page.
 *
 * Returns the token it reports with, and a disposer for when it unmounts --
 * a chart that goes away must stop being waited for, or a dashboard somebody
 * is editing never looks finished.
 */
export function chartMounted(): { token: symbol; dispose: () => void } {
  const token = Symbol("chart");
  charts.set(token, false);
  return { token, dispose: () => charts.delete(token) };
}

/** Say that chart has drawn. Later redraws say it again, harmlessly. */
export function chartDrawn(token: symbol): void {
  if (charts.has(token)) {
    charts.set(token, true);
  }
}

/**
 * How many charts exist at all, drawn or not.
 *
 * The page being photographed folds this into its "has anything moved"
 * check. Waiting for nothing to be pending is not enough on its own: before
 * any container has mounted, nothing is pending either, and that moment looks
 * exactly like being finished. A chart appearing has to count as movement.
 */
export function chartsMounted(): number {
  return charts.size;
}

/** How many charts exist but have not yet reported drawing. */
export function chartsStillDrawing(): number {
  let waiting = 0;
  charts.forEach((drawn) => {
    if (!drawn) {
      waiting += 1;
    }
  });
  return waiting;
}

/** Test seam: put the module back to how it starts. */
export function resetChartsForTests(): void {
  charts.clear();
}
