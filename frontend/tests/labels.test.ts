import { describe, expect, it } from "vitest";
import { maskPhone, pct } from "../src/services/labels";

describe("labels", () => {
  it("shows undefined rates as a dash, not 0%", () => {
    expect(pct(null)).toBe("—");
    expect(pct(0)).toBe("0%");
    expect(pct(0.1234)).toBe("12.3%");
  });
  it("masks phone numbers", () => {
    expect(maskPhone("+15550100100")).toBe("+15•••••••00");
  });
});
