# 本家 (linejs) 参照ベクタ

`linejs_vectors.json` は **本家 linejs の実コード**を Deno で実行し、固定入力に対する
出力を記録した既知解ベクタ (KAT) です。Python 移植版がバイト単位で一致することを
`tests/test_e2ee_vectors.py` / `tests/test_legy_vectors.py` が検証します。

## 再生成

```bash
deno run --config resource/linejs/deno.json --allow-read --allow-env \
  tools/gen_vectors.ts > tests/vectors/linejs_vectors.json
```

## 双方向 interop テスト

`tests/test_interop.py` は実行時に `tools/interop.ts` を Deno で起動し、
乱数を含むテキストメッセージ経路について Python↔本家 の双方向ワイヤ互換を検証します
（Deno が無い環境では自動 skip）。

## TMC ベクタ

`tmc_vectors.json` は本家 `tmc.ts` で手構築 TMC バイト列をデコードした結果と、
Huffman木・zigzag・bitmap・型変換テーブルを記録したものです
(`tests/test_tmc_vectors.py` が検証)。再生成は同梱の一時スクリプトを参照。
