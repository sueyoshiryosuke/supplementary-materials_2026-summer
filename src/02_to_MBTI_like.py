"""
src/02_to_MBTI_like.py
研究実験用スクリプト: default_5.yml の固定10キャラクターについて
LLM APIを利用してBig Five評定およびMBTI風タイプ変換を一括実行する。
"""

import datetime
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

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

# 固定10キャラクター（seed=20260817による抽出結果）
FIXED_CHARACTERS = [
    "ケンジ",
    "リン",
    "ダイスケ",
    "ミオ",
    "リュウジ",
    "トシオ",
    "メイ",
    "ミドリ",
    "ジョージ",
    "シズエ",
]

# 評定プロンプトテンプレート
RATING_PROMPT_TEMPLATE = """以下の人物プロフィールについて、10項目を1～7で評定してください。
各項目について、簡潔な評価理由も示してください。

1 = 全く違うと思う
2 = おおよそ違うと思う
3 = 少し違うと思う
4 = どちらでもない
5 = 少しそう思う
6 = まあまあそう思う
7 = 強くそう思う

1. 外向的で、活発である
2. 批判的で、対立的である
3. 信頼でき、自制心がある
4. 不安になりやすく、動揺しやすい
5. 新しい経験や考えに開かれている
6. 控えめで、物静かである
7. 共感的で、温かい
8. まとまりがなく、不注意である
9. 落ち着いており、情緒的に安定している
10. 慣習的で、新奇な発想をあまり好まない

プロフィールに書かれている内容を根拠に評定してください。

JSONのみで回答してください。

{{
  "ratings": {{
    "item1": 1,
    "item2": 1,
    "item3": 1,
    "item4": 1,
    "item5": 1,
    "item6": 1,
    "item7": 1,
    "item8": 1,
    "item9": 1,
    "item10": 1
  }},
  "reasons": {{
    "item1": "簡潔な理由",
    "item2": "簡潔な理由",
    "item3": "簡潔な理由",
    "item4": "簡潔な理由",
    "item5": "簡潔な理由",
    "item6": "簡潔な理由",
    "item7": "簡潔な理由",
    "item8": "簡潔な理由",
    "item9": "簡潔な理由",
    "item10": "簡潔な理由"
  }}
}}

人物プロフィール：
{PERSONALITY}"""

# tie-break (決選判定) 定義
TIEBREAK_CONFIG = {
    "E": {
        "dim_text": "外向性が高い人物と低い人物",
        "high_desc": "外向性が高い",
        "low_desc": "外向性が低い",
        "choice_map": {"A": "E", "B": "I"},
    },
    "O": {
        "dim_text": "開放性が高い人物と低い人物",
        "high_desc": "開放性が高い",
        "low_desc": "開放性が低い",
        "choice_map": {"A": "N", "B": "S"},
    },
    "A": {
        "dim_text": "協調性が高い人物と低い人物",
        "high_desc": "協調性が高い",
        "low_desc": "協調性が低い",
        "choice_map": {"A": "F", "B": "T"},
    },
    "C": {
        "dim_text": "誠実性が高い人物と低い人物",
        "high_desc": "誠実性が高い",
        "low_desc": "誠実性が低い",
        "choice_map": {"A": "J", "B": "P"},
    },
}


def to_mbti(ratings: Dict[str, int]) -> Tuple[Dict[str, float], str, List[str]]:
    """
    Big Five スコアと MBTI風マッピング、tie次元のリストを計算する。
    """
    # 逆転項目
    def rev(x: int) -> int:
        return 8 - x

    # Big Five
    E = (ratings["item1"] + rev(ratings["item6"])) / 2
    A = (rev(ratings["item2"]) + ratings["item7"]) / 2
    C = (ratings["item3"] + rev(ratings["item8"])) / 2
    ES = (rev(ratings["item4"]) + ratings["item9"]) / 2
    O = (ratings["item5"] + rev(ratings["item10"])) / 2

    scores = {
        "E": E,
        "A": A,
        "C": C,
        "ES": ES,
        "O": O,
    }

    # MBTI風変換
    mapping = [
        ("E", E, "E", "I"),
        ("O", O, "N", "S"),
        ("A", A, "F", "T"),
        ("C", C, "J", "P"),
    ]

    mbti = ""
    ties = []

    for dimension, score, high, low in mapping:
        if score > 4:
            mbti += high
        elif score < 4:
            mbti += low
        else:
            mbti += "?"
            ties.append(dimension)

    return scores, mbti, ties


