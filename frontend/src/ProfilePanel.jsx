import React, { useState } from 'react';
import { Sparkles, UserRound } from 'lucide-react';

const defaults = {
  age: '',
  height_cm: '',
  weight_kg: '',
  target_weight_kg: '',
  target_date: '',
  sex: 'male',
  activity_level: 'moderate',
  protein_mode: 'balanced',
  goal: 'maintain',
};
const numberFields = [
  ['age', 'Tuổi', 18, 120, 1],
  ['height_cm', 'Chiều cao (cm)', 100, 250, 0.1],
  ['weight_kg', 'Cân nặng hiện tại (kg)', 25, 400, 0.1],
  ['target_weight_kg', 'Cân nặng mong muốn (kg)', 25, 400, 0.1],
];
const selections = [
  [
    'goal',
    'Mục tiêu',
    [
      ['maintain', 'Duy trì'],
      ['gain', 'Tăng cân'],
      ['lose', 'Giảm cân'],
    ],
  ],
  [
    'sex',
    'Thông số sinh học để ước tính năng lượng',
    [
      ['male', 'Nam'],
      ['female', 'Nữ'],
    ],
  ],
  [
    'activity_level',
    'Mức vận động hiện tại',
    [
      ['sedentary', 'Ít vận động'],
      ['light', 'Nhẹ · 1–3 buổi/tuần'],
      ['moderate', 'Vừa · 3–5 buổi/tuần'],
      ['high', 'Cao · 6–7 buổi/tuần'],
    ],
  ],
  [
    'protein_mode',
    'Mức protein muốn theo dõi',
    [
      ['balanced', 'Cân bằng · khoảng 1,2 g/kg'],
      ['strength', 'Tập kháng lực · khoảng 1,6 g/kg'],
    ],
  ],
];
const fmt = (value) => Number(value).toLocaleString('vi-VN');

