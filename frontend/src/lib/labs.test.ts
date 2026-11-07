import { describe, expect, it } from "vitest";
import { detectLabs, labBadgeClass, labsToText } from "@/lib/labs";

describe("detectLabs", () => {
  it("calls a researcher with no affiliation independent", () => {
    expect(detectLabs([])).toEqual(["Independent"]);
  });

  it("recognises institutions from their full names and abbreviations", () => {
    expect(detectLabs(["Massachusetts Institute of Technology"])).toEqual(["MIT"]);
    expect(detectLabs(["Dept. of CS, MIT"])).toEqual(["MIT"]);
    expect(detectLabs(["University of California, Santa Barbara"])).toEqual(["UCSB"]);
  });

  it("names the UC campus without the generic UC badge", () => {
    expect(detectLabs(["University of California, Santa Barbara"])).toEqual(["UCSB"]);
    expect(detectLabs(["University of California, Riverside"])).toEqual(["UC"]);
  });

  it("lists every lab once across several affiliations", () => {
    const labs = detectLabs(["Stanford University", "Google Research", "Stanford AI Lab"]);
    expect(labs).toContain("Stanford");
    expect(labs).toContain("Google Research");
    expect(labs.filter((l) => l === "Stanford")).toHaveLength(1);
  });

  it("does not match an abbreviation inside another word", () => {
    // "submit" contains "mit" but is not MIT.
    expect(detectLabs(["we submit our findings to the committee for review"])).toEqual(["Independent"]);
  });

  it("shows a short unknown institution name as is", () => {
    expect(detectLabs(["Acme Institute"])).toEqual(["Acme Institute"]);
  });

  it("shortens a long unknown institution name", () => {
    const [label] = detectLabs(["Zyxwv Qrstu Institute For Advanced Things"]);
    expect(label.endsWith("…")).toBe(true);
    expect(label.length).toBeLessThanOrEqual(31);
  });

  it("treats prose in the affiliation field as independent", () => {
    expect(detectLabs(["who are the foundation of every existing enforcement system"])).toEqual([
      "Independent",
    ]);
  });
});

describe("labsToText", () => {
  it("reads naturally for an independent researcher", () => {
    expect(labsToText([])).toBe("an independent researcher");
  });

  it("joins several labs with a dot", () => {
    expect(labsToText(["Harvard University", "Yale University"])).toBe("Harvard · Yale");
  });
});

describe("labBadgeClass", () => {
  it("uses the lab's own colour, or a default", () => {
    expect(labBadgeClass("OpenAI")).toContain("emerald");
    expect(labBadgeClass("Somewhere Unknown")).toBeTruthy();
  });
});
