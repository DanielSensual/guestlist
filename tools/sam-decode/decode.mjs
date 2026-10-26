// Bulk-decode SAM 3.1 masks with Meta's JS decoder (JIT-fast; the Python port is ~1 s per mask).
// stdin: JSON lines {"key": str, "encoding": "one_bit"|"lossless", "payload": str, "width": int, "height": int}
// stdout: JSON lines {"key": str, "rle": {"size": [h, w], "counts": str}} (COCO compressed RLE, column-major)
import { createInterface } from "node:readline";
import { decodeMaskToRLE } from "@meta-sam/parser";

const rl = createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of rl) {
  if (!line.trim()) continue;
  const job = JSON.parse(line);
  try {
    const rle = decodeMaskToRLE({ encoding: job.encoding, payload: job.payload, width: job.width, height: job.height });
    process.stdout.write(JSON.stringify({ key: job.key, rle }) + "\n");
  } catch (err) {
    process.stdout.write(JSON.stringify({ key: job.key, error: String(err && err.message || err) }) + "\n");
  }
}
