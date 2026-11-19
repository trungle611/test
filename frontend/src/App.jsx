import React, { useState } from 'react';
import { apiCall } from './api.js';

const pages = [
  { id: 'home', title: 'Trang chủ', detail: 'Khung tổng quan và kết nối hệ thống.' },
  { id: 'food', title: 'Ăn uống', detail: 'Dành cho tải ảnh, xác nhận món, thực đơn và lịch sử.' },
  {
    id: 'workout',
    title: 'Tập luyện',
    detail: 'Dành cho giáo án, chi tiết bài tập và lịch đi tập.',
  },
  { id: 'profile', title: 'Cá nhân', detail: 'Dành cho hồ sơ, mục tiêu cân nặng và dinh dưỡng.' },
];

export default function App() {
  const [section, setSection] = useState('home');
  const [connection, setConnection] = useState('Chưa kiểm tra');
  const [busy, setBusy] = useState(false);
  const page = pages.find((item) => item.id === section);

  async function checkConnection() {
    setBusy(true);
    try {
      const result = await apiCall('/api/health');
      setConnection(result.status === 'ok' ? 'Đã kết nối backend' : 'Phản hồi chưa hợp lệ');
    } catch (error) {
      setConnection(error.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <strong>HBTNFIT</strong>
        <span>Dinh dưỡng & Tập luyện</span>
      </header>
      <div className="body-layout">
        <nav className="sidebar" aria-label="Điều hướng chính">
          {pages.map((item) => (
            <button
              key={item.id}
              className={section === item.id ? 'active' : ''}
              aria-pressed={section === item.id}
              onClick={() => setSection(item.id)}
            >
              {item.title}
            </button>
          ))}
        </nav>
        <main>
          <p className="kicker">KHUNG DỰ ÁN NHÓM 1</p>
          <h1>{page.title}</h1>
          <p>{page.detail}</p>
          <section className="panel">
            <h2>Không gian triển khai chức năng</h2>
            <p>
              Chọn một mục trong thanh điều hướng. Các chức năng sẽ được bổ sung trong quá trình
              phát triển.
            </p>
            {section === 'home' && (
              <>
                <button className="primary-button" disabled={busy} onClick={checkConnection}>
                  {busy ? 'Đang kiểm tra…' : 'Kiểm tra kết nối API'}
                </button>
                <p role="status">{connection}</p>
              </>
            )}
          </section>
        </main>
      </div>
    </div>
  );
}
