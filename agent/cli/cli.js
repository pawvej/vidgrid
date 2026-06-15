#!/usr/bin/env node
// vidgrid — turn a local video file into a numbered frame grid an AI can read.
// Zero-dependency client for the vidgrid render API. Node 18+ (global fetch,
// FormData, Blob).
import { readFileSync, writeFileSync } from "node:fs";
import { basename } from "node:path";

const API_BASE = (process.env.VIDGRID_API_BASE || "https://api.vidgrid.site").replace(/\/$/, "");
const KEY = process.env.VIDGRID_API_KEY;

function usage(code = 2) {
  console.error(`vidgrid — turn a video file into a numbered frame grid for an LLM.

Usage:
  vidgrid <video-file> [--grid 3x3] [--no-transcribe] [--out grid]

Options:
  --grid 2x2|3x3|4x4|5x5   force a grid size (default: auto)
  --no-transcribe          skip the Whisper transcript
  --out <name>             output prefix (default: grid)

Env:
  VIDGRID_API_KEY   required — get one at https://vidgrid.site/api
  VIDGRID_API_BASE  optional — default https://api.vidgrid.site`);
  process.exit(code);
}

const args = process.argv.slice(2);
if (args.length === 0 || args[0] === "-h" || args[0] === "--help") usage(args.length === 0 ? 2 : 0);

let file = null, grid = null, transcribe = true, out = "grid";
for (let i = 0; i < args.length; i++) {
  const a = args[i];
  if (a === "--grid") grid = args[++i];
  else if (a === "--no-transcribe") transcribe = false;
  else if (a === "--out") out = args[++i];
  else if (!a.startsWith("-")) file = a;
  else { console.error(`Unknown option: ${a}`); usage(); }
}
if (!file) usage();
if (!KEY) {
  console.error("VIDGRID_API_KEY is not set. Get one free at https://vidgrid.site/api");
  process.exit(1);
}

let buf;
try {
  buf = readFileSync(file);
} catch (e) {
  console.error(`Cannot read file: ${file} (${e.code || e.message})`);
  process.exit(1);
}

const form = new FormData();
form.append("file", new Blob([buf]), basename(file));
if (grid) form.append("grid", grid);
form.append("transcribe", String(transcribe));

let res;
try {
  res = await fetch(`${API_BASE}/v1/render`, {
    method: "POST",
    headers: { Authorization: `Bearer ${KEY}` },
    body: form,
  });
} catch (e) {
  console.error(`Could not reach vidgrid API: ${e.message}`);
  process.exit(1);
}

if (res.status === 401) { console.error("Invalid or missing VIDGRID_API_KEY."); process.exit(1); }
if (res.status === 402) { console.error("Out of credits — top up at https://vidgrid.site/api"); process.exit(1); }
if (!res.ok) {
  let detail = "";
  try { detail = JSON.stringify((await res.json()).detail || ""); } catch { detail = (await res.text()).slice(0, 200); }
  console.error(`Error ${res.status}: ${detail}`);
  process.exit(1);
}

const data = await res.json();
const paths = [];
const boards = data.boards || [];
boards.forEach((b, i) => {
  const p = boards.length === 1 ? `${out}.png` : `${out}-${i + 1}.png`;
  writeFileSync(p, Buffer.from(b.png_base64, "base64"));
  paths.push(p);
});
console.log(`Wrote ${paths.length} board(s): ${paths.join(", ")}`);

if (data.transcript) {
  const txt = data.transcript.map((w) => w.text).join(" ");
  writeFileSync(`${out}-transcript.txt`, txt);
  console.log(`Transcript: ${out}-transcript.txt`);
}
console.log(`${data.duration_seconds}s video · credits remaining: ${data.credits_remaining}`);
