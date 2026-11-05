// Renders the still frame (scripts/citation-field.png, converted to
// public/citation-field.webp) shown when a browser has
// no WebGPU or the visitor prefers reduced motion. Re-run after editing
// src/components/citation-field/citationField.wgsl.
//
//   node scripts/render-citation-poster.mjs
//
// Needs a WebGPU adapter. Without a GPU, install Mesa's software Vulkan driver
// (apt-get install mesa-vulkan-drivers) and run with
// VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json. `npx vgpu doctor`
// diagnoses setup problems.
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { PNG } from "pngjs";
import { init, effect, target } from "vgpu/node";
import { prepareShader } from "@vgpu/wgsl/prepare";

const here = (p) => fileURLToPath(new URL(p, import.meta.url));
const shader = prepareShader(readFileSync(here("../src/components/citation-field/citationField.wgsl"), "utf8"));

const width = 1920;
const height = 1080;
const time = 12.7; // a frame with one arc landing and one in flight

const gpu = await init();
const out = target(gpu, { size: [width, height] });
effect(gpu, shader, {
  set: { params: { time, aspect: width / height, px: 1 / height, intensity: 1, columns: [0.44, 0.075] } },
}).draw(out);
const pixels = await out.color.read({ mipLevel: 0, region: "all" });
gpu.dispose();

const png = new PNG({ width, height });
png.data.set(pixels);
const dest = here("./citation-field.png");
writeFileSync(dest, PNG.sync.write(png, { colorType: 2 }));
console.log(`wrote ${dest}\nConvert for the site, e.g.: cwebp -q 80 ${dest} -o public/citation-field.webp`);
