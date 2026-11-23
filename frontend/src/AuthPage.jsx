import React, { useState } from 'react';
import { ArrowRight, Eye, EyeOff, LockKeyhole, ShieldCheck, UserRound } from 'lucide-react';
import { apiCall } from './api.js';

export default function AuthPage({ onAuthenticated }) {
  const [mode, setMode] = useState('login');
  const [form, setForm] = useState({ username: '', password: '', confirm: '' });
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const isRegister = mode === 'register';
  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }));

  function switchMode(next) {
    setMode(next);
    setError('');
    setForm((current) => ({ ...current, password: '', confirm: '' }));
  }

  async function submit(event) {
    event.preventDefault();
    setError('');
    if (isRegister && form.password !== form.confirm) {
      setError('Mật khẩu xác nhận chưa khớp.');
      return;
    }
    setBusy(true);
    try {
      const payload = { username: form.username, password: form.password };
      const result = await apiCall(`/api/auth/${isRegister ? 'register' : 'login'}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      onAuthenticated(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-page">
      <header className="auth-header">
        <div className="auth-brand">
          <span className="brand-logo-frame">
            <img className="brand-logo" src="/Logo_HUET.svg" alt="Logo Đại học Công nghệ" />
          </span>
          <span>
            <b>HBTNFIT</b>
            <small>Dinh dưỡng & Tập luyện</small>
          </span>
        </div>
        <span className="auth-safe">
          <ShieldCheck size={14} /> Bảo mật phiên đăng nhập
        </span>
      </header>
      <div className="auth-layout auth-layout-simple">
        <section className="auth-card" aria-labelledby="auth-title">
          <span className="auth-card-kicker">TÀI KHOẢN HBTNFIT</span>
          <h2 id="auth-title">{isRegister ? 'Đăng ký' : 'Đăng nhập'}</h2>
          <p>
            {isRegister
              ? 'Tạo tài khoản để bắt đầu sử dụng HBTNFIT.'
              : 'Nhập thông tin tài khoản để tiếp tục.'}
          </p>
          <form onSubmit={submit}>
            <label>
              Tên đăng nhập
              <div className="auth-input">
                <UserRound size={16} />
                <input
                  required
                  minLength="3"
                  maxLength="30"
                  value={form.username}
                  onChange={(e) => update('username', e.target.value)}
                  placeholder="Nhập tên đăng nhập"
                  autoComplete="username"
                />
              </div>
            </label>
            <label>
              Mật khẩu
              <div className="auth-input">
                <LockKeyhole size={16} />
                <input
                  required
                  minLength={isRegister ? 8 : 1}
                  type={showPassword ? 'text' : 'password'}
                  value={form.password}
                  onChange={(e) => update('password', e.target.value)}
                  placeholder={isRegister ? 'Tối thiểu 8 ký tự' : 'Nhập mật khẩu'}
                  autoComplete={isRegister ? 'new-password' : 'current-password'}
                />
                <button
                  type="button"
                  aria-label={showPassword ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
                  onClick={() => setShowPassword(!showPassword)}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </label>
            {isRegister && (
              <label>
                Xác nhận mật khẩu
                <div className="auth-input">
                  <LockKeyhole size={16} />
                  <input
                    required
                    minLength="8"
                    type={showPassword ? 'text' : 'password'}
                    value={form.confirm}
                    onChange={(e) => update('confirm', e.target.value)}
                    placeholder="Nhập lại mật khẩu"
                    autoComplete="new-password"
                  />
                </div>
              </label>
            )}
            {error && (
              <div className="auth-error" role="alert">
                {error}
              </div>
            )}
            <button className="auth-submit" disabled={busy}>
              {busy ? 'Đang xử lý…' : isRegister ? 'Tạo tài khoản' : 'Đăng nhập'}{' '}
              {!busy && <ArrowRight size={16} />}
            </button>
          </form>
          <div className="auth-switch">
            {isRegister ? 'Đã có tài khoản?' : 'Chưa có tài khoản?'}{' '}
            <button disabled={busy} onClick={() => switchMode(isRegister ? 'login' : 'register')}>
              {isRegister ? 'Đăng nhập' : 'Đăng ký ngay'}
            </button>
          </div>
        </section>
      </div>
      <footer className="auth-footer">© 2026 HBTNFIT · Mỗi ngày khỏe hơn một chút.</footer>
    </main>
  );
}
