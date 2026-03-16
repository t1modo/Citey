/**
 * Institution / research-lab detection helpers.
 * Shared between the dashboard citation cards and the nav bell dropdown.
 *
 * RULES is the single source of truth for detection. To add a new institution:
 *   1. Add a rule tuple: [test function, display label]
 *   2. Optionally add a color entry in LAB_COLORS (defaults to purple).
 */

export const LAB_COLORS: Record<string, string> = {
  // Industry
  "FAIR":               "bg-blue-500/15 text-blue-300 border-blue-500/20",
  "Meta AI":            "bg-blue-500/15 text-blue-300 border-blue-500/20",
  "DeepMind":           "bg-indigo-500/15 text-indigo-300 border-indigo-500/20",
  "Google DeepMind":    "bg-indigo-500/15 text-indigo-300 border-indigo-500/20",
  "Google Research":    "bg-green-500/15 text-green-300 border-green-500/20",
  "Google Brain":       "bg-green-500/15 text-green-300 border-green-500/20",
  "OpenAI":             "bg-emerald-500/15 text-emerald-300 border-emerald-500/20",
  "Anthropic":          "bg-orange-500/15 text-orange-300 border-orange-500/20",
  "Microsoft Research": "bg-sky-500/15 text-sky-300 border-sky-500/20",
  "Microsoft":          "bg-sky-500/15 text-sky-300 border-sky-500/20",
  "IBM Research":       "bg-blue-600/15 text-blue-400 border-blue-600/20",
  "IBM":                "bg-blue-600/15 text-blue-400 border-blue-600/20",
  "Allen Institute for AI": "bg-orange-500/15 text-orange-300 border-orange-500/20",
  "AI2":                "bg-orange-500/15 text-orange-300 border-orange-500/20",
  "NVIDIA":             "bg-green-600/15 text-green-400 border-green-600/20",
  "NVIDIA Research":    "bg-green-600/15 text-green-400 border-green-600/20",
  "Hugging Face":       "bg-yellow-500/15 text-yellow-300 border-yellow-500/20",
  "Amazon":             "bg-orange-600/15 text-orange-400 border-orange-600/20",
  "AWS":                "bg-orange-600/15 text-orange-400 border-orange-600/20",
  "Apple":              "bg-gray-500/15 text-gray-300 border-gray-500/20",
  "Adobe":              "bg-red-500/15 text-red-300 border-red-500/20",
  "Salesforce":         "bg-blue-500/15 text-blue-300 border-blue-500/20",
  "Salesforce Research":"bg-blue-500/15 text-blue-300 border-blue-500/20",
  "Samsung":            "bg-blue-600/15 text-blue-400 border-blue-600/20",
  "Baidu":              "bg-blue-500/15 text-blue-300 border-blue-500/20",
  "Tencent":            "bg-teal-500/15 text-teal-300 border-teal-500/20",
  "Alibaba":            "bg-orange-500/15 text-orange-300 border-orange-500/20",
  "ByteDance":          "bg-red-500/15 text-red-300 border-red-500/20",
  "Huawei":             "bg-red-600/15 text-red-400 border-red-600/20",
  "Intel":              "bg-blue-600/15 text-blue-400 border-blue-600/20",
  "Qualcomm":           "bg-blue-500/15 text-blue-300 border-blue-500/20",
  "Sony":               "bg-gray-600/15 text-gray-400 border-gray-600/20",
  "Mila":               "bg-purple-500/15 text-purple-300 border-purple-500/20",
  "Vector Institute":   "bg-purple-500/15 text-purple-300 border-purple-500/20",
  "INRIA":              "bg-blue-500/15 text-blue-300 border-blue-500/20",
  "CNRS":               "bg-blue-600/15 text-blue-400 border-blue-600/20",
  "Max Planck Institute": "bg-indigo-500/15 text-indigo-300 border-indigo-500/20",
  // US Universities
  "MIT":          "bg-red-500/15 text-red-300 border-red-500/20",
  "Stanford":     "bg-red-600/15 text-red-400 border-red-600/20",
  "CMU":          "bg-red-700/15 text-red-400 border-red-700/20",
  "Harvard":      "bg-red-700/15 text-red-400 border-red-700/20",
  "Princeton":    "bg-orange-600/15 text-orange-400 border-orange-600/20",
  "Yale":         "bg-blue-700/15 text-blue-400 border-blue-700/20",
  "Cornell":      "bg-red-600/15 text-red-400 border-red-600/20",
  "Columbia":     "bg-blue-600/15 text-blue-400 border-blue-600/20",
  "NYU":          "bg-purple-500/15 text-purple-300 border-purple-500/20",
  "UPenn":        "bg-blue-600/15 text-blue-400 border-blue-600/20",
  "Johns Hopkins":"bg-blue-600/15 text-blue-400 border-blue-600/20",
  "Duke":         "bg-blue-700/15 text-blue-400 border-blue-700/20",
  "Dartmouth":    "bg-green-700/15 text-green-400 border-green-700/20",
  "Northwestern": "bg-purple-600/15 text-purple-400 border-purple-600/20",
  "UNC":          "bg-sky-600/15 text-sky-400 border-sky-600/20",
  "Notre Dame":   "bg-blue-700/15 text-blue-400 border-blue-700/20",
  "Georgetown":   "bg-blue-700/15 text-blue-400 border-blue-700/20",
  "Vanderbilt":   "bg-yellow-700/15 text-yellow-400 border-yellow-700/20",
  "Emory":        "bg-blue-600/15 text-blue-400 border-blue-600/20",
  "Tufts":        "bg-blue-600/15 text-blue-400 border-blue-600/20",
  "Brown":        "bg-red-700/15 text-red-400 border-red-700/20",
  "Rice":         "bg-blue-700/15 text-blue-400 border-blue-700/20",
  "UC Berkeley":  "bg-amber-500/15 text-amber-300 border-amber-500/20",
  "UCLA":         "bg-amber-500/15 text-amber-300 border-amber-500/20",
  "UCSD":         "bg-amber-500/15 text-amber-300 border-amber-500/20",
  "UCSB":         "bg-amber-500/15 text-amber-300 border-amber-500/20",
  "UC Davis":     "bg-amber-500/15 text-amber-300 border-amber-500/20",
  "UC Irvine":    "bg-amber-500/15 text-amber-300 border-amber-500/20",
  "UCSF":         "bg-teal-600/15 text-teal-400 border-teal-600/20",
  "UC":           "bg-amber-500/15 text-amber-300 border-amber-500/20",
  "UW":           "bg-purple-600/15 text-purple-400 border-purple-600/20",
  "U. Michigan":  "bg-yellow-600/15 text-yellow-400 border-yellow-600/20",
  "UIUC":         "bg-orange-600/15 text-orange-400 border-orange-600/20",
  "Georgia Tech": "bg-yellow-500/15 text-yellow-300 border-yellow-500/20",
  "UT Austin":    "bg-orange-600/15 text-orange-400 border-orange-600/20",
  "Ohio State":   "bg-red-700/15 text-red-400 border-red-700/20",
  "Penn State":   "bg-blue-700/15 text-blue-400 border-blue-700/20",
  "Purdue":       "bg-yellow-700/15 text-yellow-400 border-yellow-700/20",
  "UMD":          "bg-red-600/15 text-red-400 border-red-600/20",
  "U. Florida":   "bg-orange-600/15 text-orange-400 border-orange-600/20",
  "USC":          "bg-red-600/15 text-red-400 border-red-600/20",
  "Virginia Tech":"bg-orange-700/15 text-orange-400 border-orange-700/20",
  "Caltech":      "bg-orange-500/15 text-orange-300 border-orange-500/20",
  "Boston University": "bg-red-600/15 text-red-400 border-red-600/20",
  "Northeastern": "bg-red-500/15 text-red-300 border-red-500/20",
  "U. Chicago":   "bg-red-700/15 text-red-400 border-red-700/20",
  "UVA":          "bg-orange-600/15 text-orange-400 border-orange-600/20",
  // International
  "Oxford":          "bg-blue-700/15 text-blue-400 border-blue-700/20",
  "Cambridge":       "bg-blue-700/15 text-blue-400 border-blue-700/20",
  "ETH Zürich":      "bg-red-500/15 text-red-300 border-red-500/20",
  "EPFL":            "bg-red-500/15 text-red-300 border-red-500/20",
  "UCL":             "bg-purple-600/15 text-purple-400 border-purple-600/20",
  "Imperial College":"bg-blue-700/15 text-blue-400 border-blue-700/20",
  "Edinburgh":       "bg-purple-700/15 text-purple-400 border-purple-700/20",
  "TU Munich":       "bg-blue-600/15 text-blue-400 border-blue-600/20",
  "RWTH Aachen":     "bg-blue-600/15 text-blue-400 border-blue-600/20",
  "KU Leuven":       "bg-blue-700/15 text-blue-400 border-blue-700/20",
  "Sorbonne":        "bg-blue-700/15 text-blue-400 border-blue-700/20",
  "U. Toronto":      "bg-blue-600/15 text-blue-400 border-blue-600/20",
  "UBC":             "bg-blue-700/15 text-blue-400 border-blue-700/20",
  "McGill":          "bg-red-600/15 text-red-400 border-red-600/20",
  "UdeM":            "bg-blue-600/15 text-blue-400 border-blue-600/20",
  "NUS":             "bg-red-600/15 text-red-400 border-red-600/20",
  "NTU":             "bg-red-500/15 text-red-300 border-red-500/20",
  "SUTD":            "bg-violet-500/15 text-violet-300 border-violet-500/20",
  "KAIST":           "bg-blue-600/15 text-blue-400 border-blue-600/20",
  "POSTECH":         "bg-blue-600/15 text-blue-400 border-blue-600/20",
  "SNU":             "bg-blue-600/15 text-blue-400 border-blue-600/20",
  "Tsinghua":        "bg-purple-600/15 text-purple-400 border-purple-600/20",
  "PKU":             "bg-red-600/15 text-red-400 border-red-600/20",
  "Fudan":           "bg-blue-700/15 text-blue-400 border-blue-700/20",
  "ZJU":             "bg-blue-600/15 text-blue-400 border-blue-600/20",
  "SJTU":            "bg-red-600/15 text-red-400 border-red-600/20",
  "HKUST":           "bg-teal-600/15 text-teal-400 border-teal-600/20",
  "HKU":             "bg-green-700/15 text-green-400 border-green-700/20",
  "CUHK":            "bg-purple-600/15 text-purple-400 border-purple-600/20",
  "ANU":             "bg-red-600/15 text-red-400 border-red-600/20",
  "U. Melbourne":    "bg-blue-700/15 text-blue-400 border-blue-700/20",
  "Monash":          "bg-blue-600/15 text-blue-400 border-blue-600/20",
  "Technion":        "bg-blue-600/15 text-blue-400 border-blue-600/20",
  "Weizmann Institute": "bg-indigo-500/15 text-indigo-300 border-indigo-500/20",
  "Hebrew University":  "bg-blue-600/15 text-blue-400 border-blue-600/20",
  "CAS":             "bg-red-600/15 text-red-400 border-red-600/20",
  "Independent":     "bg-gray-500/15 text-gray-400 border-gray-500/20",
};

