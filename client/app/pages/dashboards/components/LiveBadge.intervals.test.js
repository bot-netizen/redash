import { intervalsFor, STREAM_INTERVALS, SAVED_INTERVALS, LIVE_INTERVAL_LABELS } from "./LiveBadge";

/*
  Which refresh intervals a dashboard may be set to.

  A streaming board is offered seconds: nothing on it touches a warehouse, so
  the cost of asking often is a DuckDB aggregate. An ordinary one keeps its
  half-minutes, because every refresh there is a query against somebody's
  warehouse -- and a dashboard quietly running those every two seconds is the
  fault this split exists to prevent.
*/
describe("intervalsFor", () => {
  test("a streaming dashboard is offered seconds", () => {
    expect(intervalsFor({ is_streaming: true })).toEqual([2, 5, 10, 20, 30, 60, 120]);
  });

  test("an ordinary one is not", () => {
    expect(intervalsFor({ is_streaming: false })).toEqual([30, 60, 120, 300]);
    expect(intervalsFor({})).toEqual(SAVED_INTERVALS);
  });

  test("and nothing at all defaults to the careful set", () => {
    // The set that cannot hammer a warehouse is the safe thing to guess.
    expect(intervalsFor(null)).toEqual(SAVED_INTERVALS);
  });

  test("a stream is never offered longer than two minutes", () => {
    // One nobody has looked at for two minutes has paused anyway.
    expect(Math.max(...STREAM_INTERVALS)).toBe(120);
  });

  test("every interval offered has words for it", () => {
    // A menu entry reading "Refresh undefined" is how a number gets added to
    // one list and forgotten in the other.
    [...STREAM_INTERVALS, ...SAVED_INTERVALS].forEach((interval) => {
      expect(LIVE_INTERVAL_LABELS[interval]).toEqual(expect.any(String));
    });
  });
});
