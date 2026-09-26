# 補足資料

[English / 英語版](README.md)

以下の論文の補足資料です。

**「Preserving Character in Four Letters: Personality Information Compression in AIWolf Agents Using MBTI-like Labels」**

本資料には、本研究で使用したソースコードおよび設定ファイルが含まれています。

## ディレクトリ構成

```text
src/
├── 01_select_characters.py
├── 02_to_MBTI_like.py
├── 03_generate_evaluation_contexts.py
├── 04_generate_utterances.py
├── 05_export_form_data.py
├── main.py
├── config.yml
└── default_5.yml

2026sp_game-log.txt
```

### ソースコード

* `01_select_characters.py`

  * 実験で使用する10人のキャラクターを選択します。

* `02_to_MBTI_like.py`

  * 元の自然言語による性格記述から、MBTI-likeラベルを導出します。

* `03_generate_evaluation_contexts.py`

  * AIWolfのゲームログから評価用シナリオを構成します。

* `04_generate_utterances.py`

  * Full条件およびMBTI条件で発話を生成します。

* `05_export_form_data.py`

  * 人手評価アンケート用のデータを準備します。

* `main.py`

  * 実験用スクリプトで共通して使用する関数を提供します。

* `config.yml`

  * API、モデル、推論、プロバイダ、および実験の設定を含みます。

* `default_5.yml`

  * キャラクタープロファイルの基礎として使用した大会設定ファイルです。

## 外部データ

評価用シナリオの構成に使用したAIWolfのゲームログは第三者データであり、
本リポジトリでは再配布していません。

本研究で使用したデータの出典URLおよび正確なログファイル名は、

`2026sp_game-log.txt`

に記載しています。

これらのログファイルは、公開されている
人狼知能大会 2026春季 国内大会 自然言語処理部門 の
「5人村トラック」のログアーカイブから取得したものです。

## 大会設定ファイル

`default_5.yml` は、AIWolf NLP ServerリポジトリからMIT Licenseの下で
再配布しています。

著作権表示：

Yuto Sahashi (Kano Laboratory), 2024.

本研究で使用した正確なバージョンは、以下のコミットから取得できます。

https://github.com/aiwolfdial/aiwolf-nlp-server/blob/32f1945cc5cc31b976ce02476784dd68b625c3d0/config/default_5.yml

## 設定

スクリプトを実行する前に、OpenRouterのAPIキーを環境変数
`OpenRouter_API_KEY` に設定してください。

実験で使用したモデルおよび生成設定は、
`src/config.yml` に記載されています。

## 再現方法

スクリプトは、以下の順番で実行することを想定しています。

1. `01_select_characters.py`
2. `02_to_MBTI_like.py`
3. `03_generate_evaluation_contexts.py`
4. `04_generate_utterances.py`
5. `05_export_form_data.py`

実験用スクリプトでは、APIやログ処理などの共通機能に
`main.py` を使用しています。

## ライセンス

Copyright (C) 2026 Ryosuke Sueyoshi.

本研究のために作成したソースコードおよび原著作物は、
[Zero-Clause BSD License (0BSD)](LICENSE) の下でライセンスされています。

第三者の著作物については、それぞれの元のライセンスおよび利用条件が適用されます。

Version: 1.0
2026-09-26
