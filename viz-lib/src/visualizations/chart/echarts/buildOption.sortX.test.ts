import getOptions from "../getOptions";
import buildOption from "./buildOption";

/*
  A line is only a line if its points are joined in x order.

  A category axis has always had this: every series is aligned to one sorted
  category list. A time or value axis had nothing, so the points were joined in
  the order the rows arrived -- and a query with no ORDER BY drew a line running
  backwards and forwards across the chart. A stream query is exactly that case:
  the window comes back in whatever order the engine chose.
*/
function lineOptions(overrides: any = {}) {
  return getOptions({ globalSeriesType: "line", ...overrides });
}

const UNSORTED = [
  {
    name: "north",
    type: "line",
    data: [
      { x: 3000, y: 30 },
      { x: 1000, y: 10 },
      { x: 2000, y: 20 },
    ],
  },
];

function xs(built: any, index = 0) {
  return built.option.series[index].data.map((point: any) => (Array.isArray(point) ? point[0] : point.value[0]));
}

describe("points on a non-category axis", () => {
  test("are joined in x order, whatever order the rows came in", () => {
    const option = buildOption(UNSORTED, lineOptions({ xAxis: { type: "datetime" } }));

    expect(xs(option)).toEqual([1000, 2000, 3000]);
  });

  test("and the y values travel with their own x", () => {
    const option = buildOption(UNSORTED, lineOptions({ xAxis: { type: "datetime" } }));
    const ys = option.option.series[0].data.map((point: any) => (Array.isArray(point) ? point[1] : point.value[1]));

    expect(ys).toEqual([10, 20, 30]);
  });

  test("a numeric axis is sorted as numbers, not as text", () => {
    const option = buildOption(
      [
        {
          name: "a",
          type: "line",
          data: [
            { x: 100, y: 1 },
            { x: 9, y: 2 },
            { x: 80, y: 3 },
          ],
        },
      ],
      lineOptions({ xAxis: { type: "linear" } })
    );

    expect(xs(option)).toEqual([9, 80, 100]);
  });

  // Somebody who turns sorting off is asking to plot a path in the order the
  // rows came -- a trajectory rather than a function of x.
  test("unless sorting was deliberately turned off", () => {
    const option = buildOption(UNSORTED, lineOptions({ sortX: false, xAxis: { type: "datetime" } }));

    expect(xs(option)).toEqual([3000, 1000, 2000]);
  });
});
