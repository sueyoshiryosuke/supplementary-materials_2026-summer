"""
src/03_generate_evaluation_contexts.py
2026年春季 人狼知能大会 自然言語部門（5人村）の30ゲームログから
DeepSeekが自律的に人間評価用ゲーム状況（10問）を選定・作成するスクリプト。
"""

import datetime
import glob
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# src ディレクトリからのインポート対応
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from main import (
    create_client,
    extract_reasoning_and_response,
    extract_usage,
    load_config,
    resolve_path,
    save_json_log,
)

SYSTEM_PROMPT_TEMPLATE = """あなたは人狼知能大会のゲームログを分析し、評価用タスクを設計する専門家です。

以下に、人狼知能大会（5人村トラック）の30ゲームの実ログデータを提供します。
これらの実際のゲームログを参考に、Full personality 条件と MBTI-like 条件の発話生成・人間評価に使用するゲーム状況を10問分作成してください。

【目的】
人間評価では、回答者に「人物プロフィール」「役職」「1文程度の状況説明」「生成された発話」を提示し、その発話が人物プロフィールと一致しているかを評価してもらいます。
したがって、複雑なゲーム履歴を読まなくても「役職＋1文程度の状況説明だけで、その時にどのような発話が求められるか理解できる」自然な局面を10件選定・作成してください。

【条件】
1. 提供された30ゲームの実ログから、異なる10個の局面を選定してください。
2. 10問の局面内容そのものに十分なバリエーションを持たせてください。
   - 特に、占いCO・占い結果・占い師の真贋争いだけに偏らないようにしてください。
   - 初日の挨拶・進行議論、寡黙者への発言催促、怪しい発言や投票行動への追及、誰を追放（投票）すべきかの議論、最終日（3人残り）の投票決断など、多彩なゲーム局面を含めてください。
3. situation は、人狼ゲーム未経験者でも直感的に理解できるよう、専門用語（CO、吊り、黒出し、白出し、グレー、確白、騙りなど）を避け、平易で自然な日本語の1文程度で記述してください。
4. situation には、その役職のプレイヤー自身が「その時点で知り得る情報」のみを記述してください。
   - 他プレイヤーの真の役職（ログ上のメタ情報）など、本人視点では知り得ない神視点の情報を含めないでください（例：「狂人のメイ」ではなく「占い師を名乗るメイ」とする）。
5. 元ログ中の発言者の誤解や誤認（ルール勘違い等）を、客観的な事実として situation に書かないでください。
6. source_log は提供された30ファイルの実在するログファイル名を指定してください。
7. source_day, source_lines（または特定情報）, selection_reason を明記してください。

【出力形式】
JSONのみで回答してください。コードブロック (```json ... ```) で囲んでも構いません。

{{
  "contexts": [
    {{
      "context_id": "ctx_01",
      "role": "...",
      "situation": "...",
      "source_log": "...",
      "source_day": 0,
      "source_lines": "...",
      "selection_reason": "..."
    }}
  ]
}}

【30ゲームのログデータ】
{GAME_LOGS_DATA}"""


def load_game_logs(logs_dir: Path) -> List[Tuple[str, str]]:
    """
    指定ディレクトリ内の .log ファイル（30件）を機械的に読み込む。
    意味的な要約や取捨選択は行わず、ファイル名と生テキストのタプルリストを返す。
    """
    if not logs_dir.exists() or not logs_dir.is_dir():
        raise FileNotFoundError(f"ゲームログディレクトリが見つかりません: {logs_dir}")

    log_files = sorted(list(logs_dir.glob("*.log")))
    if not log_files:
        raise ValueError(f"'{logs_dir}' 内に .log ファイルが存在しません。")

    results: List[Tuple[str, str]] = []
    for lf in log_files:
        with open(lf, "r", encoding="utf-8") as f:
            content = f.read()
        results.append((lf.name, content))

    return results


