import React, { useEffect, useRef, useState } from 'react';
import {
  AlertCircle,
  Check,
  CheckCircle2,
  CloudUpload,
  Coffee,
  Cookie,
  ImagePlus,
  LoaderCircle,
  MoonStar,
  RefreshCw,
  Search,
  SunMedium,
  Trash2,
  X,
} from 'lucide-react';
import { formatNumber as fmt, isDiscreteUnit, MEAL_LABELS, NUTRIENT_KEYS } from './constants.js';

const mealOptions = [
  { id: 'breakfast', label: 'Bữa sáng', hint: '05:00–10:00', icon: Coffee },
  { id: 'lunch', label: 'Bữa trưa', hint: '10:00–14:00', icon: SunMedium },
  { id: 'dinner', label: 'Bữa tối', hint: '17:00–21:00', icon: MoonStar },
  { id: 'snack', label: 'Bữa phụ', hint: 'Ngoài bữa chính', icon: Cookie },
];
const emptyItem = (manual = false) => ({
  foodId: '',
  grams: 250,
  manual,
  search: '',
  custom: false,
  skipped: false,
  estimated: false,
  allowMissingNutrition: false,
  kcal: '',
  protein: '',
  carb: '',
  fat: '',
});
const nutrientKeys = NUTRIENT_KEYS;
const hasNutrition = (food) =>
  food && nutrientKeys.every((key) => Number.isFinite(Number(food[`${key}_100g`])));
const basisAmount = (food) => Number(food?.basis_amount || 100);
const quantityUnit = (food) => food?.basis_unit || 'g';
const defaultQuantity = (food) =>
  quantityUnit(food) === 'g' ? Math.max(100, basisAmount(food)) : basisAmount(food);
const catalogNutrition = (food, amount) =>
  Object.fromEntries(
    nutrientKeys.map((key) => [
      key,
      (Number(food?.[`${key}_100g`] || 0) * Number(amount || 0)) / basisAmount(food),
    ]),
  );
function suggestedItem(dish) {
  const catalogFood = dish.candidates.find(hasNutrition);
  if (catalogFood)
    return { ...emptyItem(), foodId: catalogFood.id, grams: defaultQuantity(catalogFood) };
  const estimate = dish.estimated_nutrition_100g;
  return {
    ...emptyItem(true),
    search: dish.suggested_labels[0] || '',
    custom: true,
    estimated: !!estimate,
    ...Object.fromEntries(nutrientKeys.map((key) => [key, estimate?.[key] ?? ''])),
  };
}