export default function ProfilePanel({ profile, call, refresh, navigate }) {
  const [form, setForm] = useState(() => ({
    ...defaults,
    ...Object.fromEntries(Object.keys(defaults).map((key) => [key, profile[key] ?? defaults[key]])),
    avoid: (profile.avoid_tags || []).join(', '),
  }));
  const [targets, setTargets] = useState(profile.daily_targets);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const analysis = !dirty && profile.analysis;
  const today = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Ho_Chi_Minh',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date());
  const tomorrow = new Date(`${today}T00:00:00+07:00`);
  tomorrow.setUTCDate(tomorrow.getUTCDate() + 1);
  const minDate = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Ho_Chi_Minh',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(tomorrow);

  function update(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
    setDirty(true);
    setTargets(null);
    setError('');
    setMessage('');
  }
  function payload() {
    // Chỉ gửi các trường nhập; không gửi analysis/daily_targets từ response về API.
    const value = Object.fromEntries(Object.keys(defaults).map((key) => [key, form[key]]));
    for (const [key] of numberFields) value[key] = Number(value[key]);
    const difference = value.target_weight_kg - value.weight_kg;
    const expected = difference > 0.1 ? 'gain' : difference < -0.1 ? 'lose' : 'maintain';
    if (value.goal !== expected)
      throw new Error('Mục tiêu tăng/giảm/duy trì phải khớp với cân nặng mong muốn.');
    value.avoid_tags = [
      ...new Set(
        form.avoid
          .split(/[,;\n]/)
          .map((s) => s.trim())
          .filter(Boolean),
      ),
    ];
    value.target_kcal = profile.target_kcal || 1800;
    return value;
  }
  async function submit(event) {
    event.preventDefault();
    const action = event.nativeEvent.submitter?.value || 'save';
    setBusy(action);
    setError('');
    setMessage('');
    try {
      const body = JSON.stringify(payload());
      const options = { headers: { 'Content-Type': 'application/json' }, body };
      if (action === 'preview') {
        const result = await call('/api/profile/preview', { ...options, method: 'POST' });
        setTargets(result.daily_targets);
        setMessage('Đây là kết quả tính thử. Nhấn Lưu mục tiêu để áp dụng vào Ăn uống.');
      } else {
        const result = await call('/api/profile', { ...options, method: 'PUT' });
        setTargets(result.daily_targets);
        setDirty(false);
        await refresh();
        setMessage('Đã lưu mục tiêu và cập nhật bốn chỉ số trong Ăn uống.');
        if (action === 'food') navigate('food');
        if (action === 'analyze') {
          await call('/api/profile/analyze', { method: 'POST' });
          await refresh();
          setMessage('Đã tạo gợi ý. Chọn phương án phù hợp bên dưới.');
        }
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  }
  async function choose(key, id, section) {
    setBusy(id);
    setError('');
    try {
      await call('/api/profile/choice', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [key]: id }),
      });
      await refresh();
      navigate(section);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  }
  return (
    <div className="profile-page">
      <section className="panel profile-card" aria-labelledby="profile-title">
        <span className="eyebrow">
          <UserRound size={16} /> THÔNG TIN CÁ NHÂN
        </span>
        <h2 id="profile-title">Hồ sơ và mục tiêu của bạn</h2>
        <p>
          Nhập cân nặng và thời hạn để theo dõi dinh dưỡng mỗi ngày. Dữ liệu được lưu riêng theo tài
          khoản.
        </p>
        <form onSubmit={submit}>
          <fieldset disabled={!!busy} className="profile-fieldset">
            <div className="profile-form-grid">
              {numberFields.map(([key, label, min, max, step]) => (
                <label key={key}>
                  {label}
                  <input
                    name={key}
                    type="number"
                    required
                    min={min}
                    max={max}
                    step={step}
                    value={form[key]}
                    onChange={(e) => update(key, e.target.value)}
                  />
                </label>
              ))}
              <label>
                Muốn đạt mục tiêu trước ngày
                <input
                  name="target_date"
                  type="date"
                  required
                  min={minDate}
                  value={form.target_date}
                  onChange={(e) => update('target_date', e.target.value)}
                />
              </label>
              {selections.map(([key, label, options]) => (
                <label key={key}>
                  {label}
                  <select
                    name={key}
                    value={form[key]}
                    onChange={(e) => update(key, e.target.value)}
                  >
                    {options.map(([value, text]) => (
                      <option value={value} key={value}>
                        {text}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
              <label>
                Thành phần cần tránh
                <input
                  name="avoid"
                  value={form.avoid}
                  maxLength={500}
                  placeholder="Ví dụ: thịt bò, tỏi, sữa"
                  onChange={(e) => update('avoid', e.target.value)}
                />
                <small>Ngăn cách các thành phần bằng dấu phẩy.</small>
              </label>
            </div>
            {targets && (
              <div
                className="goal-preview"
                aria-label="Mục tiêu dinh dưỡng mỗi ngày"
                aria-live="polite"
              >
                {[
                  ['kcal', 'kcal', 'Mỗi ngày'],
                  ['protein_g', 'g', 'Protein'],
                  ['carb_g', 'g', 'Carb'],
                  ['fat_g', 'g', 'Chất béo'],
                ].map(([key, unit, label]) => (
                  <div key={key}>
                    <strong>
                      {fmt(targets[key])} {unit}
                    </strong>
                    <span>{label}</span>
                  </div>
                ))}
                <div>
                  <strong>{fmt(targets.days_remaining)} ngày</strong>
                  <span>Đến hạn đã chọn</span>
                </div>
              </div>
            )}
            {targets && (
              <p className="profile-help">
                Protein tính theo cân nặng hiện tại × {targets.protein_factor} g/kg, không tính theo
                số kg muốn tăng. Các chỉ số là ước tính để theo dõi, không bảo đảm đạt cân nặng vào
                thời hạn.
              </p>
            )}
            {targets?.timeline_warning && (
              <p className="profile-warning">
                Thời hạn có thể quá gấp. Mức năng lượng gợi ý đã được giới hạn; hãy cân nhắc thời
                hạn dài hơn.
              </p>
            )}
            {targets?.macro_distribution_warning && (
              <p className="profile-warning">
                Phân bố dinh dưỡng có thể chưa cân đối với hồ sơ này. Hãy xem lại mục tiêu và mức
                protein đã chọn.
              </p>
            )}
            <div className="profile-actions">
              <button className="secondary-button" name="action" value="preview">
                Tính thử
              </button>
              <button className="secondary-button" name="action" value="save">
                Lưu mục tiêu
              </button>
              <button className="primary-button" name="action" value="food">
                Lưu và xem ăn uống
              </button>
              <button className="secondary-button" name="action" value="analyze">
                <Sparkles size={16} /> Lưu và nhận gợi ý AI
              </button>
            </div>
          </fieldset>
        </form>
        {busy && (
          <p role="status">
            {busy === 'analyze' ? 'Đã lưu mục tiêu. Đang tạo gợi ý AI…' : 'Đang xử lý…'}
          </p>
        )}
        {error && (
          <p className="profile-error" role="alert">
            {error}
          </p>
        )}
        {message && (
          <p className="profile-help" role="status">
            {message}
          </p>
        )}
      </section>
      {analysis && (
        <section className="panel profile-card" aria-labelledby="guidance-title">
          <span className="eyebrow">
            <Sparkles size={16} /> GỢI Ý TỪ GEMINI
          </span>
          <h2 id="guidance-title">Phương án cho mục tiêu của bạn</h2>
          <p>{analysis.summary}</p>
          <h3>Ăn uống</h3>
          <div className="guidance-options">
            {analysis.food_options.map((option) => (
              <article className="guidance-option" key={option.id}>
                <h3>{option.title}</h3>
                <p>{option.detail}</p>
                <ul>
                  {option.examples.map((item, i) => (
                    <li key={i}>
                      {{ breakfast: 'Sáng', lunch: 'Trưa', dinner: 'Tối' }[item.meal_type]}:{' '}
                      {item.name} · {item.default_amount} {item.unit}
                    </li>
                  ))}
                </ul>
                {option.estimated_totals && (
                  <p>
                    {fmt(option.estimated_totals.kcal)} kcal ·{' '}
                    {fmt(option.estimated_totals.protein)} g protein
                  </p>
                )}
                <button
                  className="secondary-button"
                  disabled={!!busy}
                  onClick={() => choose('food_choice', option.id, 'food')}
                >
                  {profile.food_choice === option.id ? 'Xem thực đơn đã chọn' : 'Chọn cách ăn này'}
                </button>
              </article>
            ))}
          </div>
          <h3>Tập luyện</h3>
          <div className="guidance-options">
            {analysis.workout_options.map((option) => (
              <article className="guidance-option" key={option.id}>
                <h3>{option.name}</h3>
                <p>{option.detail}</p>
                <button
                  className="secondary-button"
                  disabled={!!busy}
                  onClick={() => choose('workout_choice', option.id, 'workout')}
                >
                  Chọn giáo án này
                </button>
              </article>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
