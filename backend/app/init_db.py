"""Chạy từ backend: python -m app.init_db. Không gọi Gemini hoặc xóa dữ liệu."""

from .db import initialize_database

if __name__ == "__main__":
    initialize_database()
    print("Đã khởi tạo/nâng cấp database và nạp danh mục CSV.")
