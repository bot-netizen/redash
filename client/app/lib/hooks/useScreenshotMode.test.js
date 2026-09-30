import { everyWidgetHasFinished } from "./useScreenshotMode";

/*
  The renderer waits for the page to say it has drawn. Saying so too early is
  not a slightly-early picture: it is a picture of an empty grid, because an
  empty page is perfectly still and the settling check agrees with it.

  Measured on a dashboard of eighty widgets: the same URL captured 3.1 MB or
  1.7 MB depending on which side of the race it landed, about half and half.
*/
describe("when a dashboard is worth photographing", () => {
  const loaded = (id) => ({ id, visualization: { id }, loading: false, data: { rows: [] } });
  const loading = (id) => ({ id, visualization: { id }, loading: true, data: undefined });
  const notStarted = (id) => ({ id, visualization: { id }, loading: false, data: undefined });
  const textbox = (id) => ({ id, visualization: null, text: "hello" });

  test("not before the widgets have started", () => {
    // The bug this replaced: `!widget.loading` is true before loading begins,
    // so the page announced itself drawn on its very first render.
    expect(everyWidgetHasFinished([notStarted(1), notStarted(2)])).toBe(false);
  });

  test("not while one is still loading", () => {
    expect(everyWidgetHasFinished([loaded(1), loading(2)])).toBe(false);
  });

  test("once they all have something to show", () => {
    expect(everyWidgetHasFinished([loaded(1), loaded(2)])).toBe(true);
  });

  test("an error counts as something to show", () => {
    // A widget whose query failed draws a red box. That is a real picture of
    // a real dashboard, and waiting for it to succeed would wait for ever.
    expect(everyWidgetHasFinished([{ visualization: { id: 1 }, loading: false, data: new Error("nope") }])).toBe(true);
  });

  test("a textbox has no query and is never waited for", () => {
    expect(everyWidgetHasFinished([textbox(1)])).toBe(true);
    expect(everyWidgetHasFinished([textbox(1), loading(2)])).toBe(false);
  });

  test("an empty dashboard is ready at once", () => {
    expect(everyWidgetHasFinished([])).toBe(true);
    expect(everyWidgetHasFinished(undefined)).toBe(true);
  });
});
