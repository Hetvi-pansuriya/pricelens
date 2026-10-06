import React, { useState } from 'react';
import { useAuth } from '../../context/AuthContext';

export const AccountModal = ({ isOpen, onClose }) => {
  const { user, deleteAccount } = useAuth();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState('');

  if (!isOpen) return null;

  const handleDelete = async () => {
    setDeleting(true);
    setError('');
    try {
      await deleteAccount();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to delete account. Please try again.');
      setDeleting(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="card-header">
          <h3 className="card-title">Account Settings</h3>
          <button className="btn-ghost" onClick={onClose} style={{ fontSize: '18px', padding: '4px' }}>✕</button>
        </div>

        <div className="card-padded" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div>
            <div className="metric-label">Signed in as</div>
            <div style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-main)' }}>
              {user?.email}
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
              PriceLens Workspace Member
            </div>
          </div>

          <div style={{ borderTop: '1px solid var(--border-light)', paddingTop: '18px' }}>
            <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--danger-text)', marginBottom: '6px' }}>
              Danger Zone
            </div>
            <p style={{ fontSize: '13px', marginBottom: '14px' }}>
              Deleting your account permanently removes all your companies, pricing tiers, competitor data, and generated reports.
            </p>

            {error && (
              <div className="callout callout-warning" style={{ marginBottom: '12px' }}>
                {error}
              </div>
            )}

            {!confirmDelete ? (
              <button
                type="button"
                className="btn btn-danger btn-sm"
                onClick={() => setConfirmDelete(true)}
              >
                Delete account
              </button>
            ) : (
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <button
                  type="button"
                  className="btn btn-danger btn-sm"
                  disabled={deleting}
                  onClick={handleDelete}
                >
                  {deleting ? 'Deleting...' : 'Yes, permanently delete my account'}
                </button>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setConfirmDelete(false)}
                >
                  Cancel
                </button>
              </div>
            )}
          </div>
        </div>

        <div style={{ padding: '14px 24px', backgroundColor: 'var(--bg-subtle)', borderTop: '1px solid var(--border-light)', display: 'flex', justifyContent: 'flex-end' }}>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
