import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export const Login = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await login({ email, password });
      navigate('/companies');
    } catch (err) {
      setError(err.response?.data?.detail || 'Invalid email or password. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="auth-split-wrapper">
      {/* Left Column: Value Props Preview (01-sign-in.png) */}
      <div className="auth-split-right">
        <div className="auth-preview-box">
          <div
            style={{
              fontSize: '11px',
              fontWeight: 700,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              color: 'var(--primary)',
              marginBottom: '12px',
            }}
          >
            WHAT YOU GET
          </div>
          <h2
            style={{
              fontSize: '24px',
              fontWeight: 700,
              color: 'var(--text-main)',
              marginBottom: '32px',
              lineHeight: 1.3,
            }}
          >
            Know what a price change will do before you make it.
          </h2>

          <div
            className="card"
            style={{
              backgroundColor: 'var(--bg-card)',
              borderRadius: '12px',
              padding: '8px 20px',
              border: '1px solid var(--border-card)',
              boxShadow: 'var(--shadow-md)',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                padding: '14px 0',
                borderBottom: '1px solid var(--border-light)',
                fontSize: '13.5px',
              }}
            >
              <span style={{ color: 'var(--text-secondary)' }}>Revenue impact</span>
              <span style={{ fontWeight: 600, color: 'var(--text-main)' }}>+10%, +20%, +30% scenarios</span>
            </div>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                padding: '14px 0',
                borderBottom: '1px solid var(--border-light)',
                fontSize: '13.5px',
              }}
            >
              <span style={{ color: 'var(--text-secondary)' }}>Feature audit</span>
              <span style={{ fontWeight: 600, color: 'var(--text-main)' }}>Tier placement review</span>
            </div>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                padding: '14px 0',
                borderBottom: '1px solid var(--border-light)',
                fontSize: '13.5px',
              }}
            >
              <span style={{ color: 'var(--text-secondary)' }}>Competitor benchmark</span>
              <span style={{ fontWeight: 600, color: 'var(--text-main)' }}>Live pricing pages</span>
            </div>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                padding: '14px 0',
                fontSize: '13.5px',
              }}
            >
              <span style={{ color: 'var(--text-secondary)' }}>Recommendations</span>
              <span style={{ fontWeight: 600, color: 'var(--text-main)' }}>Three ranked strategies</span>
            </div>
          </div>
        </div>
      </div>

      {/* Right Column: Sign In Form */}
      <div className="auth-split-left">
        <div className="auth-box">
          <div className="brand-logo" style={{ marginBottom: '36px', padding: 0 }}>
            <svg className="brand-icon-svg" viewBox="0 0 24 24">
              <circle cx="10" cy="10" r="7" />
              <path d="m21 21-6-6" />
              <circle cx="10" cy="10" r="2.5" fill="var(--primary)" opacity="0.4" />
            </svg>
            <span>PriceLens</span>
          </div>

          <h1 style={{ fontSize: '28px', marginBottom: '8px' }}>
            Sign in to your workspace
          </h1>
          <p style={{ marginBottom: '28px', color: 'var(--text-secondary)' }}>
            Pricing analysis for subscription businesses.
          </p>

          {error && (
            <div className="callout callout-warning" style={{ marginBottom: '20px' }}>
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label" htmlFor="email-input">
                Email
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

            <div className="form-group" style={{ marginBottom: '24px' }}>
              <div className="form-label">
                <label htmlFor="password-input">Password</label>
                <Link
                  to="/forgot-password"
                  style={{ color: 'var(--primary)', fontSize: '13px', fontWeight: 500 }}
                >
                  Forgot password?
                </Link>
              </div>
              <input
                id="password-input"
                type="password"
                required
                className="form-input"
                placeholder="••••••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              disabled={submitting}
              style={{ width: '100%', padding: '11px', fontSize: '14px', marginBottom: '20px' }}
            >
              {submitting ? 'Signing in...' : 'Sign in'}
            </button>
          </form>

          <div style={{ textAlign: 'center', fontSize: '13.5px', color: 'var(--text-secondary)' }}>
            New here?{' '}
            <Link to="/signup" style={{ color: 'var(--text-main)', fontWeight: 600 }}>
              Create an account
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
};