def format_game_logs_for_prompt(logs: List[Tuple[str, str]]) -> str:
    """30ゲームのログデータをプロンプト挿入用に機械的に整形・連結する。"""
    sections = []
    for idx, (filename, content) in enumerate(logs, start=1):
        section = f"=== GAME LOG {idx:02d}: {filename} ===\n{content.strip()}\n"
        sections.append(section)
    return "\n".join(sections)


def extract_json_from_text(text: str) -> str:
    """テキスト中からJSON文字列を抽出する（コードブロック対応）。"""
    stripped = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", stripped)
    if match:
        return match.group(1).strip()
    return stripped


def validate_contexts(contexts_data: Any, available_log_names: List[str]) -> List[Dict[str, Any]]:
    """
    LLMレスポンスから抽出された contexts データを検証する。
    10件存在すること、必須フィールドが存在すること、source_log が実在することを確認。
    """
    if not isinstance(contexts_data, dict):
        raise ValueError("レスポンスのトップレベルが辞書ではありません。")

    contexts = contexts_data.get("contexts")
    if not isinstance(contexts, list):
        raise ValueError("'contexts' キーが存在しないかリストではありません。")

    if len(contexts) != 10:
        raise ValueError(f"contexts の件数が10件ではありません (取得件数: {len(contexts)}件)。")

    required_fields = [
        "context_id",
        "role",
        "situation",
        "source_log",
        "source_day",
        "source_lines",
        "selection_reason",
    ]

    valid_contexts: List[Dict[str, Any]] = []
    for idx, item in enumerate(contexts, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"contexts[{idx-1}] がオブジェクトではありません。")

        for field in required_fields:
            if field not in item:
                raise ValueError(f"contexts[{idx-1}] に必須フィールド '{field}' が存在しません。")

        # source_log の実在性チェック
        source_log = str(item["source_log"]).strip()
        if source_log not in available_log_names:
            # パス等が付いてしまっている場合の救済
            base_name = Path(source_log).name
            if base_name in available_log_names:
                item["source_log"] = base_name
            else:
                raise ValueError(f"contexts[{idx-1}] の source_log '{source_log}' は実在する30ログに見つかりません。")

        # situation の空チェック
        if not isinstance(item["situation"], str) or not item["situation"].strip():
            raise ValueError(f"contexts[{idx-1}] の situation が空または文字列ではありません。")

        valid_contexts.append(item)

    return valid_contexts