type Rule = [(t: string) => boolean, string];

/**
 * Ordered detection rules. Each entry is [testFn, displayLabel].
 * More-specific rules must come before their general counterparts
 * (e.g. "Google DeepMind" before "DeepMind").
 *
 * The test function receives the full affiliation text joined and lowercased.
 * To add a new institution: append a rule tuple and (optionally) a LAB_COLORS entry.
 */
const RULES: Rule[] = [
  // ── Industry labs ────────────────────────────────────────────────────────
  [t => t.includes("google deepmind"),                                          "Google DeepMind"],
  [t => t.includes("deepmind"),                                                 "DeepMind"],
  [t => t.includes("google brain"),                                             "Google Brain"],
  [t => t.includes("google research"),                                          "Google Research"],
  [t => t.includes("facebook ai research") || t.includes("fair"),              "FAIR"],
  [t => t.includes("meta ai") || t.includes("meta platforms"),                 "Meta AI"],
  [t => t.includes("openai"),                                                   "OpenAI"],
  [t => t.includes("anthropic"),                                                "Anthropic"],
  [t => t.includes("microsoft research"),                                       "Microsoft Research"],
  [t => t.includes("microsoft"),                                                "Microsoft"],
  [t => t.includes("ibm research"),                                             "IBM Research"],
  [t => t.includes("ibm"),                                                      "IBM"],
  [t => t.includes("allen institute for ai") || t.includes("allenai") || t.includes("ai2"), "Allen Institute for AI"],
  [t => t.includes("nvidia research"),                                          "NVIDIA Research"],
  [t => t.includes("nvidia"),                                                   "NVIDIA"],
  [t => t.includes("hugging face"),                                             "Hugging Face"],
  [t => t.includes("amazon web services") || t.includes("aws"),                "AWS"],
  [t => t.includes("amazon"),                                                   "Amazon"],
  [t => t.includes("apple"),                                                    "Apple"],
  [t => t.includes("adobe"),                                                    "Adobe"],
  [t => t.includes("salesforce research"),                                      "Salesforce Research"],
  [t => t.includes("salesforce"),                                               "Salesforce"],
  [t => t.includes("samsung"),                                                  "Samsung"],
  [t => t.includes("baidu"),                                                    "Baidu"],
  [t => t.includes("tencent"),                                                  "Tencent"],
  [t => t.includes("alibaba"),                                                  "Alibaba"],
  [t => t.includes("bytedance"),                                                "ByteDance"],
  [t => t.includes("huawei"),                                                   "Huawei"],
  [t => t.includes("intel"),                                                    "Intel"],
  [t => t.includes("qualcomm"),                                                 "Qualcomm"],
  [t => t.includes("sony"),                                                     "Sony"],
  [t => t.includes("mila"),                                                     "Mila"],
  [t => t.includes("vector institute"),                                         "Vector Institute"],
  [t => t.includes("inria"),                                                    "INRIA"],
  [t => t.includes("cnrs"),                                                     "CNRS"],
  [t => t.includes("max planck institute"),                                     "Max Planck Institute"],
  // ── US Universities ──────────────────────────────────────────────────────
  [t => t.includes("massachusetts institute of technology") || /\bmit\b/.test(t), "MIT"],
  [t => t.includes("stanford"),                                                 "Stanford"],
  [t => t.includes("carnegie mellon") || /\bcmu\b/.test(t),                   "CMU"],
  [t => t.includes("harvard"),                                                  "Harvard"],
  [t => t.includes("princeton"),                                                "Princeton"],
  [t => t.includes("yale"),                                                     "Yale"],
  [t => t.includes("cornell"),                                                  "Cornell"],
  [t => t.includes("columbia university"),                                      "Columbia"],
  [t => t.includes("new york university") || /\bnyu\b/.test(t),               "NYU"],
  [t => t.includes("university of pennsylvania") || /\bupenn\b/.test(t),      "UPenn"],
  [t => t.includes("johns hopkins") || /\bjhu\b/.test(t),                     "Johns Hopkins"],
  [t => t.includes("duke"),                                                     "Duke"],
  [t => t.includes("dartmouth"),                                                "Dartmouth"],
  [t => t.includes("northwestern university"),                                  "Northwestern"],
  [t => t.includes("university of north carolina") || /\bunc\b/.test(t),      "UNC"],
  [t => t.includes("notre dame"),                                               "Notre Dame"],
  [t => t.includes("georgetown"),                                               "Georgetown"],
  [t => t.includes("vanderbilt"),                                               "Vanderbilt"],
  [t => t.includes("emory"),                                                    "Emory"],
  [t => t.includes("tufts"),                                                    "Tufts"],
  [t => t.includes("brown university"),                                         "Brown"],
  [t => t.includes("rice university"),                                          "Rice"],
  // UC system — specific campuses before the generic fallback
  [t => t.includes("uc berkeley") || t.includes("university of california, berkeley") || t.includes("university of california berkeley"), "UC Berkeley"],
  [t => t.includes("university of california, los angeles") || /\bucla\b/.test(t),    "UCLA"],
  [t => t.includes("university of california, san diego") || /\bucsd\b/.test(t),      "UCSD"],
  [t => t.includes("university of california, santa barbara") || /\bucsb\b/.test(t),  "UCSB"],
  [t => t.includes("university of california, davis") || t.includes("uc davis"),       "UC Davis"],
  [t => t.includes("university of california, irvine") || t.includes("uc irvine"),     "UC Irvine"],
  [t => t.includes("university of california, san francisco") || /\bucsf\b/.test(t),  "UCSF"],
  [t => t.includes("university of california"),                                 "UC"],
  [t => t.includes("university of washington") || /\buw\b/.test(t),           "UW"],
  [t => t.includes("university of michigan") || t.includes("u. michigan"),     "U. Michigan"],
  [t => t.includes("university of illinois") || /\buiuc\b/.test(t),           "UIUC"],
  [t => t.includes("georgia institute of technology") || t.includes("georgia tech"), "Georgia Tech"],
  [t => t.includes("university of texas") || t.includes("ut austin"),          "UT Austin"],
  [t => t.includes("ohio state"),                                               "Ohio State"],
  [t => t.includes("pennsylvania state") || t.includes("penn state"),          "Penn State"],
  [t => t.includes("purdue"),                                                   "Purdue"],
  [t => t.includes("university of maryland") || /\bumd\b/.test(t),            "UMD"],
  [t => t.includes("university of florida"),                                    "U. Florida"],
  [t => t.includes("university of southern california") || /\busc\b/.test(t), "USC"],
  [t => t.includes("virginia tech") || t.includes("virginia polytechnic"),     "Virginia Tech"],
  [t => t.includes("university of virginia") || /\buva\b/.test(t),            "UVA"],
  [t => t.includes("caltech") || t.includes("california institute of technology"), "Caltech"],
  [t => t.includes("boston university"),                                        "Boston University"],
  [t => t.includes("northeastern university"),                                  "Northeastern"],
  [t => t.includes("university of chicago") || t.includes("u. chicago"),       "U. Chicago"],
  // ── International ────────────────────────────────────────────────────────
  [t => t.includes("oxford"),                                                   "Oxford"],
  [t => t.includes("cambridge"),                                                "Cambridge"],
  [t => t.includes("university college london") || /\bucl\b/.test(t),         "UCL"],
  [t => t.includes("imperial college"),                                         "Imperial College"],
  [t => t.includes("university of edinburgh"),                                  "Edinburgh"],
  [t => t.includes("technical university of munich") || t.includes("technische universität münchen") || t.includes("tu munich") || /\btum\b/.test(t), "TU Munich"],
  [t => t.includes("rwth aachen"),                                              "RWTH Aachen"],
  [t => t.includes("ku leuven"),                                                "KU Leuven"],
  [t => t.includes("sorbonne"),                                                 "Sorbonne"],
  [t => t.includes("eth zürich") || t.includes("eth zurich"),                  "ETH Zürich"],
  [t => /\bepfl\b/.test(t),                                                    "EPFL"],
  [t => t.includes("university of toronto") || t.includes("u. toronto"),       "U. Toronto"],
  [t => t.includes("university of british columbia") || /\bubc\b/.test(t),    "UBC"],
  [t => t.includes("mcgill"),                                                   "McGill"],
  [t => t.includes("université de montréal") || t.includes("university of montreal") || t.includes("udem"), "UdeM"],
  [t => t.includes("national university of singapore") || /\bnus\b/.test(t),  "NUS"],
  [t => t.includes("nanyang technological") || /\bntu\b/.test(t),             "NTU"],
  [t => t.includes("singapore university of technology") || /\bsutd\b/.test(t), "SUTD"],
  [t => /\bkaist\b/.test(t),                                                   "KAIST"],
  [t => /\bpostech\b/.test(t),                                                 "POSTECH"],
  [t => t.includes("seoul national"),                                           "SNU"],
  [t => t.includes("tsinghua"),                                                 "Tsinghua"],
  [t => t.includes("peking university") || /\bpku\b/.test(t),                 "PKU"],
  [t => t.includes("fudan"),                                                    "Fudan"],
  [t => t.includes("zhejiang university") || /\bzju\b/.test(t),               "ZJU"],
  [t => t.includes("shanghai jiao tong") || /\bsjtu\b/.test(t),               "SJTU"],
  [t => t.includes("chinese academy of sciences") || /\bcas\b/.test(t),       "CAS"],
  [t => t.includes("hong kong university of science") || /\bhkust\b/.test(t), "HKUST"],
  [t => t.includes("chinese university of hong kong") || /\bcuhk\b/.test(t),  "CUHK"],
  [t => t.includes("university of hong kong") || /\bhku\b/.test(t),           "HKU"],
  [t => t.includes("australian national university") || /\banu\b/.test(t),    "ANU"],
  [t => t.includes("university of melbourne"),                                  "U. Melbourne"],
  [t => t.includes("monash"),                                                   "Monash"],
  [t => t.includes("technion"),                                                 "Technion"],
  [t => t.includes("weizmann"),                                                 "Weizmann Institute"],
  [t => t.includes("hebrew university"),                                        "Hebrew University"],
];

