export function formatPrice(
  price: string | number | null | undefined,
  currency: string
): string {
  if (price === null || price === undefined) return '—';
  const num = Number(price);
  if (isNaN(num)) return '—';
  try {
    return new Intl.NumberFormat('en-GB', {
      style: 'currency',
      currency,
      minimumFractionDigits: 2,
    }).format(num);
  } catch {
    return '—';
  }
}
