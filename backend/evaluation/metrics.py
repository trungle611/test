"""Ghép một-một các món; giữ dấu tiếng Việt và không khớp mờ theo tên."""

import re
import unicodedata


def normalized(text):
    return " ".join(re.sub(r"[^\w\s]", " ", unicodedata.normalize("NFC", text).casefold()).split())


def matched(expected, predicted, top):
    # Augmenting paths bảo đảm một dự đoán không được tính đúng cho hai món.
    assigned = {}

    def visit(index, seen):
        aliases = {normalized(s) for s in expected[index]}
        for j, labels in enumerate(predicted):
            if j in seen or not aliases.intersection(normalized(s) for s in labels[:top]):
                continue
            seen.add(j)
            if j not in assigned or visit(assigned[j], seen):
                assigned[j] = index
                return True
        return False

    return sum(visit(i, set()) for i in range(len(expected)))


def score(case, result, status):
    expected = case["expected"]
    predicted = [d["candidate_labels"] for d in result["dishes"]] if status == "ok" else []
    output = {"expected_count": len(expected), "predicted_count": len(predicted)}
    for top in (1, 3):
        tp = matched(expected, predicted, top)
        output[f"top{top}"] = {
            "tp": tp,
            "fp": len(predicted) - tp,
            "fn": len(expected) - tp,
            "exact": status == "ok" and tp == len(expected) == len(predicted),
        }
    return output


def summarize(rows):
    count = len(rows)
    summary = {"attempted_images": count, "errors": sum(r["status"] != "ok" for r in rows)}
    for top in (1, 3):
        key = f"top{top}"
        counts = {k: sum(r["score"][key][k] for r in rows) for k in ("tp", "fp", "fn")}
        tp, fp, fn = (counts[k] for k in ("tp", "fp", "fn"))
        summary[key] = {
            **counts,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
            "exact_images": sum(r["score"][key]["exact"] for r in rows),
            "exact_rate": sum(r["score"][key]["exact"] for r in rows) / count if count else None,
        }
    summary["nonfood_images"] = sum(r["score"]["expected_count"] == 0 for r in rows)
    summary["nonfood_correct"] = sum(
        r["score"]["expected_count"] == 0 and r["score"]["top1"]["exact"] for r in rows
    )
    return summary
