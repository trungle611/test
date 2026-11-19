import React, { useEffect, useMemo, useState } from 'react';
import { CalendarRange, ChevronDown, UtensilsCrossed } from 'lucide-react';
import { formatNumber as fmt, MEAL_LABELS, MEAL_SLOTS } from './constants.js';

function GoalAssessment({ day }) {
  const assessment = day.assessment;
  if (!assessment) return null;
  const names = { kcal: 'Kcal', protein: 'Protein', carb: 'Carb', fat: 'Chất béo' };
  return (
    <div className={`history-goal-assessment ${assessment.status}`}>
      <div className="history-goal-title">
        <strong>
          {day.is_today ? 'Tạm tính hôm nay · ' : ''}
          {assessment.label}
        </strong>
        {day.targets?.target_weight_kg && (
          <span>Mục tiêu cân nặng: {fmt(day.targets.target_weight_kg)} kg</span>
        )}
      </div>
      {assessment.metrics.length > 0 ? (
        <>
          <div className="history-goal-metrics">
            {assessment.metrics.map((metric) => (
              <div key={metric.key}>
                <strong>{names[metric.key]}</strong>
                <span>
                  {fmt(metric.actual)} / {fmt(metric.target)} {metric.key === 'kcal' ? 'kcal' : 'g'}
                </span>
                <b>{fmt(metric.percent)}%</b>
                <small>
                  {metric.difference < 0
                    ? 'Còn thiếu'
                    : metric.difference > 0
                      ? 'Cao hơn'
                      : 'Đúng mức'}{' '}
                  {fmt(Math.abs(metric.difference))} {metric.key === 'kcal' ? 'kcal' : 'g'}
                </small>
              </div>
            ))}
          </div>
          <small>
            Quy tắc theo dõi: kcal 90–110%, protein từ 90% mục tiêu. Carb và chất béo hiển thị để
            đối chiếu. Kết quả dựa trên món đã ghi, không đảm bảo đạt cân nặng đúng hạn.
          </small>
        </>
      ) : (
        <small>
          Ngày này chưa lưu mục tiêu dinh dưỡng để so sánh. Thiết lập hồ sơ để theo dõi từ hôm nay.
        </small>
      )}
    </div>
  );
}

export default function FoodHistory({ call, refreshKey, onError }) {
  const [history, setHistory] = useState({ period_days: 30, days: [] });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    call('/api/food-history?days=30')
      .then((result) => {
        if (active) setHistory(result);
      })
      .catch((error) => {
        if (active) onError(error.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [call, refreshKey, onError]);

  const averages = useMemo(() => {
    const days = history.days || [];
    if (!days.length) return null;
    return Object.fromEntries(
      ['kcal', 'protein', 'carb', 'fat'].map((key) => [
        key,
        days.reduce((sum, day) => sum + Number(day.totals[key] || 0), 0) / days.length,
      ]),
    );
  }, [history]);

  return (
    <section className="panel food-history-panel">
      <div className="panel-heading">
        <div>
          <div className="section-kicker">
            <CalendarRange size={15} /> LỊCH SỬ ĂN UỐNG
          </div>
          <h2>Theo dõi dinh dưỡng theo ngày</h2>
        </div>
        <span className="count-pill">30 ngày</span>
      </div>
      <p className="panel-lead">Tổng hợp các món đã xác nhận hoặc đã tick trong thực đơn gợi ý.</p>
      {averages && (
        <div className="history-average">
          <span>Trung bình trên {history.days.length} ngày có dữ liệu</span>
          <div>
            <b>{fmt(averages.kcal)} kcal</b>
            <b>{fmt(averages.protein)}g protein</b>
            <b>{fmt(averages.carb)}g carb</b>
            <b>{fmt(averages.fat)}g chất béo</b>
          </div>
        </div>
      )}
      {loading ? (
        <p className="history-food-empty">Đang tải lịch sử…</p>
      ) : history.days.length === 0 ? (
        <div className="history-food-empty">
          <UtensilsCrossed size={23} />
          <span>Chưa có món đã ăn trong 30 ngày gần đây.</span>
        </div>
      ) : (
        <div className="food-day-list">
          {history.days.map((day, index) => (
            <details className="food-day" key={day.date} open={index === 0}>
              <summary>
                <div>
                  <strong>
                    {new Date(`${day.date}T12:00:00`).toLocaleDateString('vi-VN', {
                      weekday: 'long',
                      day: '2-digit',
                      month: '2-digit',
                      year: 'numeric',
                    })}
                  </strong>
                  <span>{day.entries.length} món</span>
                  {day.assessment && (
                    <span className={`history-goal-badge ${day.assessment.status}`}>
                      {day.is_today ? 'Tạm tính · ' : ''}
                      {day.assessment.label}
                    </span>
                  )}
                </div>
                <div className="day-macros">
                  <b>{fmt(day.totals.kcal)} kcal</b>
                  <span>P {fmt(day.totals.protein)}g</span>
                  <span>C {fmt(day.totals.carb)}g</span>
                  <span>F {fmt(day.totals.fat)}g</span>
                </div>
                <ChevronDown size={18} />
              </summary>
              <GoalAssessment day={day} />
              <div className="food-day-content">
                {MEAL_SLOTS.map((slot) => {
                  const entries = day.entries.filter((entry) => entry.meal_type === slot);
                  if (!entries.length) return null;
                  return (
                    <div className="history-meal-group" key={slot}>
                      <h3>{MEAL_LABELS[slot]}</h3>
                      {entries.map((entry) => (
                        <div className="history-food-row" key={entry.id}>
                          <span>{entry.name}</span>
                          <small>
                            {fmt(entry.amount)} {entry.unit} · {fmt(entry.nutrition.kcal)} kcal
                          </small>
                        </div>
                      ))}
                    </div>
                  );
                })}
              </div>
            </details>
          ))}
        </div>
      )}
    </section>
  );
}
