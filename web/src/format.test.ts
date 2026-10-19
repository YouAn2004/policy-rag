import { describe, expect, it } from "vitest";
import { flagReasons, normaliseLabel, pct, splitAnswer, splitEmails, splitLine } from "./format";

describe("citation parsing", () => {
  it("normalises label spellings", () => {
    expect(normaliseLabel("POL-02 v3.1 §1.1")).toBe("POL-02 §1.1");
    expect(normaliseLabel("pol-02 §1.1")).toBe("POL-02 §1.1");
    expect(normaliseLabel("POL-04 Table: Approval matrix")).toBe("POL-04 Table: Approval matrix");
  });

  it("splits text and citation chips", () => {
    expect(splitLine("You get 16 days [POL-02 §1.1].")).toEqual([
      { kind: "text", text: "You get 16 days " },
      { kind: "cite", label: "POL-02 §1.1" },
      { kind: "text", text: "." },
    ]);
  });

  it("handles several labels in one bracket", () => {
    const pieces = splitLine("Sick leave [POL-02 §3.1, POL-02 §3.2] applies.");
    expect(pieces.filter((p) => p.kind === "cite")).toHaveLength(2);
  });

  it("leaves brackets that are not citations alone", () => {
    expect(splitLine("See [the form] for details")).toEqual([{ kind: "text", text: "See [the form] for details" }]);
  });

  it("keeps numbered lines as separate paragraphs", () => {
    expect(splitAnswer("1. First [POL-02 §1.1].\n\n2. Second")).toHaveLength(2);
  });
});

describe("helpers", () => {
  it("formats percentages and gaps", () => {
    expect(pct(0.857)).toBe("86%");
    expect(pct(null)).toBe("n/a");
  });

  it("explains a flagged answer", () => {
    const reasons = flagReasons({
      invalid_citations: [],
      uncited: false,
      unsupported_numbers: ["12"],
      llm_support: { supported: false, problems: ["Not supported by the clause."] },
    });
    expect(reasons).toHaveLength(2);
    expect(reasons[0]).toContain("12");
  });

  it("finds e-mail addresses", () => {
    expect(splitEmails("Please contact HR at hr@meridianworks.example.")).toEqual([
      { text: "Please contact HR at ", email: false },
      { text: "hr@meridianworks.example", email: true },
      { text: ".", email: false },
    ]);
  });
});
