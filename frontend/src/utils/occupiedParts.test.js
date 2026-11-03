import { describe, expect, it } from "vitest";
import occupiedParts from "./occupiedParts.js";

// SCRUM-84: the pages that show a booking's setup and turnaround use this text.
describe("occupiedParts", () => {
  it("gives clock times for a part within one day", () => {
    expect(occupiedParts({
      setup: { start: "2027-03-12T09:30:00", end: "2027-03-12T10:00:00" },
      turnaround: { start: "2027-03-12T12:00:00", end: "2027-03-12T12:45:00" },
    })).toBe("setup 09:30 to 10:00, turnaround 12:00 to 12:45");
  });

  it("gives dates as well for a part that crosses midnight", () => {
    expect(occupiedParts({
      setup: { start: "2027-03-11T23:30:00", end: "2027-03-12T00:30:00" },
    })).toBe("setup 2027-03-11 23:30 to 2027-03-12 00:30");
  });

  it("is empty when there is neither", () => {
    expect(occupiedParts({})).toBe("");
  });
});
