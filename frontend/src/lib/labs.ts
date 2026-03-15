/**
 * Institution / research-lab detection helpers.
 * Shared between the dashboard citation cards and the nav bell dropdown.
 */

export const LAB_COLORS: Record<string, string> = {
  "FAIR": "bg-blue-500/15 text-blue-300 border-blue-500/20",
  "Meta AI": "bg-blue-500/15 text-blue-300 border-blue-500/20",
  "DeepMind": "bg-indigo-500/15 text-indigo-300 border-indigo-500/20",
  "Google DeepMind": "bg-indigo-500/15 text-indigo-300 border-indigo-500/20",
  "Google Research": "bg-green-500/15 text-green-300 border-green-500/20",
  "OpenAI": "bg-emerald-500/15 text-emerald-300 border-emerald-500/20",
  "Microsoft Research": "bg-sky-500/15 text-sky-300 border-sky-500/20",
  "Microsoft": "bg-sky-500/15 text-sky-300 border-sky-500/20",
  "IBM Research": "bg-blue-600/15 text-blue-400 border-blue-600/20",
  "IBM": "bg-blue-600/15 text-blue-400 border-blue-600/20",
  "SUTD": "bg-violet-500/15 text-violet-300 border-violet-500/20",
  "AI2": "bg-orange-500/15 text-orange-300 border-orange-500/20",
  "NVIDIA": "bg-green-600/15 text-green-400 border-green-600/20",
  "Hugging Face": "bg-yellow-500/15 text-yellow-300 border-yellow-500/20",
  "Amazon": "bg-orange-600/15 text-orange-400 border-orange-600/20",
  "Apple": "bg-gray-500/15 text-gray-300 border-gray-500/20",
  "MIT": "bg-red-500/15 text-red-300 border-red-500/20",
  "Stanford": "bg-red-600/15 text-red-400 border-red-600/20",
  "CMU": "bg-red-700/15 text-red-400 border-red-700/20",
  "UC Berkeley": "bg-amber-500/15 text-amber-300 border-amber-500/20",
  "UCLA": "bg-amber-500/15 text-amber-300 border-amber-500/20",
  "UCSD": "bg-amber-500/15 text-amber-300 border-amber-500/20",
  "UC": "bg-amber-500/15 text-amber-300 border-amber-500/20",
  "Harvard": "bg-red-700/15 text-red-400 border-red-700/20",
  "Princeton": "bg-orange-600/15 text-orange-400 border-orange-600/20",
  "Oxford": "bg-blue-700/15 text-blue-400 border-blue-700/20",
  "Cambridge": "bg-blue-700/15 text-blue-400 border-blue-700/20",
  "NYU": "bg-purple-500/15 text-purple-300 border-purple-500/20",
  "Columbia": "bg-blue-600/15 text-blue-400 border-blue-600/20",
  "ETH Zurich": "bg-red-500/15 text-red-300 border-red-500/20",
  "EPFL": "bg-red-500/15 text-red-300 border-red-500/20",
  "Yale": "bg-blue-700/15 text-blue-400 border-blue-700/20",
  "UW": "bg-purple-600/15 text-purple-400 border-purple-600/20",
  "U Michigan": "bg-yellow-600/15 text-yellow-400 border-yellow-600/20",
  "UIUC": "bg-orange-600/15 text-orange-400 border-orange-600/20",
  "Georgia Tech": "bg-yellow-500/15 text-yellow-300 border-yellow-500/20",
  "Caltech": "bg-orange-500/15 text-orange-300 border-orange-500/20",
  "U Toronto": "bg-blue-600/15 text-blue-400 border-blue-600/20",
  "Independent": "bg-gray-500/15 text-gray-400 border-gray-500/20",
};

export function labBadgeClass(lab: string): string {
  return LAB_COLORS[lab] ?? "bg-purple-500/15 text-purple-300 border-purple-500/20";
}

