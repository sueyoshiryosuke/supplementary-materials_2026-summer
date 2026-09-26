"""
04_generate_utterances.py
10個の評価局面それぞれに固定10キャラクターを割り当て、
Full personality 条件と MBTI-like 条件で各1発話（合計20発話）を生成する。
"""

import datetime
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from openai import OpenAI

# src ディレクトリを sys.path に追加して main.py をインポート
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import main


# ---------------------------------------------------------------------------
# 定数定義
# ---------------------------------------------------------------------------

CHARACTER_ASSIGNMENTS: Dict[str, str] = {
    "ctx_01": "ミオ",
    "ctx_02": "メイ",
    "ctx_03": "ダイスケ",
    "ctx_04": "リン",
    "ctx_05": "リュウジ",
    "ctx_06": "ミドリ",
    "ctx_07": "ジョージ",
    "ctx_08": "シズエ",
    "ctx_09": "トシオ",
    "ctx_10": "ケンジ",
}

SYSTEM_PROMPT_TEMPLATE = """あなたは人狼ゲームのプレイヤーとして発話を行ってください。

【登場人物（5人村）】
{players_text}

【現在のゲーム状況】
{situation}

【あなたの人物プロフィール】
{profile_text}

【発話の要件】
- 「あなた」と指定された人物として発話してください。
- 与えられた役職はあなただけが知る非公開の情報です。
- あなたが人狼である場合、人狼であることを公開発話で明かさないでください。
- 状況に書かれていない事実を勝手に追加しないでください。
- 登場人物に存在しない人物名を出さないでください。
- 人物プロフィールに合う自然な日本語で話してください。
- 1回の発話として自然な1～2文で記述してください。
- 100文字以内で記述してください。
- 発話本文のみを出力してください。「発話:」「回答:」などのラベル、引用符、解説、思考過程などのメタ的な前置きは含めないでください。
- MBTI、personality、プロフィール、性格タイプなどのメタ情報には言及しないでください。"""


# ---------------------------------------------------------------------------
# データロード関数
# ---------------------------------------------------------------------------

