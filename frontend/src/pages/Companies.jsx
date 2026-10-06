import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { companiesApi } from '../api/companies';
import { setupApi } from '../api/setup';
import { analysisApi } from '../api/analysis';
import { StatusBadge } from '../components/common/StatusBadge';
import { formatMoney, getCurrencySymbol } from '../utils/currency';

export const Companies = () => {
  const [companies, setCompanies] = useState([]);
  const [companyDetails, setCompanyDetails] = useState({});
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [loadingSample, setLoadingSample] = useState(false);
  const [actionMenuOpen, setActionMenuOpen] = useState(null);
  const navigate = useNavigate();

  const loadData = async () => {
    try {
      setLoading(true);
      const list = await companiesApi.list();
      setCompanies(list);

      // Load nested details & history for MRR and stats
      const detailsMap = {};
      await Promise.all(
        list.map(async (c) => {
          try {
            const [detail, history] = await Promise.all([
              companiesApi.get(c.id),
              analysisApi.history(c.id).catch(() => []),
            ]);

            // Calculate MRR from tiers
            let mrr = 0;
            if (detail.tiers) {
              mrr = detail.tiers.reduce((acc, t) => {
                const count = t.user_count || 0;
                const price = t.price || 0;
                const monthlyPrice = t.billing_cycle === 'annual' ? price / 12 : price;
                return acc + (monthlyPrice * count);
              }, 0);
            }

            const latestSession = history && history.length > 0 ? history[0] : null;

            detailsMap[c.id] = {
              detail,
              mrr: Math.round(mrr),
              tierCount: detail.tiers?.length || 0,
              lastAnalysis: latestSession ? new Date(latestSession.started_at || latestSession.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : 'Not run yet',
              lastAnalysisRaw: latestSession ? new Date(latestSession.started_at || latestSession.created_at) : null,
              status: latestSession ? (latestSession.status === 'completed' ? 'Completed' : (latestSession.status === 'partial' ? 'Partial' : 'Running')) : 'Pending',
              historyCount: history.length,
            };
          } catch {
            detailsMap[c.id] = {
              detail: c,
              mrr: 0,
              tierCount: 0,
              lastAnalysis: 'Not run yet',
              status: 'Pending',
              historyCount: 0,
            };
          }
        })
      );
      setCompanyDetails(detailsMap);
    } catch (err) {
      console.error('Failed to load companies', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleLoadSample = async () => {
    setLoadingSample(true);
    try {
      const res = await setupApi.loadSampleCompany(false);
      await loadData();
      if (res.company_id) {
        navigate(`/companies/${res.company_id}/tiers`);
      }
    } catch (err) {
      console.error('Failed to load sample company', err);
    } finally {
      setLoadingSample(false);
    }
  };

  const handleDuplicate = async (e, id) => {
    e.stopPropagation();
    setActionMenuOpen(null);
    try {
      const duplicated = await companiesApi.duplicate(id);
      await loadData();
      navigate(`/companies/${duplicated.id}/tiers`);
    } catch (err) {
      console.error('Failed to duplicate', err);
    }
  };

  const handleDelete = async (e, id) => {
    e.stopPropagation();
    setActionMenuOpen(null);
    if (window.confirm('Are you sure you want to delete this company and all its data?')) {
      try {
        await companiesApi.delete(id);
        await loadData();
      } catch (err) {
        console.error('Failed to delete company', err);
      }
    }
  };

  // Stats calculation
  const totalCompanies = companies.length;
  const combinedMRR = Object.values(companyDetails).reduce((acc, curr) => acc + (curr.mrr || 0), 0);
  const totalAnalyses = Object.values(companyDetails).reduce((acc, curr) => acc + (curr.historyCount || 0), 0);

  // Compute most recent analysis date string
  const dates = Object.values(companyDetails)
    .map(c => c.lastAnalysisRaw)
    .filter(Boolean)
    .sort((a, b) => b - a);

  let lastAnalysisTime = 'None';
  if (dates.length > 0) {
    const diffDays = Math.floor((new Date() - dates[0]) / (1000 * 60 * 60 * 24));
    if (diffDays === 0) lastAnalysisTime = 'Today';
    else if (diffDays === 1) lastAnalysisTime = 'Yesterday';
    else lastAnalysisTime = `${diffDays} days ago`;
  }

  const filteredCompanies = companies.filter(c =>
    c.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    (c.industry && c.industry.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  return (
    <div>
      {/* Page Header */}
      <div className="page-header">
        <div className="page-title-group">
          <h1>Companies</h1>
          <p className="page-subtitle">
            Each company holds its tiers, competitors and analysis history.
          </p>
        </div>
        <div className="page-actions">
          <button
            type="button"
            className="btn btn-secondary"
            disabled={loadingSample}
            onClick={handleLoadSample}
          >
            {loadingSample ? 'Loading sample...' : 'Load sample company'}
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => navigate('/companies/new')}
          >
            New company
          </button>
        </div>
      </div>

      {/* 4 Metric Cards (02-companies.png) */}
      <div className="metric-grid">
        <div className="metric-card">
          <div className="metric-label">COMPANIES</div>
          <div className="metric-value">{totalCompanies}</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">COMBINED MRR</div>
          <div className="metric-value">
            {formatMoney(combinedMRR, companies[0]?.currency || 'USD')}
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-label">ANALYSES RUN</div>
          <div className="metric-value">{totalAnalyses}</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">LAST ANALYSIS</div>
          <div className="metric-value" style={{ fontSize: '22px' }}>
            {lastAnalysisTime}
          </div>
        </div>
      </div>

      {/* Companies Table Card */}
      <div className="card">
        <div className="card-header" style={{ flexWrap: 'wrap', gap: '12px' }}>
          <h2 className="card-title" style={{ fontSize: '15px' }}>Your companies</h2>
          <div style={{ width: '260px' }}>
            <input
              type="text"
              className="form-input"
              style={{ padding: '6px 12px', fontSize: '13px' }}
              placeholder="Search companies"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
        </div>

        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th style={{ width: '30%' }}>COMPANY</th>
                <th>CURRENCY</th>
                <th>TIERS</th>
                <th>CURRENT MRR</th>
                <th>LAST ANALYSIS</th>
                <th>STATUS</th>
                <th style={{ textAlign: 'right' }}></th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan="7" style={{ textAlign: 'center', padding: '36px', color: 'var(--text-muted)' }}>
                    Loading companies...
                  </td>
                </tr>
              ) : filteredCompanies.length === 0 ? (
                <tr>
                  <td colSpan="7" style={{ textAlign: 'center', padding: '48px', color: 'var(--text-muted)' }}>
                    <div style={{ marginBottom: '12px', fontSize: '15px', color: 'var(--text-main)', fontWeight: 600 }}>
                      No companies found
                    </div>
                    <p style={{ marginBottom: '20px' }}>
                      Set up your first company or load a sample company to start analyzing SaaS pricing.
                    </p>
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() => navigate('/companies/new')}
                    >
                      Set up a company
                    </button>
                  </td>
                </tr>
              ) : (
                filteredCompanies.map((c) => {
                  const info = companyDetails[c.id] || {};
                  return (
                    <tr
                      key={c.id}
                      className="interactive-row"
                      onClick={() => navigate(`/companies/${c.id}/tiers`)}
                    >
                      <td>
                        <div style={{ fontWeight: 600, color: 'var(--text-main)', fontSize: '14px' }}>
                          {c.name}
                        </div>
                        <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
                          {c.industry ? c.industry.toUpperCase().replace('_', ' ') : 'SaaS'}
                          {c.description ? ` · ${c.description.slice(0, 36)}${c.description.length > 36 ? '...' : ''}` : ''}
                        </div>
                      </td>
                      <td className="mono" style={{ fontSize: '13px' }}>
                        {c.currency || 'USD'}
                      </td>
                      <td>
                        {info.tierCount !== undefined ? info.tierCount : '-'}
                      </td>
                      <td style={{ fontWeight: 600, color: 'var(--text-main)' }}>
                        {info.mrr !== undefined ? formatMoney(info.mrr, c.currency) : '-'}
                      </td>
                      <td style={{ color: 'var(--text-secondary)' }}>
                        {info.lastAnalysis || 'Not run yet'}
                      </td>
                      <td>
                        <StatusBadge status={info.status || 'Pending'} />
                      </td>
                      <td style={{ textAlign: 'right', position: 'relative' }} onClick={(e) => e.stopPropagation()}>
                        <button
                          type="button"
                          className="btn-ghost"
                          style={{ padding: '4px 8px', fontSize: '16px' }}
                          onClick={() => setActionMenuOpen(actionMenuOpen === c.id ? null : c.id)}
                        >
                          ···
                        </button>
                        {actionMenuOpen === c.id && (
                          <div
                            style={{
                              position: 'absolute',
                              right: '12px',
                              top: '40px',
                              backgroundColor: 'var(--bg-card)',
                              border: '1px solid var(--border-card)',
                              borderRadius: 'var(--radius-md)',
                              boxShadow: 'var(--shadow-md)',
                              zIndex: 10,
                              minWidth: '130px',
                              overflow: 'hidden',
                              textAlign: 'left',
                            }}
                          >
                            <button
                              type="button"
                              style={{ width: '100%', padding: '8px 14px', fontSize: '13px', textAlign: 'left', display: 'block', color: 'var(--text-main)' }}
                              onClick={(e) => handleDuplicate(e, c.id)}
                            >
                              Duplicate
                            </button>
                            <button
                              type="button"
                              style={{ width: '100%', padding: '8px 14px', fontSize: '13px', textAlign: 'left', display: 'block', color: 'var(--danger-text)' }}
                              onClick={(e) => handleDelete(e, c.id)}
                            >
                              Delete
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
