import { useEffect } from "react";
import { has } from "lodash";
import { chartsMounted, chartsStillDrawing } from "@sqldesk/viz/lib/services/charts";
import { isDeferringOffscreenCharts } from "@sqldesk/viz/lib/services/offscreen";
import location from "@/services/location";

/*
  `?screenshot=1`: the page is being photographed, not read.

  Two things follow from that. The chrome goes, because a picture of a chart
  should be a chart. And the page has to say when it has finished drawing,
  because the renderer on the other side has no way to know: without a signal
  the usual result is a photograph of a loading spinner. Superset's own
  documentation describes checking captures for blank content afterwards,
  which is what you are left doing when the page never says.

  "Finished" has to mean *settled*, not *data has arrived*. The first version
  waited for the data and two animation frames, and produced a counter whose
  sparkline was a 90px sliver in the corner of a box 1350px wide: ECharts had
  drawn itself at the size its container had before the flex layout resolved,
  and viz-lib's resize watcher -- which polls at 100ms -- had not yet told it
  to grow. The picture was of a real moment, just not a moment anyone would
  recognise.

  So the page now waits for its own layout to stop moving: it samples the
  things that change when a chart resizes and only says "drawn" once two
  consecutive samples agree. That naturally covers the polling watcher, web
  fonts reflowing text, and anything else that settles late, without guessing
  at a sleep long enough to cover all three.
*/

export const SCREENSHOT_ATTRIBUTE = "data-rendered";

/**
 * Has every widget on this dashboard finished, so the page is worth capturing?
 *
 * Not `every(widget => !widget.loading)`, which is what this was: a widget is
 * not loading *before* it starts either, so that is true on the first render
 * and the page says it has drawn while it is still empty. An empty page is
 * perfectly still, so the settling check below agrees with it and the picture
 * is a grid of blank tiles.
 *
 * It really happened, about half the time, on a dashboard of eighty widgets:
 * the same URL captured 3.1 MB or 1.7 MB depending on which side of the race
 * it landed. A widget is done when it has stopped loading *and* has something
 * to show -- a result or an error. A textbox has no query and is done when it
 * exists.
 */
export function everyWidgetHasFinished(widgets) {
  return (widgets || []).every((widget) => !widget.visualization || (!widget.loading && widget.data !== undefined));
}

/** How often to look for movement. Longer than viz-lib's 100ms resize poll. */
const SAMPLE_MS = 150;

/** Two matching samples means settled. */
const STABLE_SAMPLES = 2;

/**
 * The earliest a page may claim to have drawn, measured from the moment its
 * data arrived.
 *
 * Stillness alone is not enough, and this is the second time that has bitten.
 * Between "every widget has its result" and "ECharts has put a canvas on the
 * page" there is a gap of a few hundred milliseconds in which the document is
 * genuinely, measurably still -- the tiles are laid out and empty. Two samples
 * 150ms apart both land in it often enough to matter: on a dashboard of eighty
 * widgets the same URL came back 3.1 MB or 1.7 MB, about half and half, with
 * the 1.7 MB one a grid of blank tiles.
 *
 * So nothing is declared drawn inside this window however still it looks. It
 * costs every capture a second and a half; a wrong picture costs more.
 */
const MIN_SETTLE_MS = 1500;

/**
 * Give up waiting and take the picture anyway.
 *
 * A page that never settles -- a live dashboard ticking every second, an
 * animation that does not end -- must still be photographed. A slightly early
 * picture beats a timeout and no picture at all.
 *
 * Raising this to 45s was tried against the capture problem described on
 * MIN_SETTLE_MS and changed nothing: the wait stayed at about ten seconds
 * either way, which is how we know the settling check is what decides and
 * this is not.
 */
const DEADLINE_MS = 10000;

export function inScreenshotMode() {
  return has(location.search, "screenshot");
}

/**
 * What the page looks like right now, as a string.
 *
 * Canvas dimensions are the tell: every chart here draws into one, and a
 * chart that is still growing changes them. The document height catches
 * everything else -- a table paginating in, an image loading, text reflowing
 * when a font arrives.
 */
