#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
05_export_form_data.py

results/generated_utterances.json と src/default_5.yml を統合し、
Google Apps Script (GAS) フォーム自動生成用のデータファイル (gas/formData.gs, results/form_data.json) を生成する。

【Form A / B の割当ルール】
- ctx_01, ctx_03, ctx_05, ctx_07, ctx_09:
    Form A: Full条件で生成された発話
    Form B: MBTI条件で生成された発話
- ctx_02, ctx_04, ctx_06, ctx_08, ctx_10:
    Form A: MBTI条件で生成された発話
    Form B: Full条件で生成された発話

【回答者に表示する情報】
- 年齢、性別、元のpersonality全文、役職、登場人物5名と公開情報、現在のゲーム状況、発話
※ condition, mbti_like, context_id, Full/MBTIの区別等の内部情報は非表示（データ構造には内部識別用に保持）
"""

import json
from pathlib import Path
from typing import Any, Dict, List
import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
RESULTS_DIR = ROOT_DIR / "results"
GAS_DIR = ROOT_DIR / "gas"

GENERATED_UTTERANCES_FILE = RESULTS_DIR / "generated_utterances.json"
DEFAULT_5_FILE = SRC_DIR / "default_5.yml"
OUTPUT_JSON_FILE = RESULTS_DIR / "form_data.json"
OUTPUT_GAS_FILE = GAS_DIR / "formData.gs"

# 割当ルール定義
# ctx_id -> (Form A condition, Form B condition)
CONDITION_ASSIGNMENTS = {
    "ctx_01": ("full", "mbti"),
    "ctx_02": ("mbti", "full"),
    "ctx_03": ("full", "mbti"),
    "ctx_04": ("mbti", "full"),
    "ctx_05": ("full", "mbti"),
    "ctx_06": ("mbti", "full"),
    "ctx_07": ("full", "mbti"),
    "ctx_08": ("mbti", "full"),
    "ctx_09": ("full", "mbti"),
    "ctx_10": ("mbti", "full"),
}


def load_generated_utterances(path: Path) -> List[Dict[str, Any]]:
    """generated_utterances.json から全レコードを読み込む。"""
    if not path.exists():
        raise FileNotFoundError(f"ファイルが見つかりません: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("records", [])


def load_default_profiles(path: Path) -> Dict[str, Dict[str, Any]]:
    """default_5.yml から全キャラクターのプロファイル（personality等）を読み込む。"""
    if not path.exists():
        raise FileNotFoundError(f"default_5.yml が見つかりません: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    profiles = data.get("custom_profile", {}).get("profiles", [])
    return {p["name"]: p for p in profiles if "name" in p}


def build_form_records(
    records: List[Dict[str, Any]],
    profiles: Dict[str, Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """
    generated_utterances レコードと default_5 プロファイルを結合し、
    Form A および Form B 用の10問ずつのレコードリストを作成する。
    """
    # (context_id, condition) -> record のマップを作成
    record_map: Dict[tuple, Dict[str, Any]] = {}
    for r in records:
        key = (r["context_id"], r["condition"])
        record_map[key] = r

    form_a_list: List[Dict[str, Any]] = []
    form_b_list: List[Dict[str, Any]] = []

    for q_idx, (ctx_id, (cond_a, cond_b)) in enumerate(CONDITION_ASSIGNMENTS.items(), start=1):
        # --- Form A ---
        rec_a = record_map.get((ctx_id, cond_a))
        if not rec_a:
            raise ValueError(f"Form A レコードが見つかりません: context={ctx_id}, condition={cond_a}")
        char_name_a = rec_a["character_id"]
        prof_a = profiles.get(char_name_a, {})
        personality_a = prof_a.get("personality", "")
        if not personality_a:
            raise ValueError(f"キャラクター '{char_name_a}' の personality が取得できません")

        item_a = {
            "question_num": q_idx,
            "context_id": ctx_id,
            "condition": cond_a,
            "character_id": char_name_a,
            "age": rec_a["age"],
            "gender": rec_a["gender"],
            "role": rec_a["role"],
            "personality": personality_a,
            "players": rec_a["players"],
            "situation": rec_a["situation"],
            "utterance": rec_a["utterance"],
        }
        form_a_list.append(item_a)

        # --- Form B ---
        rec_b = record_map.get((ctx_id, cond_b))
        if not rec_b:
            raise ValueError(f"Form B レコードが見つかりません: context={ctx_id}, condition={cond_b}")
        char_name_b = rec_b["character_id"]
        prof_b = profiles.get(char_name_b, {})
        personality_b = prof_b.get("personality", "")
        if not personality_b:
            raise ValueError(f"キャラクター '{char_name_b}' の personality が取得できません")

        item_b = {
            "question_num": q_idx,
            "context_id": ctx_id,
            "condition": cond_b,
            "character_id": char_name_b,
            "age": rec_b["age"],
            "gender": rec_b["gender"],
            "role": rec_b["role"],
            "personality": personality_b,
            "players": rec_b["players"],
            "situation": rec_b["situation"],
            "utterance": rec_b["utterance"],
        }
        form_b_list.append(item_b)

    return {
        "form_a": form_a_list,
        "form_b": form_b_list,
    }


def export_gas_file(form_data: Dict[str, Any], output_path: Path) -> None:
    """form_data 辞書を GAS 用の JavaScript 定数ファイル (formData.gs) として出力する。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    json_str = json.dumps(form_data, ensure_ascii=False, indent=2)
    gas_content = f"""// ===========================================================================
// formData.gs
// 自動生成スクリプト: src/05_export_form_data.py
// 評価アンケート Form A / Form B 用データ定義
// ===========================================================================

/**
 * 評価対象データ (Form A 10問 / Form B 10問)
 * 各問には、登場人物5名、状況説明、対象人物のプロフィール(元のpersonality全文含む)、
 * および生成された発話が含まれます。
 */
const FORM_DATA = {json_str};
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(gas_content)


def main() -> None:
    print("=" * 60)
    print(" 05_export_form_data: Form A / B 用データのエクスポート開始")
    print("=" * 60)

    records = load_generated_utterances(GENERATED_UTTERANCES_FILE)
    print(f"[INFO] 発話レコード読み込み: {len(records)} 件")

    profiles = load_default_profiles(DEFAULT_5_FILE)
    print(f"[INFO] default_5 プロファイル読み込み: {len(profiles)} 人物")

    form_data = build_form_records(records, profiles)
    print(f"[INFO] Form A 設問数: {len(form_data['form_a'])} 件 (Full: 5, MBTI: 5)")
    print(f"[INFO] Form B 設問数: {len(form_data['form_b'])} 件 (Full: 5, MBTI: 5)")

    # JSON出力
    OUTPUT_JSON_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(form_data, f, ensure_ascii=False, indent=2)
    print(f"[INFO] JSON保存完了: {OUTPUT_JSON_FILE}")

    # GASファイル出力
    export_gas_file(form_data, OUTPUT_GAS_FILE)
    print(f"[INFO] GASファイル保存完了: {OUTPUT_GAS_FILE}")

    print("=" * 60)
    print(" エクスポート完了")
    print("=" * 60)


if __name__ == "__main__":
    main()
