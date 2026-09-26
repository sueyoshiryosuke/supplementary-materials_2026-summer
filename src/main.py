"""
最小LLM実行CUIアプリ (Simple LLM Research Console)
研究実験用: 任意のプロンプトをLLMへ送信し、レスポンスを表示 & JSONログとして保存する。
"""

import datetime
import os
import sys
import time
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from dotenv import load_dotenv
from openai import OpenAI


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def resolve_path(relative_or_absolute: Path | str) -> Path:
    """プロジェクトルート基準でパスを解決する。"""
    p = Path(relative_or_absolute)
    if p.is_absolute():
        return p
    # カレントディレクトリに存在する場合はそれを優先、無ければPROJECT_ROOT基準
    if p.exists():
        return p
    return PROJECT_ROOT / p


def load_config(config_path: str = "config.yml") -> Dict[str, Any]:
    """config.yml を読み込む。"""
    path = resolve_path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"設定ファイルが見つかりません: {config_path}")
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    if not isinstance(config, dict):
        raise ValueError("config.yml の形式が正しくありません。")
    return config


def get_api_key(config: Dict[str, Any]) -> str:
    """環境変数からAPIキーを取得する。.envをロードするが内容は一切表示・記録しない。"""
    env_path = resolve_path(".env")
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    else:
        load_dotenv()
    api_key_env = config.get("api", {}).get("api_key_env", "OPENROUTER_API_KEY")
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise ValueError(f"環境変数 '{api_key_env}' に API キーが設定されていません。")
    return api_key


def create_client(config: Dict[str, Any]) -> OpenAI:
    """OpenAI互換クライアントを生成する。"""
    base_url = config.get("api", {}).get("base_url", "https://openrouter.ai/api/v1")
    api_key = get_api_key(config)
    return OpenAI(base_url=base_url, api_key=api_key)


def get_unique_log_filepath(logs_dir: Path, now: datetime.datetime) -> Path:
    """logs/ ディレクトリ内で重複しない YYYYMMDD_HHMMSS.json のパスを生成する。"""
    base_name = now.strftime("%Y%m%d_%H%M%S")
    candidate = logs_dir / f"{base_name}.json"
    counter = 2
    while candidate.exists():
        candidate = logs_dir / f"{base_name}_{counter}.json"
        counter += 1
    return candidate


def save_json_log(
    logs_dir: Path,
    success: bool,
    config: Dict[str, Any],
    prompt: str,
    response_text: Optional[str] = None,
    reasoning_text: Optional[str] = None,
    usage: Optional[Dict[str, Any]] = None,
    latency_sec: Optional[float] = None,
    error_info: Optional[Dict[str, Any]] = None,
) -> Path:
    """JSONログを保存する。秘密情報は絶対に含めない。"""
    logs_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now().astimezone()
    filepath = get_unique_log_filepath(logs_dir, now)

    model_config = config.get("model", {})
    generation_info: Dict[str, Any] = {
        "temperature": model_config.get("temperature"),
        "max_tokens": model_config.get("max_tokens"),
        "reasoning": config.get("reasoning"),
        "provider": config.get("provider"),
    }

    log_data: Dict[str, Any] = {
        "timestamp": now.isoformat(),
        "success": success,
        "base_url": config.get("api", {}).get("base_url"),
        "model": model_config.get("name"),
        "provider": config.get("provider"),
        "prompt": prompt,
        "generation": generation_info,
        "latency_sec": round(latency_sec, 3) if latency_sec is not None else None,
    }

    if success:
        log_data["reasoning"] = reasoning_text
        log_data["response"] = response_text
        log_data["usage"] = usage or {}
    else:
        log_data["error"] = error_info or {"message": "Unknown error"}

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)

    return filepath


def extract_reasoning_and_response(choice: Any) -> Tuple[Optional[str], Optional[str]]:
    """レスポンスから reasoning と final response を分離取得する。"""
    message = getattr(choice, "message", None)
    if not message:
        return None, None

    response_text = getattr(message, "content", None)

    reasoning_text = getattr(message, "reasoning_content", None)
    if not reasoning_text:
        reasoning_text = getattr(message, "reasoning", None)
    if not reasoning_text and hasattr(message, "model_extra") and isinstance(message.model_extra, dict):
        reasoning_text = message.model_extra.get("reasoning_content") or message.model_extra.get("reasoning")

    return reasoning_text, response_text


def extract_usage(response: Any) -> Dict[str, Any]:
    """レスポンスから usage 情報を取得可能な範囲で抽出する。推測値は作らない。"""
    usage = getattr(response, "usage", None)
    if not usage:
        return {}

    usage_data: Dict[str, Any] = {}
    if hasattr(usage, "prompt_tokens") and usage.prompt_tokens is not None:
        usage_data["input_tokens"] = usage.prompt_tokens
    if hasattr(usage, "completion_tokens") and usage.completion_tokens is not None:
        usage_data["output_tokens"] = usage.completion_tokens
    if hasattr(usage, "total_tokens") and usage.total_tokens is not None:
        usage_data["total_tokens"] = usage.total_tokens

    # completion_tokens_details (reasoning_tokens)
    details = getattr(usage, "completion_tokens_details", None)
    if details:
        reasoning_tokens = getattr(details, "reasoning_tokens", None)
        if reasoning_tokens is not None:
            usage_data["reasoning_tokens"] = reasoning_tokens

    return usage_data