def load_evaluation_contexts(path: Path) -> List[Dict[str, Any]]:
    """evaluation_contexts.json を読み込む。"""
    if not path.exists():
        raise FileNotFoundError(f"評価局面ファイルが見つかりません: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    contexts = data.get("contexts", [])
    if len(contexts) != 10:
        raise ValueError(f"コンテキスト数が10件ではありません: {len(contexts)} 件")
    return contexts


def load_mbti_like_characters(path: Path) -> Dict[str, Dict[str, Any]]:
    """mbti_like_characters.json からキャラクター辞書を作成する。"""
    if not path.exists():
        raise FileNotFoundError(f"MBTI評定結果ファイルが見つかりません: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    chars = data.get("characters", [])
    char_dict = {c["name"]: c for c in chars if "name" in c}
    return char_dict


def load_default_profiles(path: Path) -> Dict[str, Dict[str, Any]]:
    """default_5.yml からカスタムプロファイル（age, gender, personality等）を読み込む。"""
    if not path.exists():
        raise FileNotFoundError(f"default_5.yml が見つかりません: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    profiles = data.get("custom_profile", {}).get("profiles", [])
    prof_dict = {p["name"]: p for p in profiles if "name" in p}
    return prof_dict


# ---------------------------------------------------------------------------
# プロンプト構築関数
# ---------------------------------------------------------------------------

def format_players_text(players: List[Dict[str, str]]) -> str:
    """登場人物リストをプロンプト用にフォーマットする。"""
    lines = []
    for p in players:
        name = p.get("name", "")
        relation = p.get("relation", "")
        if relation:
            lines.append(f"- {name}: {relation}")
        else:
            lines.append(f"- {name}")
    return "\n".join(lines)


def assign_character_to_context(
    context: Dict[str, Any],
    char_name: str,
) -> Dict[str, Any]:
    """
    コンテキストの「あなた」の人物名を char_name に置換した新しいコンテキスト辞書を返す。
    「あなた」スロットの players[].name、全 players[].relation、および situation 内の
    旧対象名（old_target_name）を char_name へ一貫して置換する。
    """
    # 1. 置換前の「あなた」の名前を取得
    old_target_name = None
    for p in context.get("players", []):
        if "あなた" in p.get("relation", ""):
            old_target_name = p.get("name")
            break

    new_context = dict(context)
    new_players = []
    for p in context.get("players", []):
        p_copy = dict(p)
        if "あなた" in p_copy.get("relation", ""):
            p_copy["name"] = char_name
        # relation 内の旧名を新名へ置換
        if old_target_name and old_target_name in p_copy.get("relation", ""):
            p_copy["relation"] = p_copy["relation"].replace(old_target_name, char_name)
        new_players.append(p_copy)
    new_context["players"] = new_players

    # situation 内の旧名を新名へ置換
    if old_target_name and old_target_name in new_context.get("situation", ""):
        new_context["situation"] = new_context["situation"].replace(old_target_name, char_name)

    return new_context


def build_profile_text(
    condition: str,
    age: Any,
    gender: str,
    personality: Optional[str] = None,
    mbti_like: Optional[str] = None,
) -> str:
    """Full条件またはMBTI条件に応じたプロフィール文字列を作成する。"""
    if condition == "full":
        if personality is None:
            raise ValueError("Full条件には personality が必要です。")
        return f"age: {age}\ngender: {gender}\npersonality: {personality}"
    elif condition == "mbti":
        if mbti_like is None:
            raise ValueError("MBTI条件には mbti_like が必要です。")
        return f"age: {age}\ngender: {gender}\nMBTI: {mbti_like}"
    else:
        raise ValueError(f"未知の条件です: {condition}")


def build_utterance_prompt(
    context: Dict[str, Any],
    condition: str,
    age: Any,
    gender: str,
    personality: Optional[str] = None,
    mbti_like: Optional[str] = None,
) -> str:
    """発話生成用のプロンプトを作成する。"""
    players_text = format_players_text(context["players"])
    situation = context["situation"]
    profile_text = build_profile_text(
        condition=condition,
        age=age,
        gender=gender,
        personality=personality,
        mbti_like=mbti_like,
    )
    return SYSTEM_PROMPT_TEMPLATE.format(
        players_text=players_text,
        situation=situation,
        profile_text=profile_text,
    )


# ---------------------------------------------------------------------------
# 発話テキストのクリーンアップ・バリデーション
# ---------------------------------------------------------------------------

def clean_utterance(text: str) -> str:
    """出力された発話から余計なラベルや引用符を除去する。"""
    cleaned = text.strip()
    # 先頭のラベル除去
    prefixes = ["発話:", "発話：", "回答:", "回答：", "発言:", "発言："]
    for p in prefixes:
        if cleaned.startswith(p):
            cleaned = cleaned[len(p):].strip()

    # 外側の引用符（「」、“”、「」）のペア除去
    if (cleaned.startswith("「") and cleaned.endswith("」")) or \
       (cleaned.startswith('"') and cleaned.endswith('"')) or \
       (cleaned.startswith('“') and cleaned.endswith('”')) or \
       (cleaned.startswith("'") and cleaned.endswith("'")):
        cleaned = cleaned[1:-1].strip()

    return cleaned


# ---------------------------------------------------------------------------
# LLM 呼び出し & リトライ処理
# ---------------------------------------------------------------------------

def query_utterance(
    client: OpenAI,
    config: Dict[str, Any],
    prompt: str,
    logs_dir: Path,
    max_retries: int = 3,
) -> Tuple[str, str]:
    """
    LLM API へ問い合わせ、発話を生成する。
    成功時は (utterance, reasoning) を返す。
    失敗時は例外を送出する。
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
        "messages": [{"role": "user", "content": prompt}],
    }
    if temperature is not None:
        request_kwargs["temperature"] = temperature
    if max_tokens is not None:
        request_kwargs["max_tokens"] = max_tokens
    if extra_body:
        request_kwargs["extra_body"] = extra_body

    for attempt in range(1, max_retries + 1):
        start_time = time.perf_counter()
        try:
            response = client.chat.completions.create(**request_kwargs)
            latency = time.perf_counter() - start_time

            if not response.choices:
                raise ValueError("APIから空のchoicesレスポンスが返却されました。")

            first_choice = response.choices[0]
            reasoning_text, response_text = main.extract_reasoning_and_response(first_choice)
            usage_data = main.extract_usage(response)

            # ログ保存
            main.save_json_log(
                logs_dir=logs_dir,
                success=True,
                config=config,
                prompt=prompt,
                response_text=response_text,
                reasoning_text=reasoning_text,
                usage=usage_data,
                latency_sec=latency,
            )

            if not response_text or not response_text.strip():
                raise ValueError("空の発話レスポンスが返却されました。")

            utterance = clean_utterance(response_text)
            if not utterance:
                raise ValueError("クリーンアップ後の発話が空になりました。")

            return utterance, reasoning_text or ""

        except Exception as e:
            latency = time.perf_counter() - start_time
            error_msg = str(e)
            error_type = type(e).__name__

            main.save_json_log(
                logs_dir=logs_dir,
                success=False,
                config=config,
                prompt=prompt,
                error_info={"error_type": error_type, "message": error_msg, "attempt": attempt},
                latency_sec=latency,
            )
            print(f"[WARN] 試行 {attempt}/{max_retries} 失敗: {error_msg}", file=sys.stderr)
            if attempt == max_retries:
                raise RuntimeError(f"最大リトライ回数({max_retries})を超過しました: {error_msg}")
            time.sleep(1.0)

    raise RuntimeError("予期しないエラーにより発話取得に失敗しました。")


# ---------------------------------------------------------------------------
# メイン一括生成処理
# ---------------------------------------------------------------------------

def generate_all_utterances(
    config: Dict[str, Any],
    contexts_file: Path,
    mbti_file: Path,
    default_5_file: Path,
    output_file: Path,
    logs_dir: Path,
    client: Optional[OpenAI] = None,
) -> Dict[str, Any]:
    """
    10局面 × 2条件（Full / MBTI）の合計20発話を一括生成し、JSONとして保存する。
    全件成功時のみ output_file を書き出す。
    """
    if client is None:
        client = main.create_client(config)

    # 1. 各種入力データのロード
    raw_contexts = load_evaluation_contexts(contexts_file)
    mbti_chars = load_mbti_like_characters(mbti_file)
    default_profiles = load_default_profiles(default_5_file)

    ctx_map = {c["context_id"]: c for c in raw_contexts}

    # 2. 生成対象の20タスクを定義
    tasks = []
    for ctx_id, char_name in CHARACTER_ASSIGNMENTS.items():
        if ctx_id not in ctx_map:
            raise KeyError(f"コンテキストID '{ctx_id}' が評価局面データに存在しません。")
        if char_name not in mbti_chars:
            raise KeyError(f"キャラクター '{char_name}' がMBTIデータに存在しません。")
        if char_name not in default_profiles:
            raise KeyError(f"キャラクター '{char_name}' がdefault_5.ymlに存在しません。")

        base_ctx = ctx_map[ctx_id]
        assigned_ctx = assign_character_to_context(base_ctx, char_name)

        prof = default_profiles[char_name]
        mbti_info = mbti_chars[char_name]

        age = prof.get("age")
        gender = prof.get("gender")
        personality = prof.get("personality")
        mbti_like = mbti_info.get("mbti_like")

        # Full条件タスク
        tasks.append({
            "context_id": ctx_id,
            "character_id": char_name,
            "condition": "full",
            "role": base_ctx.get("role", ""),
            "age": age,
            "gender": gender,
            "personality": personality,
            "mbti_like": mbti_like,
            "context": assigned_ctx,
        })
        # MBTI条件タスク
        tasks.append({
            "context_id": ctx_id,
            "character_id": char_name,
            "condition": "mbti",
            "role": base_ctx.get("role", ""),
            "age": age,
            "gender": gender,
            "personality": personality,
            "mbti_like": mbti_like,
            "context": assigned_ctx,
        })

    print(f"==================================================")
    print(f" 04_generate_utterances: 計 {len(tasks)} 件の発話生成を開始")
    print(f" Model: {config.get('model', {}).get('name')}")
    print(f"==================================================")

    records: List[Dict[str, Any]] = []

    # 3. 20件のタスクを順次実行（独立したAPIリクエスト）
    for idx, t in enumerate(tasks, start=1):
        ctx_id = t["context_id"]
        char_name = t["character_id"]
        cond = t["condition"]
        assigned_ctx = t["context"]

        print(f"[{idx:02d}/{len(tasks):02d}] {ctx_id} ({char_name} / {cond.upper()}) 発話生成中...")

        # 条件に応じたプロンプト構築
        if cond == "full":
            prompt = build_utterance_prompt(
                context=assigned_ctx,
                condition="full",
                age=t["age"],
                gender=t["gender"],
                personality=t["personality"],
            )
        else:
            prompt = build_utterance_prompt(
                context=assigned_ctx,
                condition="mbti",
                age=t["age"],
                gender=t["gender"],
                mbti_like=t["mbti_like"],
            )

        utterance, reasoning = query_utterance(
            client=client,
            config=config,
            prompt=prompt,
            logs_dir=logs_dir,
        )

        print(f"  → 生成結果: {utterance} ({len(utterance)}文字)")

        record = {
            "context_id": ctx_id,
            "character_id": char_name,
            "condition": cond,
            "role": t["role"],
            "age": t["age"],
            "gender": t["gender"],
            "mbti_like": t["mbti_like"],
            "players": assigned_ctx["players"],
            "situation": assigned_ctx["situation"],
            "utterance": utterance,
        }
        records.append(record)

    # 4. 全件成功時のみファイル保存
    output_data = {
        "generated_at": datetime.datetime.now().astimezone().isoformat(),
        "model": config.get("model", {}).get("name"),
        "provider": config.get("provider", {}),
        "generation": {
            "temperature": config.get("model", {}).get("temperature"),
            "max_tokens": config.get("model", {}).get("max_tokens"),
            "reasoning": config.get("reasoning", {}),
        },
        "total_records": len(records),
        "records": records,
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"\n[INFO] 全 {len(records)} 件の発話生成が完了し、保存しました: {output_file}")
    return output_data


def main_cli() -> None:
    """CLIエントリポイント"""
    config = main.load_config("config.yml")
    contexts_file = main.resolve_path("results/evaluation_contexts.json")
    mbti_file = main.resolve_path("results/mbti_like_characters.json")
    default_5_file = main.resolve_path("src/default_5.yml")
    output_file = main.resolve_path("results/generated_utterances.json")
    logs_dir = main.resolve_path("logs")

    generate_all_utterances(
        config=config,
        contexts_file=contexts_file,
        mbti_file=mbti_file,
        default_5_file=default_5_file,
        output_file=output_file,
        logs_dir=logs_dir,
    )


if __name__ == "__main__":
    main_cli()
