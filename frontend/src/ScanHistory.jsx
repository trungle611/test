import React, { useEffect, useState } from 'react';
import { CheckCircle2, Clock3, Eye, History, ImageOff, LoaderCircle, X } from 'lucide-react';
import { MEAL_LABELS as mealLabels } from './constants.js';

export default function ScanHistory({ call, refreshKey, onError }) {
  const [items, setItems] = useState([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [viewer, setViewer] = useState(null);

  async function load(limit = 6) {
    setLoading(true);
    try {
      const data = await call(`/api/scan-history?limit=${limit}`);
      setItems(data.items);
      setHasMore(data.has_more);
    } catch (error) {
      onError?.(error.message);
    } finally {
      setLoading(false);
    }
  }

  function closeViewer() {
    if (viewer?.url) URL.revokeObjectURL(viewer.url);
    setViewer(null);
  }
  async function openViewer(item, names) {
    setViewer({ item, names, url: '', loading: true, error: '' });
    try {
      const url = URL.createObjectURL(await call(item.image_url, { responseType: 'blob' }));
      setViewer((current) =>
        current?.item.id === item.id ? { ...current, url, loading: false } : current,
      );
    } catch (error) {
      setViewer((current) =>
        current?.item.id === item.id
          ? { ...current, loading: false, error: error.message }
          : current,
      );
    }
  }

  useEffect(() => {
    void load();
  }, [refreshKey]);
  useEffect(
    () => () => {
      if (viewer?.url) URL.revokeObjectURL(viewer.url);
    },
    [viewer?.url],
  );

  return (
    <section className="panel scan-history" aria-labelledby="scan-history-title">
      <div className="panel-heading">
        <div>
          <div className="section-kicker">
            <History size={15} /> LỊCH SỬ NHẬN DIỆN
          </div>
          <h2 id="scan-history-title">Ảnh đã quét gần đây</h2>
        </div>
        {loading && <LoaderCircle className="spin" size={19} />}
      </div>
      <p className="panel-lead">Xem lại ảnh và món đã xác nhận trong phiên sử dụng của bạn.</p>
      {!loading && items.length === 0 && (
        <div className="history-empty">
          <ImageOff size={24} />
          <span>Chưa có ảnh nào trong lịch sử.</span>
        </div>
      )}
      <div className="history-list">
        {items.map((item) => {
          const names = item.dishes.map((dish) => dish.labels?.[0]).filter(Boolean);
          return (
            <article className="history-card" key={item.id}>
              <div className="history-date">
                <strong>
                  {new Intl.DateTimeFormat('vi-VN', {
                    day: '2-digit',
                    month: '2-digit',
                    year: 'numeric',
                    timeZone: 'Asia/Ho_Chi_Minh',
                  }).format(new Date(item.created_at))}
                </strong>
                <span>
                  {new Intl.DateTimeFormat('vi-VN', {
                    hour: '2-digit',
                    minute: '2-digit',
                    timeZone: 'Asia/Ho_Chi_Minh',
                  }).format(new Date(item.created_at))}
                </span>
              </div>
              <div className="history-body">
                <span className="history-meal">{mealLabels[item.meal_type] || 'Bữa ăn'}</span>
                <strong>{names.length ? names.join(', ') : 'Chưa nhận diện được món'}</strong>
                <span className={`history-status ${item.confirmed_at ? 'confirmed' : 'pending'}`}>
                  {item.confirmed_at ? (
                    <>
                      <CheckCircle2 size={14} /> Đã thêm vào thực đơn
                    </>
                  ) : (
                    <>
                      <Clock3 size={14} /> Chờ xác nhận
                    </>
                  )}
                </span>
              </div>
              <button
                className="secondary-button history-view-button"
                onClick={() => void openViewer(item, names)}
              >
                <Eye size={15} /> Xem ảnh
              </button>
            </article>
          );
        })}
      </div>
      {hasMore && (
        <button
          className="secondary-button history-more"
          disabled={loading}
          onClick={() => void load(items.length + 6)}
        >
          Xem thêm lịch sử
        </button>
      )}
      {viewer && (
        <div className="history-viewer-backdrop" role="presentation">
          <div
            className="history-viewer"
            role="dialog"
            aria-modal="true"
            aria-labelledby="history-viewer-title"
          >
            <div className="history-viewer-heading">
              <div>
                <span>{mealLabels[viewer.item.meal_type] || 'Bữa ăn'}</span>
                <h3 id="history-viewer-title">
                  {viewer.names.length ? viewer.names.join(', ') : 'Ảnh món ăn đã quét'}
                </h3>
              </div>
              <button className="icon-button" aria-label="Đóng ảnh" onClick={closeViewer}>
                <X size={20} />
              </button>
            </div>
            <div className="history-viewer-image">
              {viewer.loading ? (
                <LoaderCircle className="spin" size={28} />
              ) : viewer.error ? (
                <>
                  <ImageOff size={28} />
                  <span>{viewer.error}</span>
                </>
              ) : (
                <img
                  src={viewer.url}
                  alt={
                    viewer.names.length ? `Ảnh ${viewer.names.join(', ')}` : 'Ảnh món ăn đã quét'
                  }
                />
              )}
            </div>
            <small>
              Chụp lúc{' '}
              {new Intl.DateTimeFormat('vi-VN', {
                hour: '2-digit',
                minute: '2-digit',
                timeZone: 'Asia/Ho_Chi_Minh',
                day: '2-digit',
                month: '2-digit',
                year: 'numeric',
              }).format(new Date(viewer.item.created_at))}
            </small>
          </div>
        </div>
      )}
    </section>
  );
}
