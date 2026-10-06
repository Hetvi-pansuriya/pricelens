import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link, useOutletContext } from 'react-router-dom';
import { analysisApi } from '../api/analysis';
import { StatusBadge } from '../components/common/StatusBadge';
import { formatMoney } from '../utils/currency';

export const AnalysisHistory = () => {
  const { companyId } = useParams();
  const navigate = useNavigate();
  const { company } = useOutletContext();

  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchHistory = async () => {
      try {
        setLoading(true);
        const data = await analysisApi.history(companyId);
        setHistory(data);
      } catch (err) {
        setError(err.response?.data?.detail || 'Failed to load analysis history.');
      } finally {
        setLoading(false);
      }
    };
    fetchHistory();
  }, [companyId]);

  // Format run date & duration
  const formatRunDate = (isoStr) => {
    if (!isoStr) return 'N/A';
    const d = new Date(isoStr);
    const datePart = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    const timePart = d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
    return `${datePart} · ${timePart}`;
  };

  const formatDuration = (started, completed) => {
    if (!started || !completed) return '—';
    const diffSec = Math.round((new Date(completed) - new Date(started)) / 1000);
    if (diffSec < 60) return `${diffSec} s`;
    const min = Math.floor(diffSec / 60);
    const sec = diffSec % 60;
    return `${min} min ${sec.toString().padStart(2, '0')} s`;
  };

  // Find any partial run for the callout
  const partialRun = history.find(h => h.status === 'partial');

  // Compute MRR trend points for SVG sparkline chart
  const completedRunsWithMRR = history
    .filter(h => h.mrr && h.mrr > 0)
    .reverse(); // chronological order

  const mrrValues = completedRunsWithMRR.map(h => h.mrr);
  const minMRR = mrrValues.length > 0 ? Math.min(...mrrValues) * 0.95 : 0;
  const maxMRR = mrrValues.length > 0 ? Math.max(...mrrValues) * 1.05 : 1;

  let trendPercent = null;
  if (mrrValues.length >= 2) {
    const first = mrrValues[0];
    const last = mrrValues[mrrValues.length - 1];
    const diff = ((last - first) / first) * 100;
    trendPercent = `${diff >= 0 ? 'Up' : 'Down'} ${Math.abs(diff).toFixed(1)}% since ${new Date(completedRunsWithMRR[0].started_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`;
  }

  // Calculate SVG chart coordinates
  const svgWidth = 260;
  const svgHeight = 100;
  const paddingX = 20;
  const paddingY = 20;

  const points = completedRunsWithMRR.map((h, i) => {
    const x = paddingX + (i / Math.max(completedRunsWithMRR.length - 1, 1)) * (svgWidth - 2 * paddingX);
    const norm = (h.mrr - minMRR) / (maxMRR - minMRR || 1);
    const y = svgHeight - paddingY - norm * (svgHeight - 2 * paddingY);
    return { x, y, mrr: h.mrr };
  });

  const pathD = points.length > 1
    ? points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ')
    : '';

  return (
    <div>
      {/* Breadcrumb & Header */}
      <div className="breadcrumb-nav">
        <Link to="/companies">Companies</Link>
        <span className="breadcrumb-sep">/</span>
        <span>{company?.name || 'Company'}</span>
      </div>

      <div className="page-header">
        <div className="page-title-group">
          <h1>Analysis history</h1>
          <p className="page-subtitle">
            Every run is saved with its report and PDF.
          </p>
        </div>

        <div className="page-actions">
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => navigate(`/companies/${companyId}/analysis`)}
          >
            Run new analysis
          </button>
        </div>
      </div>

      {error && <div className="callout callout-warning">{error}</div>}

      {/* Two Column Layout (12-history.png) */}
      <div className="layout-columns">
        {/* Left Column: History Table */}
        <div className="card">
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th style={{ width: '32%' }}>RUN</th>
                  <th>STATUS</th>
                  <th>MRR AT RUN</th>
                  <th>DURATION</th>
                  <th style={{ textAlign: 'right' }}></th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan="5" style={{ textAlign: 'center', padding: '36px', color: 'var(--text-muted)' }}>
                      Loading analysis runs...
                    </td>
                  </tr>
                ) : history.length === 0 ? (
                  <tr>
                    <td colSpan="5" style={{ textAlign: 'center', padding: '36px', color: 'var(--text-muted)' }}>
                      No analyses run yet. Click "Run new analysis" to get started.
                    </td>
                  </tr>
                ) : (
                  history.map((sess) => {
                    const isSuccessOrPartial = ['completed', 'partial'].includes(sess.status);

                    return (
                      <tr key={sess.session_id}>
                        <td>
                          <div style={{ fontWeight: 600, color: 'var(--text-main)', fontSize: '13.5px' }}>
                            {formatRunDate(sess.started_at)}
                          </div>
                        </td>
                        <td>
                          <StatusBadge status={sess.status} />
                        </td>
                        <td className="mono" style={{ fontWeight: 600, color: 'var(--text-main)' }}>
                          {sess.mrr ? formatMoney(sess.mrr, sess.currency || company?.currency) : '—'}
                        </td>
                        <td style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>
                          {formatDuration(sess.started_at, sess.completed_at)}
                        </td>
                        <td style={{ textAlign: 'right' }}>
                          {isSuccessOrPartial ? (
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              onClick={() => navigate(`/reports/${sess.session_id}`)}
                            >
                              Open report
                            </button>
                          ) : (
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              onClick={() => alert(`Run error: ${sess.error_message || 'Timeout or configuration issue'}`)}
                            >
                              Details
                            </button>
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

        {/* Right Column: MRR Trend Chart & Callout (12-history.png) */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* MRR across runs card */}
          <div className="card card-padded">
            <h3 className="card-title" style={{ fontSize: '14px', marginBottom: '14px' }}>
              MRR across runs
            </h3>

            {points.length > 1 ? (
              <div>
                <svg width="100%" height="110" viewBox={`0 0 ${svgWidth} ${svgHeight}`} style={{ overflow: 'visible' }}>
                  {/* Subtle baseline */}
                  <line
                    x1="0"
                    y1={svgHeight - paddingY + 5}
                    x2={svgWidth}
                    y2={svgHeight - paddingY + 5}
                    stroke="var(--border-light)"
                    strokeWidth="1"
                  />
                  {/* Line connecting points */}
                  <path
                    d={pathD}
                    fill="none"
                    stroke="#8DA362"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                  {/* Dots */}
                  {points.map((p, i) => (
                    <circle
                      key={i}
                      cx={p.x}
                      cy={p.y}
                      r="4.5"
                      fill="#FFFFFF"
                      stroke="#5B6E38"
                      strokeWidth="2.2"
                    />
                  ))}
                </svg>

                {trendPercent && (
                  <div style={{ fontSize: '12.5px', color: 'var(--text-muted)', marginTop: '12px' }}>
                    {trendPercent}
                  </div>
                )}
              </div>
            ) : (
              <div style={{ fontSize: '13px', color: 'var(--text-muted)', padding: '20px 0' }}>
                Run multiple analyses over time to track your MRR growth and elasticity shifts.
              </div>
            )}
          </div>

          {/* Partial Report Callout (12-history.png) */}
          {partialRun && (
            <div className="callout callout-warning" style={{ borderRadius: 'var(--radius-md)' }}>
              <div>
                <strong>Partial report.</strong> One module did not finish on {new Date(partialRun.started_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}. Open the report to inspect module status.
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
