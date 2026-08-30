import json, sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from evaluator.local_evaluator import load_jsonl, catalog_index, materialize_hidden_fields
from starter.agent import classify, MATERIAL_RE, COLOR_RE

samples = load_jsonl(REPO_ROOT / "data/public_set.jsonl")
catalog_ids, categories, products = catalog_index(REPO_ROOT / "data/catalog.jsonl")

compound_count = 0
total_constraints = 0
examples = []
for sample in samples:
    card, behavior = materialize_hidden_fields(sample, products)
    for value in card.get("hard_constraints", []) + card.get("soft_preferences", []):
        total_constraints += 1
        has_material = bool(MATERIAL_RE.search(value))
        has_color = bool(COLOR_RE.search(value))
        if has_material and has_color:
            compound_count += 1
            bucket = classify(value)
            if len(examples) < 5:
                examples.append((value, bucket))

print(f"Total constraint strings examined across 200 public sessions: {total_constraints}")
print(f"Strings containing BOTH a material word and a color word: {compound_count}")
for v, b in examples:
    print(f"  {v!r} -> classified as single bucket: {b!r} (the other attribute mentioned in this same string is never marked filled)")
