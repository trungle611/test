import React, { useState } from 'react';
import { CalendarDays, Pencil, Trash2, Check, X, UtensilsCrossed } from 'lucide-react';
import {
  formatNumber as fmt,
  isDiscreteUnit,
  MEAL_LABELS as labels,
  MEAL_SLOTS as slots,
  NUTRIENT_KEYS as nutrientKeys,
} from './constants.js';

export default function TodayMeals({
  dashboard,
  profile,
  setProfile,
  selectedMeal = 'lunch',
  onOpenProfile,
  call,
  refresh,
  onError,
  compact = false,
}) {
  const [editing, setEditing] = useState(null);
  const [grams, setGrams] = useState('');
  const [mealType, setMealType] = useState('lunch');
  const [busy, setBusy] = useState(false);
  const entries = dashboard?.entries || [];
  const totals = dashboard?.totals || {};
  const editingEntry = entries.find((entry) => entry.id === editing);
  const editedGrams = Number(grams);
  const previewNutrition =
    editingEntry && Number.isFinite(editedGrams) && editedGrams > 0
      ? Object.fromEntries(
          nutrientKeys.map((key) => [
            key,
            (Number(editingEntry.nutrition?.[key] || 0) * editedGrams) / Number(editingEntry.grams),
          ]),
        )
      : null;
  const displayEntries = previewNutrition
    ? entries.map((entry) =>
        entry.id === editing
          ? { ...entry, grams: editedGrams, nutrition: previewNutrition, meal_type: mealType }
          : entry,
      )
    : entries;
  const displayTotals = previewNutrition
    ? Object.fromEntries(
        nutrientKeys.map((key) => [
          key,
          Number(totals[key] || 0) -
            Number(editingEntry.nutrition?.[key] || 0) +
            previewNutrition[key],
        ]),
      )
    : totals;
  const target = profile?.daily_targets;
  const checklist = profile?.food_checklist || [];
  const visibleChecklist = checklist.filter((item) => item.meal_type === selectedMeal);
  const completedChecklist = checklist.filter((item) => item.completed).length;
  const mealOverview = slots.map((slot) => {
    const items = displayEntries.filter((entry) => entry.meal_type === slot);
    return {
      slot,
      count: items.length,
      kcal: items.reduce((sum, entry) => sum + Number(entry.nutrition?.kcal || 0), 0),
    };
  });
  const goalRows = target
    ? [
        ['Kcal', 'kcal', 'kcal', ''],
        ['Protein', 'protein', 'protein_g', ' g'],
        ['Carb', 'carb', 'carb_g', ' g'],
        ['Chất béo', 'fat', 'fat_g', ' g'],
      ].filter(([, , key]) => target[key] != null)
    : [];

  function beginEdit(entry) {
    setEditing(entry.id);
    setGrams(String(entry.amount ?? entry.grams));
    setMealType(entry.meal_type);
  }
  async function saveEdit(id) {
    const value = Number(grams);
    if (!Number.isFinite(value) || value <= 0 || value > 2000) {
      onError('Khẩu phần phải lớn hơn 0 và không quá 2000 đơn vị.');
      return;
    }
    if (isDiscreteUnit(editingEntry?.unit) && !Number.isInteger(value)) {
      onError(`Định lượng theo đơn vị ${editingEntry.unit} phải là số nguyên.`);
      return;
    }
    setBusy(true);
    try {
      await call(`/api/food-logs/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ grams: value, meal_type: mealType }),
      });
      setEditing(null);
      await refresh();
    } catch (error) {
      onError(error.message);
    } finally {
      setBusy(false);
    }
  }
  async function remove(id) {
    setBusy(true);
    try {
      await call(`/api/food-logs/${id}`, { method: 'DELETE' });
      await refresh();
    } catch (error) {
      onError(error.message);
    } finally {
      setBusy(false);
    }
  }
  async function toggleChecklist(item) {
    const amount = Number(item.amount);
    if (!Number.isFinite(amount) || amount <= 0 || amount > 2000) {
      onError('Định lượng phải lớn hơn 0 và không quá 2000 đơn vị.');
      return;
    }
    if (isDiscreteUnit(item.unit) && !Number.isInteger(amount)) {
      onError(`Định lượng theo đơn vị ${item.unit} phải là số nguyên.`);
      return;
    }
    setBusy(true);
    try {
      const result = await call(`/api/profile/food-checklist/${encodeURIComponent(item.id)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ completed: !item.completed, amount }),
      });
      setProfile?.(result);
      await refresh();
    } catch (error) {
      onError(error.message);
    } finally {
      setBusy(false);
    }
  }
  function updateChecklistAmount(itemId, value) {
    setProfile?.((current) => ({
      ...current,
      food_checklist: (current.food_checklist || []).map((item) =>
        item.id === itemId ? { ...item, amount: value } : item,
      ),
    }));
  }

  return (
    <section className="panel today-panel" aria-labelledby="today-meals-title">
      <div className="panel-heading">
        <div>
          <div className="section-kicker">
            <CalendarDays size={15} /> DINH DƯỠNG HÔM NAY
          </div>
          <h2 id="today-meals-title">Thực đơn hôm nay</h2>
        </div>
        <span className="count-pill">{entries.length} món</span>
      </div>
      {checklist.length > 0 && (
        <div className="food-checklist">
          <div className="food-checklist-heading">
            <div>
              <strong>Gợi ý cho {labels[selectedMeal]?.toLocaleLowerCase('vi')}</strong>
              <span>
                {completedChecklist}/{checklist.length} món của ba bữa đã dùng
              </span>
            </div>
            {onOpenProfile && (
              <button className="link-button" onClick={onOpenProfile}>
                Đổi phương án
              </button>
            )}
          </div>
          <div className="food-checklist-items">
            {visibleChecklist.length ? (
              visibleChecklist.map((item) => (
                <div
                  className={`food-checklist-item ${item.completed ? 'completed' : ''}`}
                  key={item.id}
                >
                  <input
                    aria-label={`Đã ăn ${item.text}`}
                    type="checkbox"
                    checked={!!item.completed}
                    disabled={busy}
                    onChange={() => toggleChecklist(item)}
                  />
                  <div>
                    <strong>{item.text}</strong>
                    <small>Khẩu phần CSV: {item.basis_label}</small>
                  </div>
                  <label>
                    Số lượng
                    <input
                      type="number"
                      min={isDiscreteUnit(item.unit) ? '1' : '0.1'}
                      max="2000"
                      step={isDiscreteUnit(item.unit) ? '1' : '0.1'}
                      value={item.amount}
                      disabled={busy || item.completed}
                      onChange={(event) => updateChecklistAmount(item.id, event.target.value)}
                    />
                    <span>{item.unit}</span>
                  </label>
                </div>
              ))
            ) : (
              <p className="checklist-empty">
                Phương án hiện chỉ gồm ba bữa chính. Hãy chọn Bữa sáng, Bữa trưa hoặc Bữa tối.
              </p>
            )}
          </div>
          <small>
            Nhập định lượng rồi tick để thêm món vào thực đơn và cập nhật kcal, protein, carb, chất
            béo. Bỏ tick sẽ xóa đúng bản ghi vừa thêm.
          </small>
        </div>
      )}
      {target ? (
        <div className="daily-goal">
          <div className="daily-goal-top">
            <strong>Mục tiêu theo cân nặng của bạn</strong>
            {onOpenProfile && (
              <button className="link-button" onClick={onOpenProfile}>
                Sửa mục tiêu
              </button>
            )}
          </div>
          {goalRows.map(([label, totalKey, targetKey, unit]) => (
            <div className="goal-progress" key={targetKey}>
              <div>
                <span>{label}</span>
                <b>
                  {fmt(displayTotals[totalKey])} / {fmt(target[targetKey])}
                  {unit}
                </b>
              </div>
              <progress
                value={
                  target[targetKey] > 0
                    ? Math.min(
                        100,
                        Math.round(((displayTotals[totalKey] || 0) / target[targetKey]) * 100),
                      )
                    : 0
                }
                max="100"
                aria-label={`Tiến độ ${label} hôm nay`}
              />
            </div>
          ))}
          <small>
            Protein theo mức {target.protein_factor} g/kg bạn chọn; chất béo khoảng 20–30% năng
            lượng, carb là phần còn lại.{' '}
            {profile.target_date &&
              `Thời hạn mong muốn: ${new Date(`${profile.target_date}T12:00:00`).toLocaleDateString('vi-VN')}. `}
            Số liệu món chỉ được cộng sau khi xác nhận.
          </small>
        </div>
      ) : (
        <div className="daily-goal daily-goal-empty">
          <span>Chưa có mục tiêu kcal, protein, carb và chất béo mỗi ngày.</span>
          {onOpenProfile && (
            <button className="link-button" onClick={onOpenProfile}>
              Thiết lập trong Cá nhân →
            </button>
          )}
        </div>
      )}
      {target?.macro_distribution_warning && (
        <p className="goal-warning">
          Tỷ lệ carb của mục tiêu này thấp hơn khoảng tham khảo; hãy kiểm tra lại trong Cá nhân.
        </p>
      )}
      <div className="nutrition-summary">
        <div className="calorie-total">
          <strong>{fmt(displayTotals.kcal)}</strong>
          <span>kcal đã thêm</span>
        </div>
        <div className="macro-grid">
          <div>
            <b>{fmt(displayTotals.protein)}g</b>
            <span>Protein</span>
          </div>
          <div>
            <b>{fmt(displayTotals.carb)}g</b>
            <span>Carb</span>
          </div>
          <div>
            <b>{fmt(displayTotals.fat)}g</b>
            <span>Chất béo</span>
          </div>
        </div>
      </div>
      <div className="meal-overview-grid" aria-label="Tổng quan dinh dưỡng theo bữa">
        {mealOverview.map((meal) => (
          <div className={`meal-overview-card ${meal.count ? 'has-meals' : ''}`} key={meal.slot}>
            <span>{labels[meal.slot]}</span>
            <strong>{fmt(meal.kcal)} kcal</strong>
            <small>{meal.count ? `${meal.count} món` : 'Chưa có món'}</small>
          </div>
        ))}
      </div>
      {entries.length === 0 && (
        <div className="empty-state">
          <UtensilsCrossed size={24} />
          <strong>Chưa có món nào</strong>
          <p>Món chỉ được cộng vào đây sau khi bạn xác nhận thêm.</p>
        </div>
      )}
      {slots.map((slot) => {
        const meals = entries.filter((entry) => entry.meal_type === slot);
        if (!meals.length) return null;
        return (
          <div className="meal-group" key={slot}>
            <h3>{labels[slot]}</h3>
            {meals.map((entry) => (
              <div className="meal-entry" key={entry.id}>
                {editing === entry.id ? (
                  <div className="meal-edit">
                    <strong>{entry.name}</strong>
                    <div className="edit-row">
                      <label>
                        Khẩu phần ({entry.unit || 'g'})
                        <input
                          type="number"
                          min={isDiscreteUnit(entry.unit) ? '1' : '0.1'}
                          max="2000"
                          step={isDiscreteUnit(entry.unit) ? '1' : '0.1'}
                          value={grams}
                          onChange={(e) => setGrams(e.target.value)}
                        />
                      </label>
                      <label>
                        Bữa ăn
                        <select value={mealType} onChange={(e) => setMealType(e.target.value)}>
                          {slots.map((value) => (
                            <option value={value} key={value}>
                              {labels[value]}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>
                    {previewNutrition && (
                      <>
                        <div className="food-nutrition edit-nutrition">
                          <div>
                            <b>{fmt(previewNutrition.kcal)}</b>
                            <span>kcal</span>
                          </div>
                          <div>
                            <b>{fmt(previewNutrition.protein)}g</b>
                            <span>Protein</span>
                          </div>
                          <div>
                            <b>{fmt(previewNutrition.carb)}g</b>
                            <span>Carb</span>
                          </div>
                          <div>
                            <b>{fmt(previewNutrition.fat)}g</b>
                            <span>Chất béo</span>
                          </div>
                        </div>
                        <p className="edit-preview-note">
                          Ước tính theo khẩu phần mới. Nhấn dấu tích để lưu.
                        </p>
                      </>
                    )}
                    <div className="entry-actions">
                      <button
                        className="icon-button"
                        aria-label="Lưu chỉnh sửa"
                        disabled={busy}
                        onClick={() => saveEdit(entry.id)}
                      >
                        <Check size={17} />
                      </button>
                      <button
                        className="icon-button"
                        aria-label="Hủy chỉnh sửa"
                        onClick={() => setEditing(null)}
                      >
                        <X size={17} />
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="meal-icon">
                      <UtensilsCrossed size={17} />
                    </div>
                    <div className="meal-copy">
                      <strong>{entry.name}</strong>
                      <span>
                        {fmt(entry.amount ?? entry.grams)} {entry.unit || 'g'} ·{' '}
                        {fmt(entry.nutrition.kcal)} kcal
                      </span>
                    </div>
                    <div className="entry-actions">
                      <button
                        className="icon-button"
                        aria-label={`Sửa ${entry.name}`}
                        onClick={() => beginEdit(entry)}
                      >
                        <Pencil size={16} />
                      </button>
                      <button
                        className="icon-button danger"
                        aria-label={`Xóa ${entry.name}`}
                        disabled={busy}
                        onClick={() => remove(entry.id)}
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        );
      })}
      {!compact &&
        entries.some((entry) => entry.source_reference?.startsWith('Người dùng tự nhập')) && (
          <p className="data-note">
            Dinh dưỡng món tự nhập hoặc ước tính từ ảnh chưa được kiểm chứng; hãy đối chiếu trước
            khi dùng làm kế hoạch ăn uống.
          </p>
        )}
      {!compact &&
        entries.some(
          (entry) =>
            entry.source_reference?.startsWith('Người dùng tự nhập') && entry.nutrition.kcal === 0,
        ) && (
          <p className="data-note">Có món chưa có số liệu; tổng hôm nay chưa phản ánh đầy đủ.</p>
        )}
      {!compact &&
        entries.some(
          (entry) =>
            !entry.is_verified && !entry.source_reference?.startsWith('Người dùng tự nhập'),
        ) && (
          <p className="data-note">Số liệu demo chưa được kiểm chứng; chỉ dùng để thử giao diện.</p>
        )}
    </section>
  );
}
