export const MEAL_LABELS = {
  breakfast: 'Bữa sáng',
  lunch: 'Bữa trưa',
  dinner: 'Bữa tối',
  snack: 'Bữa phụ',
};

export const MEAL_SLOTS = Object.keys(MEAL_LABELS);
export const NUTRIENT_KEYS = ['kcal', 'protein', 'carb', 'fat'];

export function isDiscreteUnit(unit) {
  return !['g', 'ml'].includes((unit || 'g').toLocaleLowerCase('vi'));
}

export function formatNumber(value) {
  return Number(value || 0).toLocaleString('vi-VN', { maximumFractionDigits: 1 });
}
