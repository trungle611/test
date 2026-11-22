const API_BASE = import.meta.env.VITE_API_URL || '';
const TOKEN_KEY = 'hbtnfit_auth_token';

const validationTranslations = {
  'Field required': 'thiếu dữ liệu bắt buộc',
  'Input should be greater than 0': 'giá trị phải lớn hơn 0',
  'String should have at least 2 characters': 'tên món phải có ít nhất 2 ký tự',
};

function errorMessage(body, status) {
  if (typeof body.detail === 'string') return body.detail;
  if (Array.isArray(body.detail)) {
    const details = body.detail.map((item) => {
      const field = Array.isArray(item.loc)
        ? item.loc.filter((part) => part !== 'body').join(' → ')
        : '';
      const message = validationTranslations[item.msg] || item.msg || 'dữ liệu không hợp lệ';
      return field ? `${field}: ${message}` : message;
    });
    return `Dữ liệu gửi lên không hợp lệ (${status}): ${details.join('; ')}`;
  }
  return status === 422
    ? 'Dữ liệu gửi lên không hợp lệ (422) — hãy kiểm tra ảnh, món ăn và khẩu phần.'
    : `Lỗi ${status}`;
}

export async function apiCall(path, options = {}) {
  const { responseType, ...fetchOptions } = options;
  const headers = new Headers(options.headers || {});
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) headers.set('Authorization', `Bearer ${token}`);

  const response = await fetch(`${API_BASE}${path}`, { ...fetchOptions, headers });
  if (responseType === 'blob' && response.ok) return response.blob();

  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(errorMessage(body, response.status));
    error.status = response.status;
    if (
      response.status === 401 &&
      token &&
      getAuthToken() === token &&
      !path.startsWith('/api/auth/')
    ) {
      clearAuthToken();
      window.dispatchEvent(new Event('hbtnfit-session-expired'));
    }
    throw error;
  }
  return body;
}

export function getAuthToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function saveAuthToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearAuthToken() {
  localStorage.removeItem(TOKEN_KEY);
}