function layoutFingerprint() {
  const canvases = Array.prototype.map
    .call(document.querySelectorAll("canvas"), (canvas) => `${canvas.width}x${canvas.height}`)
    .join(",");
  // The number of charts is part of what "has anything moved" means. Without
  // it, the moment before any chart container has mounted looks exactly like
  // the moment after they have all finished: nothing pending, nothing
  // changing. That is the moment the blank captures were taken in.
  return [document.documentElement.scrollHeight, document.documentElement.scrollWidth, chartsMounted(), canvases].join(
    "|"
  );
}

/**
 * Mark the document as drawn once `ready` is true and the page has settled.
 *
 * Set on <html> rather than on any one element so the renderer's selector
 * does not depend on a page's markup.
 */
export default function useScreenshotMode(ready) {
  useEffect(() => {
    if (!inScreenshotMode() || !ready) {
      return undefined;
    }

    let cancelled = false;
    let timer = null;

    const markDrawn = () => {
      if (!cancelled) {
        document.documentElement.setAttribute(SCREENSHOT_ATTRIBUTE, "true");
      }
    };

    const waitForStillness = (previous, matches, startedAt) => {
      if (cancelled) {
        return;
      }

      const current = layoutFingerprint();
      const agreed = current === previous ? matches + 1 : 0;
      const elapsed = Date.now() - startedAt;

      // A chart below the window is not built until it is scrolled towards.
      // A page being photographed is captured whole, so the first
      // visualization to render turns that off for everybody -- and until it
      // has, most of this page is empty rectangles that are perfectly still.
      // Stillness alone said "drawn" to that, which is how a capture of an
      // eighty-widget dashboard came back with five charts on it.
      //
      // And then the charts themselves say when they have rendered, which is
      // the only answer that is not a guess about pixels. Stillness, the
      // settling floor and the deferral check are all still here -- they
      // cover a page with no ECharts on it at all, which has nothing to
      // report.
      const stillWaitingForCharts = isDeferringOffscreenCharts() || chartsStillDrawing() > 0;

      if ((agreed >= STABLE_SAMPLES && elapsed >= MIN_SETTLE_MS && !stillWaitingForCharts) || elapsed > DEADLINE_MS) {
        markDrawn();
        return;
      }

      timer = setTimeout(() => waitForStillness(current, agreed, startedAt), SAMPLE_MS);
    };

    // `document.fonts` is missing in older browsers and in jsdom; a page that
    // cannot ask about fonts should still say it is drawn. The feature check
    // is the whole line, which the compat rule cannot see -- and the browser
    // doing the photographing is a current Chromium in any case.
    // eslint-disable-next-line compat/compat
    const fonts = document.fonts ? document.fonts.ready : Promise.resolve();

    const settle = () => {
      clearTimeout(timer);
      document.documentElement.removeAttribute(SCREENSHOT_ATTRIBUTE);
      waitForStillness(null, 0, Date.now());
    };

    fonts.then(() => {
      if (!cancelled) {
        settle();
      }
    });

    /*
      Saying it again after the window changes size.

      A full-page capture is not a photograph of the page as it stands: the
      renderer stretches the viewport to the whole document height and then
      shoots. That resize re-lays-out every chart, and ECharts redraws
      asynchronously -- so the picture was taken while fifty-four canvases
      were mid-repaint, and came back with the tiles drawn and the charts
      missing. Nothing about the page's own readiness was wrong, which is why
      three attempts at making *that* stricter changed nothing.

      So a resize withdraws "drawn" and settles again, and the renderer waits
      for it a second time after it has resized.
    */
    window.addEventListener("resize", settle);

    return () => {
      cancelled = true;
      clearTimeout(timer);
      window.removeEventListener("resize", settle);
      document.documentElement.removeAttribute(SCREENSHOT_ATTRIBUTE);
    };
  }, [ready]);
}