def load_characters_from_yml(yml_path: Path, names: List[str]) -> Dict[str, str]:
    """
    default_5.yml から指定された名前リストの personality を抽出する。
    """
    if not yml_path.exists():
        raise FileNotFoundError(f"設定ファイルが見つかりません: {yml_path}")

    with open(yml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    profiles = data.get("custom_profile", {}).get("profiles", [])
    profile_dict = {p["name"]: p.get("personality", "") for p in profiles if "name" in p}

    results: Dict[str, str] = {}
    missing: List[str] = []
    for name in names:
        if name in profile_dict and profile_dict[name].strip():
            results[name] = profile_dict[name].strip()
        else:
            missing.append(name)

    if missing:
        raise ValueError(f"以下のキャラクターが yml 内に見つからないか personality が空です: {missing}")

    return results


def extract_json_from_text(text: str) -> str:
    """テキスト中からJSON文字列を抽出する（コードブロック対応）。"""
    stripped = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", stripped)
    if match:
        return match.group(1).strip()
    return stripped


def build_rating_prompt(personality: str) -> str:
    """評定プロンプトを構築する。"""
    return RATING_PROMPT_TEMPLATE.format(PERSONALITY=personality)


def parse_rating_response(response_text: str) -> Tuple[Dict[str, int], Dict[str, str]]:
    """
    LLMレスポンスから ratings (item1〜item10) と reasons (item1〜item10) をパース・検証する。
    """
    json_str = extract_json_from_text(response_text)
    try:
        data = json.loads(json_str)
    except Exception as e:
        raise ValueError(f"JSONパースエラー: {e}")

    if not isinstance(data, dict):
        raise ValueError("レスポンスのトップレベルが辞書ではありません。")

    ratings_raw = data.get("ratings")
    reasons_raw = data.get("reasons")

    if not isinstance(ratings_raw, dict):
        raise ValueError("'ratings' キーが存在しないか辞書ではありません。")
    if not isinstance(reasons_raw, dict):
        raise ValueError("'reasons' キーが存在しないか辞書ではありません。")

    ratings: Dict[str, int] = {}
    reasons: Dict[str, str] = {}

    expected_keys = [f"item{i}" for i in range(1, 11)]

    for key in expected_keys:
        if key not in ratings_raw:
            raise ValueError(f"ratings に '{key}' が存在しません。")
        val = ratings_raw[key]
        # bool は int のサブクラスなので厳密にチェック
        if isinstance(val, bool) or not isinstance(val, int):
            raise ValueError(f"ratings['{key}'] の値 ({val}) が整数ではありません。")
        if not (1 <= val <= 7):
            raise ValueError(f"ratings['{key}'] の値 ({val}) が 1～7 の範囲外です。")
        ratings[key] = val

        if key not in reasons_raw:
            raise ValueError(f"reasons に '{key}' が存在しません。")
        reason_val = reasons_raw[key]
        if not isinstance(reason_val, str) or not reason_val.strip():
            raise ValueError(f"reasons['{key}'] の値が空または文字列ではありません。")
        reasons[key] = reason_val.strip()

    return ratings, reasons


def build_tiebreak_prompt(dimension: str, personality: str) -> str:
    """指定次元の tie-break プロンプトを構築する。"""
    if dimension not in TIEBREAK_CONFIG:
        raise ValueError(f"未知の次元です: {dimension}")

    cfg = TIEBREAK_CONFIG[dimension]
    return f"""以下の人物プロフィールについて、
{cfg['dim_text']}のどちらにより近いか判断してください。

A = {cfg['high_desc']}
B = {cfg['low_desc']}

簡潔な理由も示してください。

JSONのみで回答してください。

{{
  "choice": "A",
  "reason": "簡潔な理由"
}}

人物プロフィール：
{personality}"""


def parse_tiebreak_response(response_text: str) -> Tuple[str, str]:
    """
    tie-break レスポンスから choice ('A' または 'B') と reason をパース・検証する。
    """
    json_str = extract_json_from_text(response_text)
    try:
        data = json.loads(json_str)
    except Exception as e:
        raise ValueError(f"JSONパースエラー: {e}")

    if not isinstance(data, dict):
        raise ValueError("レスポンスのトップレベルが辞書ではありません。")

    choice = data.get("choice")
    reason = data.get("reason")

    if not isinstance(choice, str) or choice.strip().upper() not in ["A", "B"]:
        raise ValueError(f"choice の値 ({choice}) が 'A' または 'B' ではありません。")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError(f"reason の値が空または文字列ではありません。")

    return choice.strip().upper(), reason.strip()


def send_prompt_and_log(
    client: Any,
    config: Dict[str, Any],
    prompt_text: str,
    logs_dir: Path,
) -> Tuple[str, Optional[str]]:
    """
    API問い合わせを送信し、logs/ へログを保存して (response_text, reasoning_text) を返す。
    エラー時はエラーログを保存して例外を送出する。
    """
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
        "messages": [{"role": "user", "content": prompt_text}],
    }
    if temperature is not None:
        request_kwargs["temperature"] = temperature
    if max_tokens is not None:
        request_kwargs["max_tokens"] = max_tokens
    if extra_body:
        request_kwargs["extra_body"] = extra_body

    start_time = time.perf_counter()
    try:
        response = client.chat.completions.create(**request_kwargs)
        latency = time.perf_counter() - start_time

        if not response.choices:
            raise ValueError("APIから空のchoicesレスポンスが返却されました。")

        first_choice = response.choices[0]
        reasoning_text, response_text = extract_reasoning_and_response(first_choice)
        usage_data = extract_usage(response)

        save_json_log(
            logs_dir=logs_dir,
            success=True,
            config=config,
            prompt=prompt_text,
            response_text=response_text,
            reasoning_text=reasoning_text,
            usage=usage_data,
            latency_sec=latency,
        )

        if response_text is None:
            raise ValueError("APIレスポンスの content が空です。")

        return response_text, reasoning_text

    except Exception as e:
        latency = time.perf_counter() - start_time
        error_msg = str(e)
        error_type = type(e).__name__

        save_json_log(
            logs_dir=logs_dir,
            success=False,
            config=config,
            prompt=prompt_text,
            error_info={"error_type": error_type, "message": error_msg},
            latency_sec=latency,
        )
        raise RuntimeError(f"APIエラー ({error_type}): {error_msg}")