def run_generation(
    config_path: str = "config.yml",
    logs_dir: Optional[Path] = None,
    output_path: Optional[Path] = None,
    api_logs_dir: Optional[Path] = None,
    max_retries: int = 3,
) -> None:
    """30ゲームログからDeepSeekを通して10問の評価用状況を自動選定・生成する。"""
    config = load_config(config_path)
    client = create_client(config)

    target_logs_dir = logs_dir or resolve_path("src/2026sp_game-log")
    target_output = output_path or resolve_path("results/evaluation_contexts.json")
    target_api_logs = api_logs_dir or resolve_path("logs")

    print("==================================================")
    print(" 03_generate_evaluation_contexts")
    print(" 30ゲームログからの人間評価用10局面 自律選定")
    print("==================================================")
    print(f"Model: {config.get('model', {}).get('name')}")
    print(f"ログディレクトリ: {target_logs_dir}")

    # 1. 30ゲームのログを機械的に読み込む
    logs = load_game_logs(target_logs_dir)
    print(f"[INFO] {len(logs)} 件のゲームログを機械的に読み込みました。")
    available_log_names = [name for name, _ in logs]

    # 2. プロンプト構築（プレースホルダのみの中立プロンプト）
    logs_text = format_game_logs_for_prompt(logs)
    prompt = SYSTEM_PROMPT_TEMPLATE.format(GAME_LOGS_DATA=logs_text)

    # 3. DeepSeek API へ問い合わせ（リトライ付き）
    validated_contexts: Optional[List[Dict[str, Any]]] = None

    model_name = config.get("model", {}).get("name")
    temperature = config.get("model", {}).get("temperature", 1.0)
    max_tokens = config.get("model", {}).get("max_tokens")

    extra_body: Dict[str, Any] = {}
    if "reasoning" in config and config["reasoning"]:
        extra_body["reasoning"] = config["reasoning"]
    if "provider" in config and config["provider"]:
        extra_body["provider"] = config["provider"]

    request_kwargs: Dict[str, Any] = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
    }
    if temperature is not None:
        request_kwargs["temperature"] = temperature
    if max_tokens is not None:
        request_kwargs["max_tokens"] = max_tokens
    if extra_body:
        request_kwargs["extra_body"] = extra_body

    print(f"[INFO] DeepSeek へ局面選定・生成を依頼中 (Reasoning ON)...")

    for attempt in range(1, max_retries + 1):
        start_time = time.perf_counter()
        try:
            response = client.chat.completions.create(**request_kwargs)
            latency = time.perf_counter() - start_time

            if not response.choices:
                raise ValueError("APIから空のchoicesレスポンスが返却されました。")

            first_choice = response.choices[0]
            reasoning_text, response_text = extract_reasoning_and_response(first_choice)
            usage_data = extract_usage(response)

            # APIログを logs/ へ保存
            log_path = save_json_log(
                logs_dir=target_api_logs,
                success=True,
                config=config,
                prompt=prompt,
                response_text=response_text,
                reasoning_text=reasoning_text,
                usage=usage_data,
                latency_sec=latency,
            )
            print(f"[INFO] APIログを保存しました: {log_path}")

            if response_text is None:
                raise ValueError("APIレスポンスの content が空です。")

            # JSONパースとバリデーション
            json_str = extract_json_from_text(response_text)
            parsed_data = json.loads(json_str)
            validated_contexts = validate_contexts(parsed_data, available_log_names)
            print(f"[INFO] 10問のゲーム状況が正常に選定・検証されました。")
            break

        except Exception as e:
            latency = time.perf_counter() - start_time
            error_msg = str(e)
            error_type = type(e).__name__
            print(f"[WARN] 試行 {attempt}/{max_retries} 失敗: {error_msg}")

            save_json_log(
                logs_dir=target_api_logs,
                success=False,
                config=config,
                prompt=prompt,
                error_info={"error_type": error_type, "message": error_msg},
                latency_sec=latency,
            )

            if attempt == max_retries:
                raise RuntimeError(f"DeepSeek による局面選定が最大リトライ回数 ({max_retries}) に達し失敗しました: {e}")

    # 4. 結果を results/evaluation_contexts.json に保存
    target_output.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now().astimezone()

    model_config = config.get("model", {})
    generation_info = {
        "temperature": model_config.get("temperature"),
        "max_tokens": model_config.get("max_tokens"),
        "reasoning": config.get("reasoning"),
    }

    result_json = {
        "generated_at": now.isoformat(),
        "model": model_config.get("name"),
        "provider": config.get("provider"),
        "generation": generation_info,
        "description": "2026年春季人狼知能大会5人村トラック30ゲームログからDeepSeekが自律選定した人間評価用ゲーム状況（10問）",
        "contexts": validated_contexts,
    }

    with open(target_output, "w", encoding="utf-8") as f:
        json.dump(result_json, f, ensure_ascii=False, indent=2)

    print(f"\n[INFO] 最終結果を保存しました: {target_output}")

    # 5. サマリー表示
    print("\n==================================================")
    print(" 選定された人間評価用ゲーム状況 (10問)")
    print("==================================================")
    for c in validated_contexts:
        print(f"[{c['context_id']}] 役職: {c['role']:<10} (Day {c['source_day']})")
        print(f"  状況: {c['situation']}")
        print(f"  元ログ: {c['source_log']} ({c.get('source_lines', '')})")
        print(f"  選定理由: {c.get('selection_reason', '')}\n")
    print("==================================================")


if __name__ == "__main__":
    try:
        run_generation()
    except Exception as e:
        print(f"\n[FATAL ERROR] 処理が異常終了しました: {e}", file=sys.stderr)
        sys.exit(1)
