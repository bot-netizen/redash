import { buildTooltipFormatter, buildBoxTooltipFormatter } from "./buildOption";

describe("chart tooltips", () => {
  const options = { numberFormat: "0,0.00", percentFormat: "0%", series: {}, textFormat: null };

  test("a series named with markup is shown as text", () => {
    const html = buildTooltipFormatter(
      options,
      false
    )([{ marker: "", seriesName: '<img src="x" onerror="alert(1)">', axisValueLabel: "<b>2024</b>", value: [0, 5] }]);

    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img");
    expect(html).not.toContain("<b>2024</b>");
  });

  test("and in a boxplot's", () => {
    const html = buildBoxTooltipFormatter(options)({
      marker: "",
      seriesName: "<script>1</script>",
      name: "<i>x</i>",
      value: [0, 1, 2, 3, 4, 5],
    });

    expect(html).not.toContain("<script>");
    expect(html).not.toContain("<i>");
  });
});
