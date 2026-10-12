import { describe, expect, it } from "vitest";

import {
  CLOSE_BAD_TICKET,
  CLOSE_NORMAL,
  CLOSE_TAKEN_OVER,
  closeQuestion,
  endingNotice,
  exitStatusOf,
  refusalNotice,
  resizeMessage,
} from "./claudeTerminal";

describe("claudeTerminal", () => {

  it("reads the exit status of the control message of the backend, and nothing else", () => {
    expect(exitStatusOf('{"exit": 0}')).toBe(0);
    expect(exitStatusOf('{"exit": -9}')).toBe(-9);
    expect(exitStatusOf('{"exit": "0"}')).toBeNull();
    expect(exitStatusOf('{"other": 1}')).toBeNull();
    expect(exitStatusOf("null")).toBeNull();
    expect(exitStatusOf("not json")).toBeNull();
  });

  it("gives the size of the terminal as the backend reads it", () => {
    expect(JSON.parse(resizeMessage(120, 30))).toEqual({ resize: [120, 30] });
  });

  it("says why a session ended", () => {
    expect(endingNotice(CLOSE_NORMAL, 0)).toBe("Claude Code ended.");
    expect(endingNotice(CLOSE_NORMAL, 3)).toBe("Claude Code ended with exit status 3.");
    expect(endingNotice(CLOSE_NORMAL, -9)).toBe("Claude Code ended, killed by signal 9.");
    expect(endingNotice(CLOSE_TAKEN_OVER, null)).toBe("The session was opened in another page.");
    expect(endingNotice(CLOSE_BAD_TICKET, null)).toMatch(/could not open/);
    expect(endingNotice(1006, null)).toMatch(/connection to the backend was lost/);
    expect(endingNotice(CLOSE_NORMAL, null)).toMatch(/connection to the backend was lost/);
  });

  it("says why a session could not start", () => {
    expect(refusalNotice(404, "No program is saved in '/p'")).toMatch(/save this one first/);
    expect(refusalNotice(409, "")).toBe("Claude Code is already open on this program in another page.");
    expect(refusalNotice(503, "debasher_claude is not installed with this backend"))
      .toBe("debasher_claude is not installed with this backend.");
    expect(refusalNotice(503, "")).toBe("Claude Code cannot run in the page here.");
    expect(refusalNotice(500, "boom")).toBe("The session could not start (500): boom.");
  });

  it("asks before closing only what would be lost", () => {
    expect(closeQuestion(false, false)).toBeNull();
    expect(closeQuestion(true, false)).toMatch(/changes made since it was last saved are lost\.$/);
    expect(closeQuestion(false, true)).toBe("Close the program? The session of Claude Code ends.");
    expect(closeQuestion(true, true)).toMatch(/are lost, and the session of Claude Code ends\.$/);
  });

});