export default function ScanSection({
  call,
  foods,
  mealType,
  setMealType,
  onAdded,
  onHistoryChange,
}) {
  const picker = useRef(null);
  const scanInFlight = useRef(false);
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState('');
  const [scan, setScan] = useState(null);
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [dragging, setDragging] = useState(false);

  useEffect(
    () => () => {
      if (preview) URL.revokeObjectURL(preview);
    },
    [preview],
  );

  function update(index, changes) {
    setItems((current) => current.map((item, i) => (i === index ? { ...item, ...changes } : item)));
  }
  function clearPhoto() {
    setFile(null);
    setPreview('');
    setScan(null);
    setItems([]);
    setError('');
    if (picker.current) picker.current.value = '';
  }

  async function recognize(selected) {
    if (!selected || scanInFlight.current || busy) return;
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(selected.type)) {
      clearPhoto();
      setError('Ảnh không hợp lệ. Hãy chọn JPG, PNG hoặc WEBP.');
      return;
    }
    if (selected.size > 5 * 1024 * 1024) {
      clearPhoto();
      setError('Ảnh vượt quá 5 MB. Hãy chọn ảnh nhỏ hơn.');
      return;
    }
    scanInFlight.current = true;
    setFile(selected);
    setPreview(URL.createObjectURL(selected));
    setScan(null);
    setItems([]);
    setError('');
    setSuccess('');
    setBusy('scan');
    try {
      const form = new FormData();
      form.append('file', selected);
      form.append('meal_type', mealType);
      const result = await call('/api/scan', { method: 'POST', body: form });
      setScan(result);
      setItems(result.dishes.map(suggestedItem));
      if (result.status === 'unknown')
        setError('Chưa nhận diện được món trong danh mục. Bạn có thể tìm tên món thủ công.');
    } catch (err) {
      setError(`${err.message}. Bạn có thể thử lại hoặc nhập món thủ công.`);
      setScan({
        request_id: crypto.randomUUID(),
        dishes: [
          {
            suggested_labels: [],
            candidates: [],
            visible_ingredients: [],
            uncertainty_reason: 'Chưa có gợi ý từ AI',
          },
        ],
        warnings: [],
      });
      setItems([emptyItem(true)]);
    } finally {
      scanInFlight.current = false;
      setBusy('');
    }
  }

  async function demo(filename) {
    const response = await fetch(`/demo/${filename}`);
    if (!response.ok) {
      setError('Không tải được ảnh mẫu.');
      return;
    }
    const selected = new File([await response.blob()], filename, { type: 'image/png' });
    await recognize(selected);
  }

  const active = items.filter((item) => !item.skipped);
  const validAmount = (item) => {
    const amount = Number(item.grams);
    const food = foods.find((candidate) => candidate.id === item.foodId);
    const unit = item.custom ? 'g' : quantityUnit(food);
    return amount > 0 && amount <= 2000 && (!isDiscreteUnit(unit) || Number.isInteger(amount));
  };
  const ready =
    active.length > 0 &&
    active.every(
      (item) =>
        (item.foodId ||
          (item.custom &&
            item.search.trim().length >= 2 &&
            ((Number(item.kcal) > 0 &&
              nutrientKeys.every((key) => item[key] !== '' && item[key] != null)) ||
              item.allowMissingNutrition))) &&
        validAmount(item),
    );
  async function save() {
    if (!ready) return;
    const avoidMatches = [
      ...new Set(
        scan.dishes.flatMap((dish, index) =>
          items[index]?.skipped ? [] : dish.avoid_matches || [],
        ),
      ),
    ];
    const avoidanceAcknowledged =
      avoidMatches.length > 0
        ? window.confirm(
            `Cảnh báo: món có thể chứa thành phần bạn cần tránh: ${avoidMatches.join(', ')}. Bạn đã kiểm tra và vẫn muốn thêm?`,
          )
        : false;
    if (avoidMatches.length > 0 && !avoidanceAcknowledged) return;
    setBusy('save');
    setError('');
    try {
      await call('/api/food-logs/batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          confirmation_id: scan.request_id,
          avoidance_acknowledged: avoidanceAcknowledged,
          items: active.map((item) => ({
            food_id: item.custom ? null : item.foodId,
            custom_food: item.custom
              ? {
                  name: item.search.trim(),
                  ...Object.fromEntries(
                    ['kcal', 'protein', 'carb', 'fat'].map((key) => [
                      `${key}_100g`,
                      Number(item[key] || 0),
                    ]),
                  ),
                }
              : null,
            grams: Number(item.grams),
            meal_type: mealType,
            confirmed: true,
          })),
        }),
      });
      clearPhoto();
      setSuccess(`Đã thêm ${active.length} món vào thực đơn hôm nay.`);
      await onAdded();
      onHistoryChange?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  }

  return (
    <div className="food-flow">
      <section className="panel upload-panel" aria-labelledby="upload-title">
        <div className="panel-heading">
          <div>
            <div className="section-kicker">
              <ImagePlus size={15} /> NHẬN DIỆN MÓN ĂN
            </div>
            <h2 id="upload-title">Tải ảnh bữa ăn</h2>
          </div>
          <span className="step-pill">BƯỚC 01</span>
        </div>
        <p className="panel-lead">
          Chọn hoặc kéo thả ảnh. Gemini sẽ gợi ý từng món để bạn kiểm tra trước khi thêm.
        </p>
        <div className="meal-picker" aria-labelledby="meal-picker-title">
          <div className="meal-picker-heading">
            <strong id="meal-picker-title">Bạn đang ghi món cho bữa nào?</strong>
            <span>Chọn bữa trước hoặc sau khi tải ảnh.</span>
          </div>
          <div className="meal-choice-grid" role="group" aria-label="Chọn bữa ăn">
            {mealOptions.map((option) => {
              const Icon = option.icon;
              return (
                <button
                  type="button"
                  className={`meal-choice ${mealType === option.id ? 'selected' : ''}`}
                  aria-pressed={mealType === option.id}
                  onClick={() => setMealType(option.id)}
                  key={option.id}
                >
                  <Icon size={18} />
                  <span>
                    <b>{option.label}</b>
                    <small>{option.hint}</small>
                  </span>
                  {mealType === option.id && <Check size={15} className="meal-choice-check" />}
                </button>
              );
            })}
          </div>
        </div>
        <input
          ref={picker}
          className="sr-only"
          type="file"
          accept="image/jpeg,image/png,image/webp"
          onChange={(event) => {
            const selected = event.target.files[0];
            if (selected) void recognize(selected);
          }}
        />
        <div
          className={`drop-zone ${dragging ? 'dragging' : ''} ${preview ? 'has-preview' : ''}`}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            const selected = event.dataTransfer.files[0];
            if (selected) void recognize(selected);
          }}
        >
          {preview ? (
            <>
              <img src={preview} alt="Ảnh bữa ăn đang được kiểm tra" />
              <div className="photo-actions">
                <button
                  className="photo-button"
                  disabled={busy}
                  onClick={() => picker.current?.click()}
                >
                  <RefreshCw size={16} /> Đổi ảnh
                </button>
                <button className="photo-button" disabled={busy} onClick={clearPhoto}>
                  <Trash2 size={16} /> Xóa ảnh
                </button>
              </div>
            </>
          ) : (
            <>
              <div className="upload-icon">
                <CloudUpload size={28} />
              </div>
              <strong>Kéo thả ảnh món ăn vào đây</strong>
              <span>hoặc chọn ảnh từ thiết bị của bạn</span>
              <button className="primary-button" onClick={() => picker.current?.click()}>
                <ImagePlus size={17} /> Tải ảnh
              </button>
              <small>JPG, PNG hoặc WEBP · Tối đa 5 MB</small>
            </>
          )}
        </div>
        {preview && !busy && (
          <button className="link-button retry-button" onClick={() => recognize(file)}>
            <RefreshCw size={15} /> Thử nhận diện lại
          </button>
        )}
        {busy && (
          <div className="inline-state loading" role="status">
            <LoaderCircle size={18} className="spin" />
            <span>{busy === 'scan' ? 'Đang phân tích ảnh…' : 'Đang thêm món…'}</span>
          </div>
        )}
        {error && (
          <div className="inline-state error" role="alert">
            <AlertCircle size={18} />
            <span>{error}</span>
          </div>
        )}
        {success && (
          <div className="inline-state success" role="status">
            <CheckCircle2 size={18} />
            <span>{success}</span>
          </div>
        )}
        <div className="demo-links">
          <span>Ảnh thử nhanh:</span>
          <button disabled={busy} onClick={() => demo('pho_bo_synthetic.png')}>
            Một món
          </button>
          <button disabled={busy} onClick={() => demo('pho_bo_com_tam_synthetic.png')}>
            Hai món
          </button>
        </div>
      </section>

      {scan && (
        <section className="panel recognition-panel" aria-labelledby="recognition-title">
          <div className="panel-heading">
            <div>
              <div className="section-kicker">
                <CheckCircle2 size={15} /> KIỂM TRA KẾT QUẢ
              </div>
              <h2 id="recognition-title">Xác nhận món ăn</h2>
            </div>
            <span className="step-pill">BƯỚC 02</span>
          </div>
          <p className="panel-lead">
            Chọn đúng món và chỉnh khẩu phần. Món chưa xác nhận sẽ không tính vào tổng dinh dưỡng.
          </p>
          {scan.dishes.map((dish, index) => {
            const item = items[index];
            if (!item) return null;
            const usableCandidates = dish.candidates.filter(hasNutrition);
            const selected =
              foods.find((food) => food.id === item.foodId) ||
              usableCandidates.find((food) => food.id === item.foodId);
            const previewFood = selected || (!item.manual ? usableCandidates[0] : null);
            const values =
              item.custom && nutrientKeys.some((key) => item[key] !== '' && item[key] != null)
                ? Object.fromEntries(
                    nutrientKeys.map((key) => [
                      key,
                      (Number(item[key] || 0) * Number(item.grams || 0)) / 100,
                    ]),
                  )
                : previewFood
                  ? catalogNutrition(previewFood, item.grams)
                  : null;
            const unit = item.custom ? 'g' : quantityUnit(previewFood);
            const query = item.search.toLocaleLowerCase('vi');
            const filtered = foods.filter(
              (food) =>
                hasNutrition(food) &&
                (!query ||
                  food.name.toLocaleLowerCase('vi').includes(query) ||
                  food.aliases.some((alias) => alias.toLocaleLowerCase('vi').includes(query))),
            );
            return (
              <div className={`recognized-dish ${item.skipped ? 'is-skipped' : ''}`} key={index}>
                <div className="dish-top">
                  <div>
                    <span className="dish-number">MÓN {String(index + 1).padStart(2, '0')}</span>
                    <h3>{dish.suggested_labels[0] || 'Món chưa rõ'}</h3>
                    <span
                      className={`recognition-confidence ${(dish.confidence ?? 0) >= 0.8 ? 'high' : (dish.confidence ?? 0) >= 0.65 ? 'medium' : 'low'}`}
                    >
                      {(dish.confidence ?? 0) >= 0.8
                        ? 'Tin cậy cao'
                        : (dish.confidence ?? 0) >= 0.65
                          ? 'Cần kiểm tra'
                          : 'Không chắc chắn — hãy nhập tay'}
                    </span>
                  </div>
                  <button
                    className="subtle-button"
                    onClick={() => update(index, { skipped: !item.skipped })}
                  >
                    {item.skipped ? 'Khôi phục' : 'Bỏ qua món này'}
                  </button>
                </div>
                {!item.skipped && (
                  <>
                    {dish.visible_ingredients.length > 0 && (
                      <p className="observed">Nhìn thấy: {dish.visible_ingredients.join(', ')}</p>
                    )}
                    {dish.uncertainty_reason && (
                      <p className="observed">{dish.uncertainty_reason}</p>
                    )}
                    {dish.avoid_matches?.length > 0 && (
                      <div className="inline-state avoid-warning" role="alert">
                        <AlertCircle size={18} />
                        <span>
                          <b>Cảnh báo thành phần cần tránh:</b> {dish.avoid_matches.join(', ')}. Kết
                          quả từ ảnh không thể xác nhận món hoàn toàn an toàn.
                        </span>
                      </div>
                    )}
                    {!item.manual && usableCandidates.length > 0 && (
                      <div
                        className="choice-grid"
                        role="group"
                        aria-label={`Gợi ý món ${index + 1}`}
                      >
                        {usableCandidates.map((food) => (
                          <button
                            key={food.id}
                            className={`food-choice ${item.foodId === food.id ? 'chosen' : ''}`}
                            aria-pressed={item.foodId === food.id}
                            onClick={() =>
                              update(index, { foodId: food.id, grams: defaultQuantity(food) })
                            }
                          >
                            <span>
                              {food.name}
                              <small>{food.basis_label || '100 g'}</small>
                            </span>
                            {item.foodId === food.id && <Check size={17} />}
                          </button>
                        ))}
                      </div>
                    )}
                    {!item.manual && (
                      <button
                        className="link-button"
                        onClick={() =>
                          update(index, {
                            manual: true,
                            custom: true,
                            foodId: '',
                            grams: 250,
                            search: dish.suggested_labels[0] || '',
                            estimated: !!dish.estimated_nutrition_100g,
                            ...Object.fromEntries(
                              nutrientKeys.map((key) => [
                                key,
                                dish.estimated_nutrition_100g?.[key] ?? '',
                              ]),
                            ),
                          })
                        }
                      >
                        <Search size={15} /> Gợi ý chưa đúng? Nhập tay
                      </button>
                    )}
                    {item.manual && (
                      <div className="manual-fields">
                        <label>
                          Tên món bạn nhận ra
                          <input
                            value={item.search}
                            onChange={(event) =>
                              update(index, {
                                search: event.target.value,
                                foodId: '',
                                custom: true,
                                estimated: false,
                                allowMissingNutrition: false,
                                ...Object.fromEntries(nutrientKeys.map((key) => [key, ''])),
                              })
                            }
                            placeholder="Nhập tên món"
                          />
                        </label>
                        {filtered.length > 0 && (
                          <label>
                            Hoặc chọn món trong danh mục
                            <select
                              value={item.custom ? '' : item.foodId}
                              onChange={(event) => {
                                const food = foods.find((value) => value.id === event.target.value);
                                update(index, {
                                  foodId: event.target.value,
                                  custom: false,
                                  grams: food ? defaultQuantity(food) : item.grams,
                                });
                              }}
                            >
                              <option value="">Chọn món</option>
                              {filtered.map((food) => (
                                <option key={food.id} value={food.id}>
                                  {food.name} · {food.basis_label || '100 g'}
                                </option>
                              ))}
                            </select>
                          </label>
                        )}
                        <label className="custom-choice">
                          <input
                            type="checkbox"
                            checked={item.custom}
                            onChange={(event) =>
                              update(index, {
                                custom: event.target.checked,
                                foodId: '',
                                ...(event.target.checked ? { grams: 250 } : {}),
                              })
                            }
                          />{' '}
                          Món chưa có trong danh mục — tự xác nhận tên và dinh dưỡng
                        </label>
                        {item.custom && (
                          <>
                            <p className="data-note">
                              <b>Dinh dưỡng ước tính trong 1 g món ăn</b>
                            </p>
                            <div className="custom-macros">
                              {[
                                ['kcal', 'Calo (kcal)'],
                                ['protein', 'Protein (g)'],
                                ['carb', 'Carb (g)'],
                                ['fat', 'Chất béo (g)'],
                              ].map(([key, label]) => (
                                <label key={key}>
                                  {label} / 1 g
                                  <input
                                    type="number"
                                    min="0"
                                    max={key === 'kcal' ? '9' : '1'}
                                    step="any"
                                    value={
                                      item[key] === '' || item[key] == null
                                        ? ''
                                        : Number((Number(item[key]) / 100).toFixed(6))
                                    }
                                    onChange={(event) =>
                                      update(index, {
                                        [key]:
                                          event.target.value === ''
                                            ? ''
                                            : Number((Number(event.target.value) * 100).toFixed(4)),
                                        allowMissingNutrition: false,
                                      })
                                    }
                                    placeholder="Chưa rõ"
                                  />
                                </label>
                              ))}
                            </div>
                            <p className="data-note">
                              {item.estimated
                                ? 'Gemini ước tính cho 1 g món đã chế biến; bạn hãy sửa nếu cần. '
                                : 'Chưa có đủ số liệu; bạn có thể nhập tay. '}
                              Dinh dưỡng khẩu phần = giá trị trên 1 g × số gram bạn nhập. Chỉ lưu
                              khi bạn đã kiểm tra bốn ô.
                            </p>
                            {!(
                              Number(item.kcal) > 0 &&
                              nutrientKeys.every((key) => item[key] !== '' && item[key] != null)
                            ) && (
                              <label className="custom-choice">
                                <input
                                  type="checkbox"
                                  checked={item.allowMissingNutrition}
                                  onChange={(event) =>
                                    update(index, { allowMissingNutrition: event.target.checked })
                                  }
                                />{' '}
                                Vẫn thêm món dù thiếu dinh dưỡng (ô trống tính là 0)
                              </label>
                            )}
                          </>
                        )}
                        {usableCandidates.length > 0 && (
                          <button
                            className="link-button"
                            onClick={() =>
                              update(index, {
                                manual: false,
                                custom: false,
                                foodId: usableCandidates[0].id,
                                search: '',
                                grams: defaultQuantity(usableCandidates[0]),
                              })
                            }
                          >
                            <X size={15} /> Quay lại gợi ý
                          </button>
                        )}
                      </div>
                    )}
                    <div className="result-fields">
                      <label>
                        Khẩu phần
                        <input
                          type="number"
                          min={isDiscreteUnit(unit) ? '1' : '0.1'}
                          max="2000"
                          step={isDiscreteUnit(unit) ? '1' : '0.1'}
                          value={item.grams}
                          onChange={(event) => update(index, { grams: event.target.value })}
                        />
                      </label>
                      <span className="unit-label">{unit}</span>
                    </div>
                    {values && (
                      <div className={`food-nutrition ${!selected ? 'preview-values' : ''}`}>
                        <div>
                          <b>{fmt(values.kcal)}</b>
                          <span>kcal</span>
                        </div>
                        <div>
                          <b>{fmt(values.protein)}g</b>
                          <span>Protein</span>
                        </div>
                        <div>
                          <b>{fmt(values.carb)}g</b>
                          <span>Carb</span>
                        </div>
                        <div>
                          <b>{fmt(values.fat)}g</b>
                          <span>Chất béo</span>
                        </div>
                      </div>
                    )}
                    {item.custom && item.estimated && (
                      <p className="source-note">
                        Ước tính từ Gemini theo ảnh, chưa kiểm chứng; chỉ cộng vào thực đơn sau khi
                        bạn xác nhận.
                      </p>
                    )}
                    {previewFood && (
                      <p className="source-note">
                        Dữ liệu theo {previewFood.basis_label || '100 g'}. Nguồn:{' '}
                        {previewFood.source_reference}
                        {!previewFood.is_verified && ' · Chưa được kiểm chứng'}
                      </p>
                    )}
                  </>
                )}
              </div>
            );
          })}
          <button
            className="link-button add-missed"
            onClick={() => {
              if (items.length >= 5) {
                setError('Tối đa 5 món trong một ảnh.');
                return;
              }
              setScan((current) => ({
                ...current,
                dishes: [
                  ...current.dishes,
                  {
                    suggested_labels: [],
                    candidates: [],
                    visible_ingredients: [],
                    uncertainty_reason: 'Món bạn tự thêm',
                  },
                ],
              }));
              setItems((current) => [...current, emptyItem(true)]);
            }}
          >
            + Thêm món Gemini bỏ sót
          </button>
          <div className="confirm-footer">
            <label>
              Bữa ăn
              <select value={mealType} onChange={(event) => setMealType(event.target.value)}>
                {Object.entries(MEAL_LABELS).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <button className="primary-button" disabled={!ready || busy} onClick={save}>
              <Check size={18} /> Xác nhận thêm {active.length} món
            </button>
          </div>
        </section>
      )}
    </div>
  );
}
