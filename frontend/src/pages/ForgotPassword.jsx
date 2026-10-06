import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { authApi } from '../api/auth';

export const ForgotPassword = () => {
  const [email, setEmail] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await authApi.forgotPassword(email);
      setSubmitted(true);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to send reset link. Please check your email.');
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

          <h1 style={{ fontSize: '26px', marginBottom: '8px' }}>Reset password</h1>
          <p style={{ marginBottom: '28px', color: 'var(--text-secondary)' }}>
            Enter your email and we'll send you instructions to reset your password.
          </p>

          {error && (
            <div className="callout callout-warning" style={{ marginBottom: '20px' }}>
              {error}
            </div>
          )}

          {submitted ? (
            <div>
              <div className="callout callout-success" style={{ marginBottom: '20px' }}>
                If that email exists in our system, a password reset link has been dispatched.
              </div>
              <Link to="/login" className="btn btn-secondary" style={{ width: '100%' }}>
                Back to Sign in
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit}>
              <div className="form-group" style={{ marginBottom: '24px' }}>
                <label className="form-label" htmlFor="email-input">
                  Account Email
                </label>
                <input
                  id="email-input"
                  type="email"
                  required
                  className="form-input"
                  placeholder="name@company.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>

              <button
                type="submit"
                className="btn btn-primary"
                disabled={loading}
                style={{ width: '100%', padding: '11px', marginBottom: '16px' }}
              >
                {loading ? 'Sending link...' : 'Send reset link'}
              </button>

              <div style={{ textAlign: 'center' }}>
                <Link to="/login" style={{ color: 'var(--text-secondary)', fontSize: '13.5px' }}>
                  ← Return to sign in
                </Link>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
};
