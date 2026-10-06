/**
 * Currency helpers for formatting and symbols throughout PriceLens.
 */

export const CURRENCY_SYMBOLS = {
  USD: '$',
  EUR: '€',
  GBP: '£',
  INR: '₹',
  CAD: 'CA$',
  AUD: 'AU$',
  JPY: '¥',
  CHF: 'CHF ',
  SGD: 'S$',
  AED: 'AED ',
  BRL: 'R$',
  CNY: '¥',
  SEK: 'kr ',
  NZD: 'NZ$',
};

export const SUPPORTED_CURRENCIES = [
  { code: 'USD', symbol: '$', label: 'USD ($)' },
  { code: 'EUR', symbol: '€', label: 'EUR (€)' },
  { code: 'GBP', symbol: '£', label: 'GBP (£)' },
  { code: 'INR', symbol: '₹', label: 'INR (₹)' },
  { code: 'CAD', symbol: 'CA$', label: 'CAD (CA$)' },
  { code: 'AUD', symbol: 'AU$', label: 'AUD (AU$)' },
  { code: 'JPY', symbol: '¥', label: 'JPY (¥)' },
  { code: 'CHF', symbol: 'CHF', label: 'CHF' },
  { code: 'SGD', symbol: 'S$', label: 'SGD (S$)' },
  { code: 'AED', symbol: 'AED', label: 'AED' },
  { code: 'BRL', symbol: 'R$', label: 'BRL (R$)' },
];

export const getCurrencySymbol = (currencyCode = 'USD') => {
  if (!currencyCode) return '$';
  const upper = String(currencyCode).toUpperCase().trim();
  return CURRENCY_SYMBOLS[upper] || (upper.length === 3 ? `${upper} ` : '$');
};

export const formatMoney = (amount, currencyCode = 'USD', includeCents = false) => {
  if (amount === null || amount === undefined || isNaN(amount)) return '—';
  const num = Number(amount);
  const symbol = getCurrencySymbol(currencyCode);
  const formatted = num.toLocaleString('en-US', {
    minimumFractionDigits: includeCents ? 2 : (Number.isInteger(num) ? 0 : 2),
    maximumFractionDigits: 2,
  });
  return `${symbol}${formatted}`;
};
