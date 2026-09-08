// Reference-vector generator: runs the REAL linejs (本家) crypto functions
// with fixed inputs and emits deterministic known-answer vectors as JSON.
// Run: deno run --config resource/linejs/deno.json --allow-read --allow-env \
//        tools/gen_vectors.ts > tests/vectors/linejs_vectors.json
import { Buffer } from "node:buffer";
import crypto from "node:crypto";
import nacl from "tweetnacl";
import { E2EE } from "../resource/linejs/packages/linejs/base/e2ee/mod.ts";
import {
  xxhash32,
  encodeLegyHeaders,
  decodeLegyHeaders,
} from "../resource/linejs/packages/linejs/base/request/legy.ts";
import {
  resolveLineAccessToken,
  shouldUseLegyEncryptedAccess,
  isJwt,
  isPrimaryAccessToken,
  createPrimaryAccessToken,
} from "../resource/linejs/packages/linejs/base/request/auth_token.ts";
import {
  packCompactPlainMessage,
  packCompactE2EEMessage,
  encodeCompactText,
  writeCompactI32,
  writeCompactI64,
  decodeCompactMessageResponse,
} from "../resource/linejs/packages/linejs/base/service/talk/compact.ts";

const hex = (b: Uint8Array) => Buffer.from(b).toString("hex");
const b64 = (b: Uint8Array) => Buffer.from(b).toString("base64");

const e2ee = new E2EE({
  profile: { mid: "u-self" },
  storage: { get() { return Promise.resolve(null); }, set() { return Promise.resolve(); } },
  getToType() { return 0; },
  log() {},
} as never);

// ---- fixed key material -------------------------------------------------
const privA = Buffer.from(Array.from({ length: 32 }, (_, i) => i + 1));
const privB = Buffer.from(Array.from({ length: 32 }, (_, i) => i + 33));
const pubA = Buffer.from(nacl.scalarMult.base(new Uint8Array(privA)));
const pubB = Buffer.from(nacl.scalarMult.base(new Uint8Array(privB)));
const shared = e2ee.generateSharedSecret(privA, pubB);

// ---- E2EE deterministic vectors -----------------------------------------
const sha_vectors = [
  { args: [{ t: "str", v: "abc" }], out: hex(e2ee.getSHA256Sum("abc")) },
  { args: [{ t: "hex", v: hex(shared) }, { t: "str", v: "Key" }],
    out: hex(e2ee.getSHA256Sum(Buffer.from(shared), "Key")) },
  { args: [{ t: "hex", v: hex(shared) }, { t: "str", v: "IV" }],
    out: hex(e2ee.getSHA256Sum(Buffer.from(shared), "IV")) },
];

const salt = Buffer.from("00112233445566778899aabbccddeeff", "hex");
const gcmKeyText = e2ee.getSHA256Sum(Buffer.from(shared), salt, Buffer.from("Key"));

// encryptE2EEMessageV2 is deterministic given a fixed nonce.
const nonce = Buffer.from("aabbccddeeff00112233445566", "hex").subarray(0, 12);
const aad = e2ee.generateAAD("u-to", "u-from", 3, 7, 2, 0);
const gcmData = Buffer.from(JSON.stringify({ text: "hello 本家" }));
const gcmOut = e2ee.encryptE2EEMessageV2(gcmData, gcmKeyText, nonce, aad);

// V1: build a ciphertext with node crypto using the 本家 key/iv derivation.
const v1AesKey = e2ee.getSHA256Sum(Buffer.from(shared), salt, "Key");
const v1AesIv = e2ee.xor(e2ee.getSHA256Sum(Buffer.from(shared), salt, "IV"));
const v1Plain = Buffer.from(JSON.stringify({ text: "v1 本家 message" }));
const v1cipher = crypto.createCipheriv("aes-256-cbc", v1AesKey, v1AesIv);
const v1ct = Buffer.concat([v1cipher.update(v1Plain), v1cipher.final()]);

// deriveKeyMaterial + encryptByKeyMaterial (deterministic given fixed keyMaterial)
const keyMaterial = Buffer.from(Array.from({ length: 32 }, (_, i) => (i * 7) & 0xff));
const dk = await e2ee.deriveKeyMaterial(keyMaterial);
const rawMedia = Buffer.from("secret media payload 本家 12345");
const enc = await e2ee.encryptByKeyMaterial(rawMedia, keyMaterial);

