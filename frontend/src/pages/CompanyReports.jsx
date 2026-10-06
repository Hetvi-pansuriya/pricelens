import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link, useOutletContext } from 'react-router-dom';
import { analysisApi } from '../api/analysis';

export const CompanyReports = () => {
  const { companyId } = useParams();
  const navigate = useNavigate();
  const { company } = useOutletContext();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const checkReports = async () => {
      try {
        setLoading(true);
        const history = await analysisApi.history(companyId);
        // Find latest completed session with a report
        const latestCompleted = history.find(
          (h) => h.status === 'completed' && (h.report_id || h.session_id)
        );

        if (latestCompleted) {
          // Redirect smoothly to the latest report view
          navigate(`/reports/${latestCompleted.session_id}`, { replace: true });
        } else {
          setLoading(false);
        }
      } catch (err) {
        setError(err.response?.data?.detail || 'Failed to check reports.');
        setLoading(false);
      }
    };

    checkReports();
  }, [companyId, navigate]);

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-muted)' }}>
        <p>Loading latest pricing report...</p>
      </div>
    );
  }

  return (
    <div>
      <div className="breadcrumb-nav">
        <Link to="/companies">Companies</Link>
        <span className="breadcrumb-sep">/</span>
        <span>{company?.name || 'Company'}</span>
      </div>

      <div className="page-header">
        <div className="page-title-group">
          <h1>Pricing Reports</h1>
          <p className="page-subtitle">
            Revenue impact models, feature tier placement audits, and competitor benchmarks.
          </p>
        </div>
      </div>

      {error && <div className="callout callout-warning">{error}</div>}

      <div className="card card-padded" style={{ textAlign: 'center', padding: '64px 24px', maxWidth: '680px', margin: '40px auto' }}>
        <div 
          style={{
            width: '54px',
            height: '54px',
            borderRadius: '50%',
            backgroundColor: 'var(--primary-light)',
            border: '1px solid var(--primary-border)',
            color: 'var(--primary)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            margin: '0 auto 20px auto',
          }}
        >
          <svg viewBox="0 0 24 24" width="28" height="28" stroke="currentColor" strokeWidth="2" fill="none">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="16" y1="13" x2="8" y2="13" />
            <line x1="16" y1="17" x2="8" y2="17" />
            <polyline points="10 9 9 9 8 9" />
          </svg>
        </div>

        <h3 style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text-main)', marginBottom: '8px' }}>
          No reports generated yet
        </h3>
        <p style={{ fontSize: '14px', color: 'var(--text-secondary)', maxWidth: '440px', margin: '0 auto 24px auto', lineHeight: 1.5 }}>
          Run your first pricing analysis for {company?.name || 'your company'} to get an interactive 4-part revenue and competitor benchmark report.
        </p>

        <div style={{ display: 'flex', gap: '12px', justifyContent: 'center' }}>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => navigate(`/companies/${companyId}/analysis`)}
          >
            Run analysis now →
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => navigate(`/companies/${companyId}/history`)}
          >
            View run history
          </button>
        </div>
      </div>
    </div>
  );
};
