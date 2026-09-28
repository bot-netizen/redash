import { defaultPopupHtml, defaultTooltipHtml } from "./popups";

describe("a marker's default popup", () => {
  test("shows a cell as text, whatever it contains", () => {
    const html = defaultPopupHtml({ name: '<img src="x" onerror="alert(1)">', n: 3 }, 51.5, -0.1);

    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img");
    expect(html).toContain("<li>n: 3</li>");
  });

  test("the tooltip too", () => {
    expect(defaultTooltipHtml("<b>", 1)).toBe("<strong>&lt;b&gt;, 1</strong>");
  });
});
