import { execFileSync } from "node:child_process";
import path from "node:path";

type Posting = { company: string; title: string; location: string; description: string; salary_text?: string };
type Demo = { resume: string; preferences: Record<string, unknown>; postings: Record<string, Posting> };

/** Sample resume, preferences, and postings come from the backend fixtures, so there is one source of truth. */
export function demoData(): Demo {
  const script = [
    "import json",
    "from app.semantic.fake_fixtures import DEMO_PREFERENCES, FIXTURES, SAMPLE_RESUME",
    "print(json.dumps({'resume': SAMPLE_RESUME, 'preferences': DEMO_PREFERENCES,",
    "                  'postings': {k: v['posting'] for k, v in FIXTURES.items()}}))",
  ].join("\n");
  const out = execFileSync("uv", ["run", "python", "-c", script], { cwd: path.join(__dirname, "../../backend"), encoding: "utf8" });
  return JSON.parse(out) as Demo;
}
