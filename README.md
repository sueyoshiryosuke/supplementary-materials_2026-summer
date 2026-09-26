# Supplementary Materials

[日本語版 / Japanese](README_ja.md)

Supplementary materials for:

**"Preserving Character in Four Letters: Personality Information Compression in AIWolf Agents Using MBTI-like Labels"**

These materials contain the source code and configuration files used in this study.

## Directory Structure

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

### Source code

* `01_select_characters.py`

  * Selects the 10 characters used in the experiment.

* `02_to_MBTI_like.py`

  * Derives MBTI-like labels from the original personality descriptions.

* `03_generate_evaluation_contexts.py`

  * Constructs evaluation scenarios from AIWolf game logs.

* `04_generate_utterances.py`

  * Generates utterances under the Full and MBTI conditions.

* `05_export_form_data.py`

  * Prepares data for the human evaluation survey.

* `main.py`

  * Provides common functions used by the experimental scripts.

* `config.yml`

  * Contains the API, model, reasoning, provider, and experiment settings.

* `default_5.yml`

  * Tournament configuration used as the basis for the character profiles.

## External Data

The AIWolf game logs used to construct the evaluation scenarios are
third-party data and are not redistributed in this repository.

The source URL and the exact log files used in this study are listed in:

`2026sp_game-log.txt`

The log files were obtained from the publicly available AIWolf 2026
5-player Village Track archive.

## Tournament Configuration

`default_5.yml` is redistributed from the AIWolf NLP Server repository
under the MIT License.

Original copyright: Yuto Sahashi (Kano Laboratory), 2024.

The exact version used in this study is available at the following
commit:

https://github.com/aiwolfdial/aiwolf-nlp-server/blob/32f1945cc5cc31b976ce02476784dd68b625c3d0/config/default_5.yml

## Configuration

Before running the scripts, set the OpenRouter API key in the
environment variable `OpenRouter_API_KEY`.

The model and generation settings used in the experiments are specified
in `src/config.yml`.

## Reproduction

The scripts are intended to be run in the following order:

1. `01_select_characters.py`
2. `02_to_MBTI_like.py`
3. `03_generate_evaluation_contexts.py`
4. `04_generate_utterances.py`
5. `05_export_form_data.py`

The experimental scripts use `main.py` for common API and logging
functions.

## License

Copyright (C) 2026 Ryosuke Sueyoshi.

Original source code and materials developed for this study are
licensed under the [Zero-Clause BSD License (0BSD)](LICENSE).

Third-party materials retain their original licenses and terms.

Version: 1.0
2026-09-26