const out = {
  e2ee: {
    pubA: hex(pubA), pubB: hex(pubB),
    privA: hex(privA), privB: hex(privB),
    shared: hex(shared),
    sha256: sha_vectors,
    xor_input: hex(Buffer.concat([Buffer.alloc(16, 0xaa), Buffer.alloc(16, 0x55)])),
    xor_out: hex(e2ee.xor(Buffer.concat([Buffer.alloc(16, 0xaa), Buffer.alloc(16, 0x55)]))),
    intBytes: [0, 1, 255, 256, 65536, 2147483647, -1].map((i) => ({ i, out: hex(e2ee.getIntBytes(i)) })),
    aad: { to: "u-to", from: "u-from", c: 3, d: 7, e: 2, f: 0, out: hex(aad) },
    gcm_v2: {
      salt: hex(salt), nonce: hex(nonce),
      gcmKey: hex(gcmKeyText),
      data_utf8: gcmData.toString("utf-8"),
      aad: hex(aad),
      out: hex(gcmOut),
    },
    cbc_v1: {
      salt: hex(salt),
      aesKey: hex(v1AesKey), aesIv: hex(v1AesIv),
      plain_utf8: v1Plain.toString("utf-8"),
      ciphertext: hex(v1ct),
    },
    keyMaterial: {
      input: hex(keyMaterial),
      encKey: hex(dk.encKey), macKey: hex(dk.macKey), nonce: hex(dk.nonce),
      raw_utf8: rawMedia.toString("utf-8"),
      keyMaterial_b64: enc.keyMaterial,
      encryptedData: hex(enc.encryptedData),
    },
    signData: {
      key: hex(Buffer.alloc(32, 9)),
      data: hex(Buffer.from("data to sign")),
      out: hex(e2ee.signData(Buffer.from("data to sign"), Buffer.alloc(32, 9))),
    },
  },
  legy: {
    xxhash32: ["", "a", "hello", "The quick brown fox", "0123456789abcdef0123"].map((s) => ({
      input_utf8: s, seed: 0, out: xxhash32(new TextEncoder().encode(s), 0),
    })),
    encodeLegyHeaders: (() => {
      const hdrs = { "x-lpqs": "/S4?v=1", "x-lt": "token-本家" };
      const bytes = encodeLegyHeaders(hdrs);
      return { headers: hdrs, out: hex(bytes) };
    })(),
    decodeLegyHeaders: (() => {
      const hdrs = { "x-lc": "200", "x-le": "7" };
      const bytes = encodeLegyHeaders(hdrs);
      const body = Buffer.from("THRIFTBODY", "utf-8");
      const dec = decodeLegyHeaders(Buffer.concat([bytes, body]));
      return { encoded: hex(Buffer.concat([bytes, body])), headers: dec.headers, data: hex(dec.data) };
    })(),
  },
  compact: (() => {
    const toUser = "u" + "0123456789abcdef0123456789abcdef";
    const toGroup = "c" + "fedcba9876543210fedcba9876543210";
    const chunks = [
      Buffer.alloc(16, 0x11),                 // salt
      Buffer.from("ciphertext+tag bytes 本家", "utf-8"), // encData
      Buffer.alloc(12, 0x22),                 // nonce
      Buffer.from([0x00, 0x00, 0x00, 0x03]),  // senderKeyId = 3
      Buffer.from([0xff, 0xff, 0xff, 0xf9]),  // receiverKeyId = -7 (signed)
    ];
    // Craft a success response with the exported writers: bool(1)+seq+msgId+timeMs
    const resp: number[] = [1];
    writeCompactI32(resp, 42);
    writeCompactI64(resp, 1234567890123456789n);
    writeCompactI64(resp, 1700000000000n);
    const respBytes = Uint8Array.from(resp);
    const decoded = decodeCompactMessageResponse(respBytes);
    const i32vec: { v: number; out: string }[] = [];
    for (const v of [0, 1, -1, 42, 300, -300, 2147483647, -2147483648]) {
      const o: number[] = [];
      writeCompactI32(o, v);
      i32vec.push({ v, out: hex(Uint8Array.from(o)) });
    }
    return {
      plain: {
        seqId: 7, to: toUser, text: "hello 本家 🌸",
        out: hex(packCompactPlainMessage(7, toUser, "hello 本家 🌸")),
      },
      plain_ascii: {
        seqId: 1, to: toGroup, text: "abc",
        out: hex(packCompactPlainMessage(1, toGroup, "abc")),
      },
      e2ee: {
        seqId: 99, to: toUser, msgType: 5,
        chunks: chunks.map((c) => hex(c)),
        out: hex(packCompactE2EEMessage(99, toUser, chunks, 5)),
      },
      encodeCompactText: ["abc", "日本語テキスト", "🌸🌟", "mixed 混在 text"].map((t) => ({
        text: t, out: hex(encodeCompactText(t)),
      })),
      writeCompactI32: i32vec,
      response: { bytes: hex(respBytes), decoded: {
        sequenceId: decoded.sequenceId,
        messageId: decoded.messageId.toString(),
        createdTime: decoded.createdTime,
      } },
    };
  })(),
  auth_token: {
    isJwt: (() => {
      const h = b64(Buffer.from(JSON.stringify({ alg: "HS256" })));
      const p = b64(Buffer.from(JSON.stringify({ iat: 1, sub: "x" })));
      const jwt = `${h}.${p}.sig`.replace(/=/g, "");
      return [
        { token: jwt, out: isJwt(jwt) },
        { token: "a.b.c", out: isJwt("a.b.c") },
        { token: "notajwt", out: isJwt("notajwt") },
      ];
    })(),
    createPrimaryAccessToken: (() => {
      // fixed authKey (mid:base64key) and fixed now
      const key = b64(Buffer.alloc(20, 0x42));
      const authKey = `u0123456789abcdef0123456789abcdef:${key}`;
      const now = 1700000000000;
      return { authKey, now, out: createPrimaryAccessToken(authKey, now) };
    })(),
    resolveLineAccessToken: (() => {
      const h = b64(Buffer.from(JSON.stringify({ alg: "HS256" })));
      const p = b64(Buffer.from(JSON.stringify({ iat: 1 })));
      const jwt = `${h}.${p}.sig`.replace(/=/g, "");
      return [
        { token: `u123:${jwt}`, out: resolveLineAccessToken(`u123:${jwt}`) },
        { token: jwt, out: resolveLineAccessToken(jwt) },
      ];
    })(),
    shouldUseLegyEncryptedAccess: (() => {
      const h = b64(Buffer.from(JSON.stringify({ alg: "HS256" })));
      const p = b64(Buffer.from(JSON.stringify({ iat: 1 })));
      const jwt = `${h}.${p}.sig`.replace(/=/g, "");
      return [
        { token: jwt, out: shouldUseLegyEncryptedAccess(jwt) },
        { token: "plain", out: shouldUseLegyEncryptedAccess("plain") },
      ];
    })(),
  },
};

console.log(JSON.stringify(out, null, 2));
