/*
  A line diff, for showing what one version of a query changed.

  Written here rather than taken from a package. The only diff library in the
  tree is one of webpack's own transitive dependencies, which would vanish the
  next time the lockfile moves, and this is thirty lines for a job measured in
  tens of lines of SQL: the longest common subsequence, then a walk back
  through it.

  `LIMIT` is a guard, not a judgement about SQL: the table is lines x lines, and
  a pasted query of ten thousand lines would ask for a hundred million cells.
  Past it the two versions are reported as wholly different, which is honest
  and costs nothing.
*/

export const LIMIT = 2000;

function lines(text) {
  // A trailing newline otherwise reads as a blank line somebody added.
  return (text || "").replace(/\n$/, "").split("\n");
}

function table(before, after) {
  const lengths = [];
  for (let i = 0; i <= before.length; i += 1) {
    lengths.push(new Array(after.length + 1).fill(0));
  }
  for (let i = before.length - 1; i >= 0; i -= 1) {
    for (let j = after.length - 1; j >= 0; j -= 1) {
      lengths[i][j] =
        before[i] === after[j] ? lengths[i + 1][j + 1] + 1 : Math.max(lengths[i + 1][j], lengths[i][j + 1]);
    }
  }
  return lengths;
}

/**
 * The lines of `after`, each marked against `before`.
 *
 * Returns `{ type, text }` in reading order, where type is "same", "added" or
 * "removed" — removed lines are kept in place so a change reads as a change
 * rather than as an unexplained gap.
 */
export default function diffLines(before, after) {
  const left = lines(before);
  const right = lines(after);

  if (left.length > LIMIT || right.length > LIMIT) {
    return [...left.map((text) => ({ type: "removed", text })), ...right.map((text) => ({ type: "added", text }))];
  }

  const lengths = table(left, right);
  const out = [];
  let i = 0;
  let j = 0;
  while (i < left.length && j < right.length) {
    if (left[i] === right[j]) {
      out.push({ type: "same", text: left[i] });
      i += 1;
      j += 1;
    } else if (lengths[i + 1][j] >= lengths[i][j + 1]) {
      out.push({ type: "removed", text: left[i] });
      i += 1;
    } else {
      out.push({ type: "added", text: right[j] });
      j += 1;
    }
  }
  while (i < left.length) {
    out.push({ type: "removed", text: left[i] });
    i += 1;
  }
  while (j < right.length) {
    out.push({ type: "added", text: right[j] });
    j += 1;
  }
  return out;
}

/** Whether a diff holds any change at all. */
export function unchanged(diff) {
  return diff.every((line) => line.type === "same");
}
