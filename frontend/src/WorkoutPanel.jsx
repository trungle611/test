import React, { useEffect, useState } from 'react';
import {
  Activity,
  CalendarDays,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  CirclePlay,
  Clock3,
  Dumbbell,
} from 'lucide-react';

const statusText = { not_started: 'Chưa bắt đầu', started: 'Đang tập', completed: 'Hoàn thành' };
const attendanceText = { attended: 'Có đi tập', missed: 'Nghỉ', completed: 'Hoàn thành' };
const weekdays = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'];

function monthKey(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
}

function monthLabel(value) {
  const [year, month] = value.split('-').map(Number);
  return new Intl.DateTimeFormat('vi-VN', { month: 'long', year: 'numeric' }).format(
    new Date(year, month - 1, 1),
  );
}

export default function WorkoutPanel({ workouts, call, refresh, onError }) {
  const [expanded, setExpanded] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [calendarMonth, setCalendarMonth] = useState(() => monthKey(new Date()));
  const [calendar, setCalendar] = useState(null);
  const [calendarLoading, setCalendarLoading] = useState(false);
  const items = workouts?.items || [];
  const completed = items.filter((item) => item.status === 'completed').length;
  const minutes = items.reduce((sum, item) => sum + item.duration_minutes, 0);
  const attendance = workouts?.attendance;
  const canTrain = attendance === 'attended';

  useEffect(() => {
    let active = true;
    setCalendarLoading(true);
    call(`/api/workouts/attendance?month=${calendarMonth}`)
      .then((result) => {
        if (active) setCalendar(result);
      })
      .catch((error) => {
        if (active) onError(error.message);
      })
      .finally(() => {
        if (active) setCalendarLoading(false);
      });
    return () => {
      active = false;
    };
  }, [calendarMonth, workouts?.date, workouts?.attendance, workouts?.selected_plan?.id]);

  function changeMonth(offset) {
    const [year, month] = calendarMonth.split('-').map(Number);
    setCalendarMonth(monthKey(new Date(year, month - 1 + offset, 1)));
  }

  async function act(item, action) {
    setBusyId(item.id);
    try {
      await call(`/api/workouts/${item.id}/${action}`, { method: 'POST' });
      await refresh();
    } catch (error) {
      onError(error.message);
    } finally {
      setBusyId(null);
    }
  }
  async function checkIn(status) {
    setBusyId('attendance');
    try {
      await call('/api/workouts/attendance', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      });
      await refresh();
    } catch (error) {
      onError(error.message);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="panel workout-panel" aria-labelledby="workout-title">
      <div className="panel-heading">
        <div>
          <div className="section-kicker">
            <Activity size={15} /> BUỔI TẬP KẾ TIẾP
          </div>
          <h2 id="workout-title">
            {workouts?.session_name} · Buổi {workouts?.session_number}
          </h2>
          <p className="session-plan">
            {workouts?.selected_plan?.name} · {workouts?.selected_plan?.sessions_per_cycle} buổi /
            chu kỳ
          </p>
        </div>
        <span className="count-pill">
          {completed}/{items.length} bài xong
        </span>
      </div>
      <p className="panel-lead">
        Tập theo thứ tự buổi, không theo thứ trong tuần. Bỏ lỡ hôm nay thì lần sau vẫn là buổi này.
        Hoàn thành tất cả bài để chuyển sang buổi kế tiếp.
      </p>
      <div className="attendance-box">
        <div>
          <strong>Hôm nay bạn có đi tập không?</strong>
          <span>
            {attendance ? `Đã ghi nhận: ${attendanceText[attendance]}` : 'Chưa ghi nhận hôm nay'}
          </span>
        </div>
        {attendance !== 'completed' && (
          <div className="attendance-actions">
            <button
              className="primary-button"
              disabled={busyId === 'attendance' || attendance === 'attended'}
              onClick={() => checkIn('attended')}
            >
              <Check size={16} /> Có đi tập
            </button>
            <button
              className="missed-button"
              disabled={busyId === 'attendance' || attendance === 'missed'}
              onClick={() => checkIn('missed')}
            >
              Nghỉ hôm nay
            </button>
          </div>
        )}
      </div>
      <div className="attendance-calendar">
        <div className="calendar-toolbar">
          <div>
            <span className="calendar-kicker">
              <CalendarDays size={15} /> LỊCH ĐI TẬP
            </span>
            <strong>{monthLabel(calendarMonth)}</strong>
          </div>
          <div className="calendar-nav">
            <button aria-label="Tháng trước" onClick={() => changeMonth(-1)}>
              <ChevronLeft size={18} />
            </button>
            <button
              className="calendar-today"
              disabled={calendarMonth === monthKey(new Date())}
              onClick={() => setCalendarMonth(monthKey(new Date()))}
            >
              Hôm nay
            </button>
            <button aria-label="Tháng sau" onClick={() => changeMonth(1)}>
              <ChevronRight size={18} />
            </button>
          </div>
        </div>
        <div className="calendar-summary">
          <span>
            <i className="legend-dot attended" /> Đi tập <b>{calendar?.attended_count || 0} ngày</b>
          </span>
          <span>
            <i className="legend-dot missed" /> Nghỉ <b>{calendar?.missed_count || 0} ngày</b>
          </span>
          <span>
            <i className="legend-dot unmarked" /> Chưa ghi nhận
          </span>
        </div>
        <div className={`calendar-grid ${calendarLoading ? 'is-loading' : ''}`}>
          {weekdays.map((day) => (
            <div className="calendar-weekday" key={day}>
              {day}
            </div>
          ))}
          {Array.from({ length: calendar?.first_weekday || 0 }, (_, index) => (
            <div className="calendar-empty" key={`empty-${index}`} />
          ))}
          {(calendar?.days || []).map((entry) => {
            const isToday = entry.day === workouts?.date;
            const isFuture = entry.day > workouts?.date;
            return (
              <div
                className={`calendar-day ${entry.status || 'unmarked'} ${isToday ? 'today' : ''} ${isFuture ? 'future' : ''}`}
                key={entry.day}
                title={`${entry.day}: ${attendanceText[entry.status] || 'Chưa ghi nhận'}`}
              >
                <b>{Number(entry.day.slice(8))}</b>
                {entry.status && <small>{entry.status === 'missed' ? 'Nghỉ' : 'Tập'}</small>}
              </div>
            );
          })}
        </div>
        <p>
          Ngày xanh là đã đi tập hoặc hoàn thành buổi tập; ngày đỏ là đã chọn nghỉ. Ngày xám chưa
          được tính là nghỉ.
        </p>
      </div>
      <div className="workout-overview">
        <span>
          <Clock3 size={16} /> Khoảng {minutes} phút
        </span>
        <span>
          <Dumbbell size={16} /> {items.length} bài tập
        </span>
      </div>
      {attendance === 'missed' && (
        <p className="missed-note">
          Buổi này được giữ lại cho lần đi tập tiếp theo. Bạn vẫn có thể sửa ghi nhận hôm nay.
        </p>
      )}
      <div className="workout-list">
        {items.map((item, index) => (
          <article
            className={`workout-item ${item.status === 'completed' ? 'is-complete' : ''}`}
            key={item.id}
          >
            <div className="workout-row">
              <div className="workout-number">{String(index + 1).padStart(2, '0')}</div>
              <div className="workout-copy">
                <strong>{item.name}</strong>
                <span>
                  {item.category} · {item.duration_minutes} phút
                  {item.sets ? ` · ${item.sets} hiệp${item.reps ? ` × ${item.reps}` : ''}` : ''}
                </span>
              </div>
              <span className={`status-tag ${item.status}`}>
                {item.status === 'completed' && <Check size={13} />} {statusText[item.status]}
              </span>
            </div>
            <div className="workout-actions">
              <button
                className="link-button"
                onClick={() => setExpanded(expanded === item.id ? null : item.id)}
              >
                {expanded === item.id ? 'Ẩn chi tiết' : 'Xem chi tiết'}{' '}
                {expanded === item.id ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
              </button>
              {canTrain && item.status === 'not_started' && (
                <button
                  className="small-action"
                  disabled={busyId === item.id}
                  onClick={() => act(item, 'start')}
                >
                  <CirclePlay size={15} /> Bắt đầu tập
                </button>
              )}
              {canTrain && item.status === 'started' && (
                <button
                  className="small-action"
                  disabled={busyId === item.id}
                  onClick={() => act(item, 'complete')}
                >
                  <Check size={15} /> Hoàn thành
                </button>
              )}
            </div>
            {expanded === item.id && (
              <div className="workout-detail">
                <p className="exercise-focus">Nhóm cơ chính: {item.focus}</p>
                <p>{item.detail}</p>
                {item.steps?.length > 0 && (
                  <ol className="exercise-steps">
                    {item.steps.map((step, index) => (
                      <li key={index}>{step}</li>
                    ))}
                  </ol>
                )}
                {item.rest_seconds > 0 && (
                  <p className="rest-note">Nghỉ khoảng {item.rest_seconds} giây giữa các hiệp.</p>
                )}
                {canTrain && item.status === 'not_started' && (
                  <button
                    className="primary-button"
                    disabled={busyId === item.id}
                    onClick={() => act(item, 'start')}
                  >
                    <CirclePlay size={17} /> Bắt đầu tập
                  </button>
                )}
                {canTrain && item.status === 'started' && (
                  <button
                    className="primary-button"
                    disabled={busyId === item.id}
                    onClick={() => act(item, 'complete')}
                  >
                    <Check size={17} /> Hoàn thành bài tập
                  </button>
                )}
                {item.status === 'completed' && (
                  <p className="done-copy">
                    <Check size={16} /> Bạn đã hoàn thành bài này trong buổi hiện tại.
                  </p>
                )}
                {!canTrain && item.status !== 'completed' && (
                  <p>Ghi nhận có đi tập để bắt đầu bài này.</p>
                )}
              </div>
            )}
          </article>
        ))}
      </div>
      <p className="data-note">Giáo án mẫu để tham khảo; dừng lại nếu đau hoặc không thoải mái.</p>
    </section>
  );
}