def resolve_tiebreaks(
    client: Any,
    config: Dict[str, Any],
    personality: str,
    ties: List[str],
    mbti_initial: str,
    max_retries: int,
    logs_dir: Path,
) -> Tuple[str, Dict[str, Dict[str, str]]]:
    """
    tie が発生した次元について LLM に決選判定を問い合わせ、mbti_like 文字列と tie_breaks 情報を確定する。
    """
    dimension_order = ["E", "O", "A", "C"]
    mbti_chars = list(mbti_initial)
    tie_breaks: Dict[str, Dict[str, str]] = {}

    for dim in ties:
        prompt = build_tiebreak_prompt(dim, personality)
        parsed_choice: Optional[str] = None
        parsed_reason: Optional[str] = None

        print(f"    [Tie-Break] 次元 {dim} の決選判定を実行中...")

        for attempt in range(1, max_retries + 1):
            try:
                resp_text, _ = send_prompt_and_log(client, config, prompt, logs_dir)
                choice, reason = parse_tiebreak_response(resp_text)
                parsed_choice = choice
                parsed_reason = reason
                break
            except Exception as e:
                print(f"      [WARN] Tie-Break 試行 {attempt}/{max_retries} 失敗: {e}")
                if attempt == max_retries:
                    raise RuntimeError(f"次元 {dim} の Tie-Break が最大リトライ回数 ({max_retries}) に達し失敗しました: {e}")

        resolved_char = TIEBREAK_CONFIG[dim]["choice_map"][parsed_choice]
        idx = dimension_order.index(dim)
        mbti_chars[idx] = resolved_char

        tie_breaks[dim] = {
            "choice": parsed_choice,
            "reason": parsed_reason,
            "resolved_type": resolved_char,
        }
        print(f"    [Tie-Break] 次元 {dim} -> {parsed_choice} ({resolved_char}) 確定")

    return "".join(mbti_chars), tie_breaks


