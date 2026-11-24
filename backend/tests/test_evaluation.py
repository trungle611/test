"""Kiểm tra chống rò rỉ tập ảnh, ghép một-một và giữ lỗi trong mẫu số."""

import copy
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from backend.evaluation.dataset import freeze
from backend.evaluation.metrics import matched, normalized, score, summarize
from backend.evaluation.runner import run, write_json


@pytest.fixture
def manifest(tmp_path):
    Image.new("RGB", (12, 12), "red").save(tmp_path / "one.png")
    Image.new("RGB", (12, 12), "blue").save(tmp_path / "two.png")
    case = {
        "id": "one",
        "image": "one.png",
        "split": "dev",
        "synthetic": False,
        "group_id": "group-one",
        "category": "single",
        "source": "group photo",
        "reviewed_by": ["Hoàng", "Bình"],
        "expected": [["Phở bò"]],
    }
    return {"cases": [case]}, tmp_path


def test_lock_images_and_reviewer_requirement(manifest):
    data, root = manifest
    locked = freeze(data, root)
    assert len(locked["cases"][0]["sha256"]) == 64
    data["cases"][0]["reviewed_by"] = ["Bình"]
    with pytest.raises(ValueError, match="hai người"):
        freeze(data, root)


@pytest.mark.parametrize("same_file", [True, False])
def test_reject_duplicate_images_and_group_leakage(manifest, same_file):
    data, root = manifest
    second = copy.deepcopy(data["cases"][0])
    second.update(id="two", split="test", group_id="other" if same_file else "group-one")
    if not same_file:
        second["image"] = "two.png"
    data["cases"].append(second)
    with pytest.raises(ValueError):
        freeze(data, root)


def test_synthetic_cannot_be_final_test(manifest):
    data, root = manifest
    data["cases"][0].update(synthetic=True, split="test")
    with pytest.raises(ValueError, match="smoke"):
        freeze(data, root)


def test_root_escape_rejected(manifest):
    data, root = manifest
    data["cases"][0]["image"] = "../private.png"
    with pytest.raises(ValueError, match="ngoài"):
        freeze(data, root)


def test_one_prediction_cannot_cover_two_expected_dishes():
    assert matched([["Phở bò"], ["Phở bò"]], [["Phở bò"]], 3) == 1
    assert matched([["A", "B"], ["A"]], [["A"], ["B"]], 1) == 2


def test_top3_and_accent_policy():
    assert normalized(" PHỞ BÒ! ") == "phở bò"
    assert normalized("Pho bo") != normalized("Phở bò")
    assert matched([["Phở bò"]], [["Bún bò", "Phở bò"]], 1) == 0
    assert matched([["Phở bò"]], [["Bún bò", "Phở bò"]], 3) == 1


def test_error_is_not_correct_rejection_for_nonfood():
    case = {"expected": []}
    error = score(case, None, "quota")
    good = score(case, {"dishes": []}, "ok")
    summary = summarize([{"status": "quota", "score": error}, {"status": "ok", "score": good}])
    assert summary["errors"] == 1
    assert summary["top1"]["exact_rate"] == 0.5
    assert summary["nonfood_correct"] == 1
    assert summary["top1"]["precision"] is None


def test_missing_and_extra_dishes_are_counted():
    result = {"dishes": [{"candidate_labels": ["Phở bò"]}, {"candidate_labels": ["Cá kho"]}]}
    values = score({"expected": [["Phở bò"], ["Cơm tấm"]]}, result, "ok")
    assert values["top1"] == {"tp": 1, "fp": 1, "fn": 1, "exact": False}


def test_service_error_keeps_expected_dishes_as_false_negatives():
    values = score({"expected": [["Phở bò"], ["Cơm tấm"]]}, None, "timeout")
    assert values["top1"]["fn"] == 2


def test_runner_records_provider_text_and_refuses_overwrite(manifest, monkeypatch):
    from backend.app import ai

    data, root = manifest
    lock = root / "locked.json"
    write_json(lock, freeze(data, root))
    raw = json.dumps(
        {
            "dishes": [
                {
                    "candidate_labels": ["Phở bò"],
                    "confidence": 0.9,
                    "visible_ingredients": ["thịt bò"],
                    "uncertainty_reason": "",
                    "estimated_nutrition_1g": {"kcal": 1, "protein": 0.1, "carb": 0.1, "fat": 0.01},
                }
            ],
            "warning": "",
        },
        ensure_ascii=False,
    )
    fake = SimpleNamespace(
        models=SimpleNamespace(
            generate_content=lambda **kwargs: SimpleNamespace(text=raw, model_version="test-model")
        )
    )
    monkeypatch.setattr(ai, "client", lambda key=None: fake)
    output = root / "run"
    result = run(lock, root, output, "dev")
    assert result["complete"] is True
    assert result["top1"]["exact_images"] == 1
    response = json.loads((output / "response-0001.json").read_text(encoding="utf-8"))
    assert response["provider_calls"][0]["text"] == raw
    assert response["provider_calls"][0]["model_version"] == "test-model"
    assert (output / "checksums.json").is_file()
    with pytest.raises(FileExistsError):
        run(lock, root, output, "dev")


def test_runner_refuses_changed_image_before_creating_output(manifest):
    data, root = manifest
    lock = root / "locked.json"
    write_json(lock, freeze(data, root))
    Image.new("RGB", (12, 12), "green").save(root / "one.png")
    with pytest.raises(ValueError, match="đã thay đổi"):
        run(lock, root, root / "bad-run", "dev")
    assert not (root / "bad-run").exists()