export function labBadgeClass(lab: string): string {
  return LAB_COLORS[lab] ?? "bg-purple-500/15 text-purple-300 border-purple-500/20";
}

/** Map affiliation strings to all recognisable lab/institution labels. */
export function detectLabs(affiliations: string[]): string[] {
  if (!affiliations.length) return ["Independent"];

  const t = affiliations.join(" ").toLowerCase();
  const seen = new Set<string>();
  const labs: string[] = [];

  for (const [test, label] of RULES) {
    if (!seen.has(label) && test(t)) {
      labs.push(label);
      seen.add(label);
    }
  }

  if (labs.length === 0) {
    // Only show the raw affiliation string if it plausibly looks like an
    // institution name: starts with uppercase and is short (≤7 words).
    // Prose text ("who are the foundation of every existing enforcement
    // system") fails both checks and falls through to "Independent".
    const first = affiliations[0].trim();
    const wordCount = first.split(/\s+/).length;
    if (/^[A-Z0-9]/.test(first) && wordCount <= 7) {
      labs.push(first.length > 30 ? first.slice(0, 30).trimEnd() + "…" : first);
    } else {
      labs.push("Independent");
    }
  }

  return labs;
}

/** Format lab names for inline text (e.g. "MIT · Stanford" or "an independent researcher"). */
export function labsToText(affiliations: string[]): string {
  const labs = detectLabs(affiliations);
  if (labs.length === 1 && labs[0] === "Independent") return "an independent researcher";
  return labs.join(" · ");
}