def save_results(
    output_path: Path,
    config: Dict[str, Any],
    characters_results: List[Dict[str, Any]],
) -> None:
    """最終集計結果を results/mbti_like_characters.json へ保存する。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now().astimezone()

    model_config = config.get("model", {})
    generation_info = {
        "temperature": model_config.get("temperature"),
        "max_tokens": model_config.get("max_tokens"),
        "reasoning": config.get("reasoning"),
    }

    results_data = {
        "generated_at": now.isoformat(),
        "model": model_config.get("name"),
        "provider": config.get("provider"),
        "generation": generation_info,
        "experiment": config.get("experiment", {}),
        "characters": characters_results,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results_data, f, ensure_ascii=False, indent=2)

    print(f"\n[INFO] 最終結果を保存しました: {output_path}")


def run_experiment(
    config_path: str = "config.yml",
    yml_path: Optional[Path] = None,
    results_path: Optional[Path] = None,
    logs_dir: Optional[Path] = None,
) -> None:
    """固定10キャラクターの一括評定実験を実行する。"""
    config = load_config(config_path)
    client = create_client(config)

    target_yml = yml_path or resolve_path("src/default_5.yml")
    target_results = results_path or resolve_path("results/mbti_like_characters.json")
    target_logs = logs_dir or resolve_path("logs")

    max_rating_retries = config.get("experiment", {}).get("max_rating_retries", 3)
    max_tiebreak_retries = config.get("experiment", {}).get("max_tiebreak_retries", 3)

    print("==================================================")
    print(" 02_to_MBTI_like: 固定10キャラクター一括評定実験")
    print("==================================================")
    print(f"Model: {config.get('model', {}).get('name')}")
    print(f"Provider: {config.get('provider')}")
    print(f"対象キャラクター ({len(FIXED_CHARACTERS)}名): {', '.join(FIXED_CHARACTERS)}")
    print(f"最大リトライ: 評定={max_rating_retries}回, Tie-Break={max_tiebreak_retries}回")
    print("==================================================\n")

    personalities = load_characters_from_yml(target_yml, FIXED_CHARACTERS)
    characters_results: List[Dict[str, Any]] = []

    for idx, name in enumerate(FIXED_CHARACTERS, start=1):
        personality = personalities[name]
        print(f"[{idx}/{len(FIXED_CHARACTERS)}] '{name}' の評定を開始...")

        rating_prompt = build_rating_prompt(personality)
        ratings: Optional[Dict[str, int]] = None
        reasons: Optional[Dict[str, str]] = None

        # 評定問い合わせ（リトライ付き）
        for attempt in range(1, max_rating_retries + 1):
            try:
                resp_text, _ = send_prompt_and_log(client, config, rating_prompt, target_logs)
                ratings, reasons = parse_rating_response(resp_text)
                break
            except Exception as e:
                print(f"  [WARN] 評定 試行 {attempt}/{max_rating_retries} 失敗: {e}")
                if attempt == max_rating_retries:
                    raise RuntimeError(f"キャラクター '{name}' の評定が最大リトライ回数 ({max_rating_retries}) に達し失敗しました: {e}")

        # Big Five / MBTI風計算
        scores, mbti_raw, ties = to_mbti(ratings)
        print(f"  Big Five: E={scores['E']}, A={scores['A']}, C={scores['C']}, ES={scores['ES']}, O={scores['O']}")
        print(f"  MBTI (暫定): {mbti_raw} (Ties: {ties if ties else 'なし'})")

        # tie-break (決選判定)
        tie_breaks: Dict[str, Dict[str, str]] = {}
        mbti_final = mbti_raw
        if ties:
            mbti_final, tie_breaks = resolve_tiebreaks(
                client=client,
                config=config,
                personality=personality,
                ties=ties,
                mbti_initial=mbti_raw,
                max_retries=max_tiebreak_retries,
                logs_dir=target_logs,
            )
            print(f"  MBTI (確定): {mbti_final}")

        char_data = {
            "name": name,
            "personality": personality,
            "ratings": ratings,
            "reasons": reasons,
            "big_five": scores,
            "ties": ties,
            "tie_breaks": tie_breaks,
            "mbti_like": mbti_final,
        }
        characters_results.append(char_data)
        print(f"  => '{name}' 完了: MBTI風 = {mbti_final}\n")

    # 全10名分を保存
    save_results(target_results, config, characters_results)

    # サマリー表示
    print("\n==================================================")
    print(" 実験結果サマリー (全10名)")
    print("==================================================")
    print(f"{'No.':<4} {'名前':<8} {'E':>4} {'A':>4} {'C':>4} {'ES':>4} {'O':>4}  {'MBTI風':<6} {'TieBreak'}")
    print("-" * 55)
    for idx, c in enumerate(characters_results, start=1):
        bf = c["big_five"]
        tb_info = ", ".join([f"{k}->{v['resolved_type']}" for k, v in c["tie_breaks"].items()]) if c["tie_breaks"] else "-"
        print(f"{idx:<4} {c['name']:<8} {bf['E']:>4.1f} {bf['A']:>4.1f} {bf['C']:>4.1f} {bf['ES']:>4.1f} {bf['O']:>4.1f}  {c['mbti_like']:<6} {tb_info}")
    print("==================================================")


if __name__ == "__main__":
    try:
        run_experiment()
    except Exception as e:
        print(f"\n[FATAL ERROR] 実験が異常終了しました: {e}", file=sys.stderr)
        sys.exit(1)
