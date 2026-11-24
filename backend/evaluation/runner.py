"""Chạy nối tiếp qua luồng nhận diện thật; không ghi vào database người dùng."""

import csv
import importlib.metadata
import json
import mimetypes
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from .dataset import digest, freeze, image_path
from .metrics import score, summarize

REPO = Path(__file__).resolve().parents[2]


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def catalog_data():
    path = REPO / "data/serving_items_team_unverified.csv"
    with path.open(encoding="utf-8-sig", newline="") as stream:
        catalog = [
            {"food_id": r["id"], "name": r["name"], "portion": r["basis_label"]}
            for r in csv.DictReader(stream)
            if r["item_type"] in {"dish", "beverage"} and r["source_type"] == "team_csv"
        ]
    return catalog, digest(path.read_bytes())


def run(lock_path, root, output, split, env_file=None):
    from dotenv import load_dotenv

    if env_file:
        load_dotenv(env_file, override=True)
    # Import sau khi nạp cấu hình riêng; không sao chép khóa vào kết quả.
    from ..app import ai

    if not os.getenv("GEMINI_API_KEY", "").strip():
        raise ValueError("Thiếu GEMINI_API_KEY; đặt trong backend/.env hoặc dùng --env-file")
    lock_bytes = Path(lock_path).read_bytes()
    locked = json.loads(lock_bytes)
    if locked.get("schema_version") != 1:
        raise ValueError("Phiên bản lock không được hỗ trợ")
    freeze(locked, root)
    cases = [c for c in locked["cases"] if c["split"] == split]
    if not cases:
        raise ValueError(f"Không có ảnh thuộc split {split}")
    # Kiểm tra tất cả ảnh trước khi tốn lượt gọi dịch vụ.
    for case in locked["cases"]:
        if digest(image_path(root, case["image"]).read_bytes()) != case["sha256"]:
            raise ValueError(f"Ảnh đã thay đổi sau khi khóa: {case['id']}")
    catalog, catalog_hash = catalog_data()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "dataset.lock.json", locked)
    commit = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "-C", str(REPO), "status", "--porcelain"], capture_output=True, text=True
    ).stdout.strip()
    metadata = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "split": split,
        "dataset_sha256": digest(lock_bytes),
        "catalog_sha256": catalog_hash,
        "ai_code_sha256": digest(Path(ai.__file__).read_bytes()),
        "evaluation_code_sha256": {
            p.name: digest(p.read_bytes()) for p in Path(__file__).parent.glob("*.py")
        },
        "git_commit": commit,
        "sdk_version": importlib.metadata.version("google-genai"),
        "working_tree_dirty": bool(dirty),
        "prompt_version": ai.SCAN_PROMPT_VERSION,
        "requested_model": os.getenv("GEMINI_MODEL", ai.DEFAULT_MODEL),
        "pipeline": "app.ai.scan_image including validation and Vietnamese repair",
        "note": "smoke không phải đánh giá cuối; không đo độ chính xác dinh dưỡng",
    }
    write_json(output / "run.json", metadata)
    rows = []
    original_client = ai.client
    with (output / "results.jsonl").open("x", encoding="utf-8") as journal:
        for number, case in enumerate(cases, 1):
            calls = []

            def traced_client(key=None):
                actual = original_client(key)
                if actual is None:
                    return None

                def generate(**kwargs):
                    item = {"requested_model": kwargs.get("model")}
                    calls.append(item)
                    try:
                        response = actual.models.generate_content(**kwargs)
                    except Exception as exc:
                        item["error_type"] = type(exc).__name__
                        item["http_status"] = getattr(exc, "code", None)
                        # Không lưu str(exc), URL hoặc request có thể chứa credential.
                        raise
                    item.update(
                        text=response.text, model_version=getattr(response, "model_version", None)
                    )
                    return response

                return SimpleNamespace(models=SimpleNamespace(generate_content=generate))

            started = time.monotonic()
            result, status, error_type = None, "ok", None
            path = image_path(root, case["image"])
            try:
                with patch.object(ai, "client", traced_client):
                    result = ai.scan_image(
                        path.read_bytes(), mimetypes.guess_type(path)[0], catalog, []
                    )
            except Exception as exc:
                status = getattr(
                    exc,
                    "reason",
                    "invalid_response" if isinstance(exc, ai.AIResponseError) else "error",
                )
                error_type = type(exc).__name__
            row = {
                "case_id": case["id"],
                "category": case["category"],
                "status": status,
                "error_type": error_type,
                "latency_ms": round((time.monotonic() - started) * 1000),
                "provider_calls": calls,
                "result": result,
                "score": score(case, result, status),
            }
            write_json(output / f"response-{number:04d}.json", row)
            journal.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            journal.flush()
            rows.append(row)
            print(f"{number}/{len(cases)}: {case['id']} - {status}", flush=True)
            if status in {"quota", "authentication"}:
                break
    summary = {
        "planned_images": len(cases),
        "complete": len(rows) == len(cases),
        "split": split,
        **summarize(rows),
        "by_category": {
            c: summarize([r for r in rows if r["category"] == c])
            for c in sorted({r["category"] for r in rows})
        },
    }
    summary["top1_exact_rate_planned"] = summary["top1"]["exact_images"] / len(cases)
    summary["top3_exact_rate_planned"] = summary["top3"]["exact_images"] / len(cases)
    write_json(output / "summary.json", summary)
    artifacts = {p.name: digest(p.read_bytes()) for p in output.iterdir() if p.is_file()}
    write_json(output / "checksums.json", artifacts)
    return summary
