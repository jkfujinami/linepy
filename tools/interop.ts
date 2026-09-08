// Interop worker: performs a single E2EE op with 本家 (linejs) code.
// Reads one JSON job from stdin, writes one JSON result to stdout.
import { Buffer } from "node:buffer";
import { E2EE } from "../resource/linejs/packages/linejs/base/e2ee/mod.ts";

const e2ee = new E2EE({
  profile: { mid: "u-self" },
  storage: { get() { return Promise.resolve(null); }, set() { return Promise.resolve(); } },
  getToType() { return 0; },
  log() {},
} as never);

const hex = (b: Uint8Array) => Buffer.from(b).toString("hex");
const fromHex = (s: string) => Buffer.from(s, "hex");

const input = JSON.parse(new TextDecoder().decode(await new Response(Deno.stdin.readable).arrayBuffer()));

let result: unknown;
if (input.op === "decryptV2") {
  const chunks = input.chunks.map(fromHex);
  const dec = e2ee.decryptE2EEMessageV2(
    input.to, input.from, chunks,
    fromHex(input.privKey), fromHex(input.pubKey),
    input.spec ?? 2, input.contentType ?? 0,
  );
  result = { text: dec.text };
} else if (input.op === "encryptText") {
  const chunks = e2ee.encryptE2EETextMessage(
    input.senderKeyId, input.receiverKeyId,
    fromHex(input.keyData), input.spec ?? 2,
    input.text, input.to, input.from,
  );
  result = { chunks: chunks.map((c: Uint8Array) => hex(c)) };
} else {
  result = { error: "unknown op" };
}
console.log(JSON.stringify(result));
