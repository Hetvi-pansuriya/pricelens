import React from 'react';

export const StatusBadge = ({ status, text }) => {
  const normalized = (status || '').toLowerCase().trim();
  let badgeClass = 'badge-neutral';
  let label = text || status;

  if (['completed', 'success', 'ready', 'verified', 'active', 'right placed', 'low risk'].includes(normalized)) {
    badgeClass = 'badge-success';
  } else if (['partial', 'warning', 'confirm', 'medium risk', 'undifferentiated'].includes(normalized)) {
    badgeClass = 'badge-warning';
  } else if (['failed', 'blocked', 'error', 'high risk', 'blocker'].includes(normalized)) {
    badgeClass = 'badge-danger';
  } else if (['running', 'in_progress', 'processing', 'gatekeeper'].includes(normalized)) {
    badgeClass = 'badge-info';
  }

  // Capitalize nicely if not given
  if (!text && label) {
    label = label.charAt(0).toUpperCase() + label.slice(1);
  }

  return (
    <span className={`badge ${badgeClass}`}>
      {label}
    </span>
  );
};