def execute_prompt(
    client: OpenAI,
    config: Dict[str, Any],
    prompt_text: str,
    logs_dir: Optional[Path] = None,
) -> bool:
    """
    LLM API へ問い合わせを送信し、結果を表示してログを保存する。
    各リクエストは完全に独立（stateless）であり、過去の履歴は含めない。
    """
    target_logs_dir = resolve_path("logs") if logs_dir is None else Path(logs_dir)
    model_name = config.get("model", {}).get("name")
    temperature = config.get("model", {}).get("temperature", 1.0)
    max_tokens = config.get("model", {}).get("max_tokens")

    # OpenRouter 用 extra_body パラメータ構築 (Reasoning ON / Provider 固定)
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

    print("\n[INFO] LLMへ問い合わせ中...")
    start_time = time.perf_counter()

    try:
        response = client.chat.completions.create(**request_kwargs)
        latency = time.perf_counter() - start_time

        if not response.choices:
            raise ValueError("APIから空のchoicesレスポンスが返却されました。")

        first_choice = response.choices[0]
        reasoning_text, response_text = extract_reasoning_and_response(first_choice)
        usage_data = extract_usage(response)

        # レスポンス表示
        if reasoning_text:
            print("\n===== REASONING =====")
            print(reasoning_text)
            print("=====================")

        print("\n===== RESPONSE =====")
        print(response_text if response_text is not None else "(空のレスポンス)")
        print("====================")

        # ログ保存
        log_path = save_json_log(
            logs_dir=target_logs_dir,
            success=True,
            config=config,
            prompt=prompt_text,
            response_text=response_text,
            reasoning_text=reasoning_text,
            usage=usage_data,
            latency_sec=latency,
        )
        print(f"\n[INFO] ログを保存しました: {log_path}")
        return True

    except Exception as e:
        latency = time.perf_counter() - start_time
        error_msg = str(e)
        error_type = type(e).__name__
        print(f"\n[ERROR] APIエラーが発生しました ({error_type}): {error_msg}", file=sys.stderr)

        # エラー時も秘密情報を除外したログを保存
        log_path = save_json_log(
            logs_dir=target_logs_dir,
            success=False,
            config=config,
            prompt=prompt_text,
            error_info={"error_type": error_type, "message": error_msg},
            latency_sec=latency,
        )
        print(f"[INFO] エラーログを保存しました: {log_path}", file=sys.stderr)
        return False


def get_direct_input_prompt() -> Optional[str]:
    """CUI上で複数行のプロンプトを直接入力する。"""
    print("\n--- プロンプト直接入力 ---")
    print("プロンプトを入力してください。")
    print("単独行で '.send' と入力すると送信します。('.cancel' で中止)")
    print("--------------------------")

    lines: List[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == ".send":
            break
        if line.strip() == ".cancel":
            print("[INFO] 入力をキャンセルしました。")
            return None
        lines.append(line)

    prompt_text = "\n".join(lines)
    if not prompt_text.strip():
        print("[WARN] プロンプトが空です。送信を中止しました。")
        return None
    return prompt_text


def get_prompt_from_file(prompt_dir: Optional[Path] = None) -> Optional[str]:
    """prompt/ フォルダ内の .txt ファイル一覧から1つ選択して内容を読み込む。"""
    target_prompt_dir = resolve_path("prompt") if prompt_dir is None else Path(prompt_dir)
    if not target_prompt_dir.exists() or not target_prompt_dir.is_dir():
        print(f"\n[ERROR] ディレクトリ '{target_prompt_dir}' が存在しません。")
        return None

    txt_files = sorted(list(target_prompt_dir.glob("*.txt")))
    if not txt_files:
        print(f"\n[ERROR] '{target_prompt_dir}' ディレクトリ内に .txt ファイルが見つかりません。")
        return None

    print(f"\n--- {target_prompt_dir.name}/ からファイルを選択 ---")
    for idx, file_path in enumerate(txt_files, start=1):
        print(f"[{idx}] {file_path.name}")
    print("[b] 戻る")
    print("-----------------------------------")

    while True:
        try:
            choice = input("\n番号を選択してください: ").strip()
        except EOFError:
            return None

        if choice.lower() == "b":
            return None

        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(txt_files):
                selected_file = txt_files[idx - 1]
                try:
                    with open(selected_file, "r", encoding="utf-8") as f:
                        content = f.read()
                    if not content.strip():
                        print(f"[WARN] ファイル '{selected_file.name}' は空です。")
                        return None
                    print(f"[INFO] '{selected_file.name}' を読み込みました。")
                    return content
                except Exception as e:
                    print(f"[ERROR] ファイル読み込みに失敗しました: {e}")
                    return None

        print("無効な選択です。正しい番号または 'b' を入力してください。")


def main():
    """メインループ"""
    try:
        config = load_config("config.yml")
    except Exception as e:
        print(f"[FATAL] 設定ファイルの読み込みに失敗しました: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        client = create_client(config)
    except Exception as e:
        print(f"[FATAL] クライアントの初期化に失敗しました: {e}", file=sys.stderr)
        sys.exit(1)

    model_name = config.get("model", {}).get("name", "Unknown")
    reasoning_enabled = config.get("reasoning", {}).get("enabled", False)

    while True:
        print("\n========================================")
        print(" Simple LLM Research Console")
        print("========================================")
        print(f"Model: {model_name}")
        print(f"Reasoning: {'ON' if reasoning_enabled else 'OFF'}")
        print()
        print("[1] プロンプトを直接入力")
        print("[2] prompt/ からプロンプトを選択")
        print("[q] 終了")
        print("========================================")

        try:
            choice = input("\n選択してください: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n終了します。")
            break

        if choice == "1":
            prompt = get_direct_input_prompt()
            if prompt is not None:
                execute_prompt(client, config, prompt)
        elif choice == "2":
            prompt = get_prompt_from_file()
            if prompt is not None:
                execute_prompt(client, config, prompt)
        elif choice.lower() == "q":
            print("\n終了します。")
            break
        else:
            print("無効な選択です。1, 2, または q を入力してください。")


if __name__ == "__main__":
    main()
