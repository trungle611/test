"""Kiểm tra nhãn và khóa tập ảnh trước khi gọi AI."""

import hashlib
import json
from pathlib import Path

from PIL import Image


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def image_path(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError(f"Ảnh không tồn tại hoặc ngoài thư mục dữ liệu: {relative}")
    return path


def freeze(manifest, root):
    if not isinstance(manifest, dict) or not isinstance(manifest.get("cases"), list):
        raise ValueError("Manifest cần có danh sách cases")
    if not manifest["cases"]:
        raise ValueError("Chưa có ảnh để đánh giá")
    ids, hashes, groups = set(), set(), {}
    locked = []
    for case in manifest["cases"]:
        if not isinstance(case, dict):
            raise ValueError("Mỗi case phải là một object")
        ident = case.get("id")
        if not isinstance(ident, str) or not ident or ident in ids:
            raise ValueError("ID ảnh phải là chuỗi không trùng")
        ids.add(ident)
        split = case.get("split")
        if split not in {"dev", "test", "smoke"}:
            raise ValueError(f"{ident}: split phải là dev, test hoặc smoke")
        if type(case.get("synthetic")) is not bool:
            raise ValueError(f"{ident}: cần khai báo synthetic true/false")
        if case["synthetic"] and split != "smoke":
            raise ValueError("Ảnh tổng hợp chỉ được dùng cho smoke")
        reviewers = case.get("reviewed_by", [])
        if not isinstance(reviewers, list) or any(
            not isinstance(r, str) or not r.strip() for r in reviewers
        ):
            raise ValueError(f"{ident}: danh sách người duyệt không hợp lệ")
        if split != "smoke" and len({r.strip().casefold() for r in reviewers}) < 2:
            raise ValueError(f"{ident}: cần hai người duyệt nhãn độc lập")
        if any(
            not isinstance(case.get(k), str) or not case[k].strip()
            for k in ("source", "group_id", "category", "image")
        ):
            raise ValueError(f"{ident}: thiếu nguồn, group_id hoặc nhóm tình huống")
        group = case["group_id"]
        if group in groups and groups[group] != split:
            raise ValueError(f"{ident}: cùng nhóm ảnh xuất hiện ở nhiều split")
        groups[group] = split
        expected = case.get("expected")
        if not isinstance(expected, list) or len(expected) > 5:
            raise ValueError(
                f"{ident}: expected là danh sách tối đa 5 món, rỗng nếu không có đồ ăn"
            )
        for labels in expected:
            if (
                not isinstance(labels, list)
                or not labels
                or any(not isinstance(s, str) or not s.strip() for s in labels)
            ):
                raise ValueError(
                    f"{ident}: mỗi món cần tên chuẩn và tên tương đương được duyệt trước"
                )
        path = image_path(root, case["image"])
        raw = path.read_bytes()
        if len(raw) > 5 * 1024 * 1024:
            raise ValueError(f"{ident}: ảnh vượt 5 MB")
        with Image.open(path) as picture:
            if picture.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError(f"{ident}: định dạng ảnh không hỗ trợ")
            picture.verify()
        sha = digest(raw)
        if sha in hashes:
            raise ValueError(f"{ident}: ảnh trùng nội dung, kể cả khác tên file")
        hashes.add(sha)
        locked.append({**case, "sha256": sha})
    return {"schema_version": 1, "cases": locked}
