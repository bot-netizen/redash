import { chartDrawn, chartMounted, chartsStillDrawing, resetChartsForTests } from "./charts";

/*
  The page being photographed waits on this. Getting it wrong in either
  direction is expensive: too eager and the picture is a grid of empty
  rectangles, too cautious and every capture waits out its deadline.
*/
describe("knowing when the charts have drawn", () => {
  beforeEach(() => resetChartsForTests());

  test("a page with no charts is waiting for nothing", () => {
    expect(chartsStillDrawing()).toBe(0);
  });

  test("a chart that has mounted is one to wait for", () => {
    chartMounted();

    expect(chartsStillDrawing()).toBe(1);
  });

  test("counted from the container, not from the chart being created", () => {
    // A chart still waiting to come on screen has no ECharts instance yet and
    // is still one the page is waiting for. Counting from creation would say
    // "nothing pending" for a dashboard whose charts are all below the fold --
    // exactly the case that produced blank captures.
    chartMounted();
    chartMounted();

    expect(chartsStillDrawing()).toBe(2);
  });

  test("and stops being one once it says it has drawn", () => {
    const first = chartMounted();
    const second = chartMounted();

    chartDrawn(first.token);
    expect(chartsStillDrawing()).toBe(1);

    chartDrawn(second.token);
    expect(chartsStillDrawing()).toBe(0);
  });

  test("saying so twice is harmless", () => {
    // ECharts reports `finished` on every render, not only the first.
    const { token } = chartMounted();

    chartDrawn(token);
    chartDrawn(token);

    expect(chartsStillDrawing()).toBe(0);
  });

  test("a chart that goes away stops being waited for", () => {
    // Otherwise a dashboard somebody is editing never looks finished.
    const { dispose } = chartMounted();
    expect(chartsStillDrawing()).toBe(1);

    dispose();

    expect(chartsStillDrawing()).toBe(0);
  });

  test("a token from a chart that has gone is ignored", () => {
    const { token, dispose } = chartMounted();
    dispose();

    chartDrawn(token); // must not resurrect it

    expect(chartsStillDrawing()).toBe(0);
  });

  test("two charts get different tokens", () => {
    // Sharing one would let the first to finish answer for both.
    const first = chartMounted();
    const second = chartMounted();

    expect(first.token).not.toBe(second.token);
  });
});
