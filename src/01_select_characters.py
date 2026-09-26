import random

"""
実行結果

seed = 20260817

01. ケンジ      12歳  男性  0-12
02. リン        9歳  女性  0-12
03. ダイスケ     16歳  男性  13-19
04. ミオ       17歳  女性  13-19
05. リュウジ     28歳  男性  20-39
06. トシオ      28歳  男性  20-39
07. メイ       24歳  女性  20-39
08. ミドリ      38歳  女性  20-39
09. ジョージ     65歳  男性  40+
10. シズエ      78歳  女性  40+

合計: 10名
男性: 5 女性: 5
"""

SEED = 20260817

profiles = [
    # 男性
    ("ミナト", 10, "男性"),
    ("タクミ", 10, "男性"),
    ("ケンジ", 12, "男性"),
    ("リュウジ", 28, "男性"),
    ("ダイスケ", 16, "男性"),
    ("シオン", 16, "男性"),
    ("ベンジャミン", 28, "男性"),
    ("トシオ", 28, "男性"),
    ("ジョナサン", 38, "男性"),
    ("シュンイチ", 32, "男性"),
    ("ジョージ", 65, "男性"),
    ("セルヴァス", 85, "男性"),

    # 女性
    ("サクラ", 10, "女性"),
    ("リン", 9, "女性"),
    ("ユミ", 16, "女性"),
    ("メイ", 24, "女性"),
    ("ミサキ", 24, "女性"),
    ("ミオ", 17, "女性"),
    ("ミヅキ", 24, "女性"),
    ("ミナコ", 28, "女性"),
    ("アスカ", 29, "女性"),
    ("ミドリ", 38, "女性"),
    ("ヴィクトリア", 37, "女性"),
    ("シズエ", 78, "女性"),
]

# 年齢層ごとの抽出人数
# （40歳以上を「高齢者」とは呼ばない。チャッピー反省済み）
strata = [
    ("0-12",  0, 12, {"男性": 1, "女性": 1}),
    ("13-19", 13, 19, {"男性": 1, "女性": 1}),
    ("20-39", 20, 39, {"男性": 2, "女性": 2}),
    ("40+",   40, 999, {"男性": 1, "女性": 1}),
]

rng = random.Random(SEED)
selected = []

for label, min_age, max_age, quotas in strata:
    for gender, count in quotas.items():
        candidates = [
            p for p in profiles
            if p[2] == gender and min_age <= p[1] <= max_age
        ]

        if len(candidates) < count:
            raise ValueError(
                f"{label} / {gender}: 候補者が足りません"
            )

        # seedに対して再現可能な無作為順位をつける
        ranked = sorted(
            candidates,
            key=lambda _: rng.random()
        )

        for person in ranked[:count]:
            name, age, gender = person
            selected.append((name, age, gender, label))

print(f"seed = {SEED}")
print()

for i, (name, age, gender, group) in enumerate(selected, 1):
    print(f"{i:02d}. {name:<8} {age:>2}歳  {gender}  {group}")

print()
print(f"合計: {len(selected)}名")
print(
    "男性:",
    sum(1 for x in selected if x[2] == "男性"),
    "女性:",
    sum(1 for x in selected if x[2] == "女性"),
)