import React, { useState } from 'react';
import { useSearchParams, Link, useNavigate } from 'react-router-dom';
import { authApi } from '../api/auth';

export const ResetPassword = () => {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') || '';
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!token) {
      setError('Missing reset token. Please use the link sent to your email.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }
    if (newPassword.length < 8) {
      setError('Password must be at least 8 characters long.');
      return;
    }

    setLoading(true);
    setError('');
    try {
      await authApi.resetPassword(token, newPassword);
      setSuccess(true);
      setTimeout(() => navigate('/login'), 2500);
    } catch (err) {
      setError(err.response?.data?.detail || 'Invalid or expired token.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-split-wrapper">
      <div className="auth-split-left" style={{ flex: 1 }}>
        <div className="auth-box">
          <div className="brand-logo" style={{ marginBottom: '36px', padding: 0 }}>
            <svg className="brand-icon-svg" viewBox="0 0 24 24">
              <circle cx="10" cy="10" r="7" />
              <path d="m21 21-6-6" />
              <circle cx="10" cy="10" r="2.5" fill="var(--primary)" opacity="0.4" />
            </svg>
            <span>PriceLens</span>
          </div>

          <h1 style={{ fontSize: '26px', marginBottom: '8px' }}>Set new password</h1>
          <p style={{ marginBottom: '28px', color: 'var(--text-secondary)' }}>
            Enter your new password below.
          </p>

          {error && (
            <div className="callout callout-warning" style={{ marginBottom: '20px' }}>
              {error}
            </div>
          )}

          {success ? (
            <div>
              <div className="callout callout-success" style={{ marginBottom: '20px' }}>
                Password successfully updated! Redirecting to sign in...
              </div>
              <Link to="/login" className="btn btn-primary" style={{ width: '100%' }}>
                Sign in now
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label className="form-label" htmlFor="new-pw">
                  New Password
                </label>
                <input
                  id="new-pw"
                  type="password"
                  required
                  className="form-input"
                  placeholder="At least 8 characters"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                />
              </div>

              <div className="form-group" style={{ marginBottom: '24px' }}>
                <label className="form-label" htmlFor="conf-pw">
                  Confirm Password
                </label>
                <input
                  id="conf-pw"
                  type="password"
                  required
                  className="form-input"
                  placeholder="Repeat new password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                />
              </div>

              <button
                type="submit"
                className="btn btn-primary"
                disabled={loading}
                style={{ width: '100%', padding: '11px', marginBottom: '16px' }}
              >
                {loading ? 'Updating password...' : 'Update password'}
              </button>

              <div style={{ textAlign: 'center' }}>
                <Link to="/login" style={{ color: 'var(--text-secondary)', fontSize: '13.5px' }}>
                  ← Cancel
                </Link>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
};
