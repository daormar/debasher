import { describe, expect, it } from "vitest";
import { residentProcessStatus } from "./processStatus";

describe("residentProcessStatus", () => {
  it("shows UNFINISHED_BUT_RUNNABLE as UNFINISHED, and every other status as it is", () => {
    expect(residentProcessStatus("UNFINISHED_BUT_RUNNABLE")).toBe("UNFINISHED");
    expect(residentProcessStatus("IN-PROGRESS")).toBe("IN-PROGRESS");
    expect(residentProcessStatus(undefined)).toBeUndefined();
  });
});
