import diffLines, { LIMIT, unchanged } from "./diffLines";

/*
  The diff has to be right about three things that a careless one gets wrong:
  an unchanged line in the middle of changes, a line that only moved, and the
  difference between "nothing changed" and "everything changed".
*/
function marked(before, after) {
  return diffLines(before, after).map((line) => `${line.type[0]} ${line.text}`);
}

describe("diffLines", () => {
  test("identical text is all the same", () => {
    expect(marked("select 1\nfrom t", "select 1\nfrom t")).toEqual(["s select 1", "s from t"]);
  });

  test("a changed line is one removal and one addition, in place", () => {
    expect(marked("select 1\nfrom t", "select 2\nfrom t")).toEqual(["r select 1", "a select 2", "s from t"]);
  });

  test("the lines around a change are kept as context", () => {
    const diff = marked("a\nb\nc", "a\nB\nc");

    expect(diff[0]).toBe("s a");
    expect(diff[diff.length - 1]).toBe("s c");
  });

  test("an added line does not mark the rest of the query as changed", () => {
    // The naive line-by-line comparison fails exactly here: inserting one line
    // at the top makes every line after it look different.
    expect(marked("a\nb", "new\na\nb")).toEqual(["a new", "s a", "s b"]);
  });

  test("a deleted line likewise", () => {
    expect(marked("gone\na\nb", "a\nb")).toEqual(["r gone", "s a", "s b"]);
  });

  test("a trailing newline is not a blank line somebody added", () => {
    expect(unchanged(diffLines("select 1", "select 1\n"))).toBe(true);
  });

  test("an empty version against a full one is all additions", () => {
    expect(marked("", "a\nb")).toEqual(["r ", "a a", "a b"]);
  });

  test("past the size guard the two are reported as wholly different", () => {
    const huge = new Array(LIMIT + 1).fill("x").join("\n");
    const diff = diffLines(huge, huge);

    expect(unchanged(diff)).toBe(false);
  });

  test("unchanged says no when anything moved", () => {
    expect(unchanged(diffLines("a", "b"))).toBe(false);
  });
});