/** Map affiliation strings to all recognisable lab/institution labels. */
export function detectLabs(affiliations: string[]): string[] {
  if (!affiliations.length) return ["Independent"];
  const t = affiliations.join(" ").toLowerCase();
  const labs: string[] = [];

  // Industry labs (specific before general)
  if (t.includes("fair") || t.includes("facebook ai research")) labs.push("FAIR");
  else if (t.includes("meta ai") || t.includes("meta platforms")) labs.push("Meta AI");

  if (t.includes("google deepmind")) labs.push("Google DeepMind");
  else if (t.includes("deepmind")) labs.push("DeepMind");

  if (t.includes("google brain") || t.includes("google research")) labs.push("Google Research");
  if (t.includes("openai")) labs.push("OpenAI");
  if (t.includes("microsoft research")) labs.push("Microsoft Research");
  else if (t.includes("microsoft")) labs.push("Microsoft");
  if (t.includes("ibm research")) labs.push("IBM Research");
  else if (t.includes("ibm")) labs.push("IBM");
  if (t.includes("allen institute") || t.includes("allenai")) labs.push("AI2");
  if (t.includes("nvidia")) labs.push("NVIDIA");
  if (t.includes("hugging face")) labs.push("Hugging Face");
  if (t.includes("amazon") || t.includes("aws")) labs.push("Amazon");
  if (t.includes("apple inc") || t.includes("apple, inc") || /\bapple\b/.test(t)) labs.push("Apple");

  // Universities
  if (/\bmit\b/.test(t) || t.includes("massachusetts institute of technology")) labs.push("MIT");
  if (t.includes("stanford")) labs.push("Stanford");
  if (t.includes("carnegie mellon") || /\bcmu\b/.test(t)) labs.push("CMU");
  if (t.includes("uc berkeley") || t.includes("university of california, berkeley") || t.includes("university of california berkeley")) labs.push("UC Berkeley");
  else if (t.includes("university of california, los angeles") || t.includes("ucla")) labs.push("UCLA");
  else if (t.includes("university of california, san diego") || t.includes("ucsd")) labs.push("UCSD");
  else if (t.includes("university of california")) labs.push("UC");
  if (t.includes("harvard")) labs.push("Harvard");
  if (t.includes("princeton")) labs.push("Princeton");
  if (t.includes("oxford")) labs.push("Oxford");
  if (t.includes("cambridge")) labs.push("Cambridge");
  if (t.includes("university of toronto") || t.includes("u of toronto")) labs.push("U Toronto");
  if (t.includes("new york university") || /\bnyu\b/.test(t)) labs.push("NYU");
  if (t.includes("columbia university") || t.includes("columbia, new york")) labs.push("Columbia");
  if (t.includes("eth zürich") || t.includes("eth zurich")) labs.push("ETH Zurich");
  if (/\bepfl\b/.test(t)) labs.push("EPFL");
  if (t.includes("yale")) labs.push("Yale");
  if (t.includes("university of washington") || /\buw\b/.test(t)) labs.push("UW");
  if (t.includes("university of michigan")) labs.push("U Michigan");
  if (t.includes("university of illinois") || /\buiuc\b/.test(t)) labs.push("UIUC");
  if (t.includes("georgia tech") || t.includes("georgia institute of technology")) labs.push("Georgia Tech");
  if (t.includes("caltech") || t.includes("california institute of technology")) labs.push("Caltech");
  if (t.includes("singapore university of technology") || /\bsutd\b/.test(t)) labs.push("SUTD");

  if (labs.length === 0) {
    const first = affiliations[0];
    labs.push(first.length > 28 ? first.slice(0, 28).trimEnd() + "…" : first);
  }

  return labs;
}

/** Format lab names for inline text (e.g. "MIT · Stanford" or "an independent researcher"). */
export function labsToText(affiliations: string[]): string {
  const labs = detectLabs(affiliations);
  if (labs.length === 1 && labs[0] === "Independent") return "an independent researcher";
  return labs.join(" · ");
}
