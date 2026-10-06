import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate, Link, useOutletContext } from 'react-router-dom';
import { analysisApi } from '../api/analysis';
import { companiesApi } from '../api/companies';
import { StatusBadge } from '../components/common/StatusBadge';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const RunAnalysis = () => {
  const { companyId } = useParams();
  const navigate = useNavigate();
  const { company, setCompany } = useOutletContext();

  const [sessionId, setSessionId] = useState(null);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState('idle'); // 'idle' | 'running' | 'completed' | 'partial' | 'failed'
  const [secondsElapsed, setSecondsElapsed] = useState(0);
  const [error, setError] = useState('');
  const timerRef = useRef(null);
  const eventSourceRef = useRef(null);

  useEffect(() => {
    if (!company) {
      companiesApi.get(companyId).then(setCompany).catch(console.error);
    }
  }, [companyId]);

  // Start analysis
  const handleStartAnalysis = async () => {
    setError('');
    setProgress(5);
    setStatus('running');
    setSecondsElapsed(0);

    try {
      const startRes = await analysisApi.start(companyId);
      const sid = startRes.session_id;
      setSessionId(sid);

      // Start elapsed timer
      timerRef.current = setInterval(() => {
        setSecondsElapsed(prev => prev + 1);
      }, 1000);

      // Get ticket for SSE
      const ticketRes = await analysisApi.getTicket(sid);
      const ticket = ticketRes.ticket;

      // Connect SSE
      const es = new EventSource(`${API_BASE_URL}/analysis/progress/${sid}?ticket=${ticket}`);
      eventSourceRef.current = es;

      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          if (data.progress !== undefined) {
            setProgress(data.progress);
          }
          if (data.status) {
            setStatus(data.status);
          }
          if (data.progress === 100 || ['completed', 'partial'].includes(data.status)) {
            es.close();
            clearInterval(timerRef.current);
            setTimeout(() => {
              navigate(`/reports/${sid}`, { state: { autoEmailed: true } });
            }, 1200);
          } else if (data.status === 'failed') {
            es.close();
            clearInterval(timerRef.current);
            setError('Analysis failed. ' + (data.error_message || 'Please check your company tiers.'));
          }
        } catch (err) {
          console.error('SSE parse error', err);
        }
      };

      es.onerror = () => {
        // Fallback to polling if SSE drops
        console.warn('SSE disconnected, falling back to polling');
        es.close();
        startPollingFallback(sid);
      };
    } catch (err) {
      clearInterval(timerRef.current);
      setStatus('idle');
      setError(err.response?.data?.detail || 'Failed to start analysis.');
    }
  };

  const startPollingFallback = (sid) => {
    const pollInterval = setInterval(async () => {
      try {
        const history = await analysisApi.history(companyId);
        const current = history.find(h => h.session_id === sid);
        if (current) {
          setProgress(current.progress || 50);
          if (current.progress === 100 || ['completed', 'partial'].includes(current.status)) {
            clearInterval(pollInterval);
            clearInterval(timerRef.current);
            setTimeout(() => navigate(`/reports/${sid}`, { state: { autoEmailed: true } }), 1000);

          } else if (current.status === 'failed') {
            clearInterval(pollInterval);
            clearInterval(timerRef.current);
            setError('Analysis encountered an error.');
            setStatus('failed');
          }
        }
      } catch {
        // ignore polling network error
      }
    }, 3000);
  };

  const handleCancelView = () => {
    if (eventSourceRef.current) eventSourceRef.current.close();
    if (timerRef.current) clearInterval(timerRef.current);
    navigate(`/companies/${companyId}/tiers`);
  };

  useEffect(() => {
    return () => {
      if (eventSourceRef.current) eventSourceRef.current.close();
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  const tiers = company?.tiers || [];
  const competitors = company?.competitors || [];
  const tiersReady = tiers.length > 0;
  const usersReady = tiers.some(t => (t.user_count || 0) > 0);
  const compSuccessCount = competitors.filter(c => c.scrape_status?.includes('success')).length;

  // Determine sub-steps state based on progress
  const getStepState = (thresholdDone, thresholdRunning) => {
    if (progress >= thresholdDone) return 'done';
    if (progress >= thresholdRunning && status === 'running') return 'running';
    return 'waiting';
  };

  const m1State = getStepState(50, 5);
  const m2State = getStepState(50, 10);
  const m3State = getStepState(75, 50);
  const m4State = getStepState(90, 75);
  const reportState = getStepState(100, 90);

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
          <h1>Run analysis</h1>
          <p className="page-subtitle">
            Revenue and feature checks run first, then the benchmark and recommendations.
          </p>
        </div>

        <div className="page-actions">
          {status === 'running' ? (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleCancelView}
            >
              Cancel view
            </button>
          ) : (
            <button
              type="button"
              className="btn btn-primary"
              disabled={!tiersReady}
              onClick={handleStartAnalysis}
            >
              {tiersReady ? 'Start full analysis' : 'Add tiers first'}
            </button>
          )}
        </div>
      </div>

      {error && <div className="callout callout-warning">{error}</div>}

      {/* Two Column Layout (07-run-analysis.png) */}
      <div className="layout-columns">
        {/* Left Column: Analysis Progress Card */}
        <div className="card card-padded">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <h3 className="card-title">
              {status === 'running' ? 'Analysis in progress' : (status === 'completed' ? 'Analysis complete!' : 'Ready to analyze')}
            </h3>
            <span style={{ fontSize: '22px', fontWeight: 700, color: 'var(--text-main)' }}>
              {progress}%
            </span>
          </div>

          <div className="progress-bar-wrap" style={{ height: '9px', marginBottom: '14px' }}>
            <div className="progress-bar-fill" style={{ width: `${progress}%` }} />
          </div>

          <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '28px' }}>
            {status === 'running' ? (
              `Started ${secondsElapsed} seconds ago. You can leave this page; the analysis continues in the background.`
            ) : (
              'Click "Start full analysis" to trigger the sensitivity engine and Groq AI benchmarks.'
            )}
          </div>

          {/* 5 Step Progress List (07-run-analysis.png) */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {/* Step 1: Revenue Impact */}
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', gap: '12px' }}>
                <span style={{ marginTop: '2px', color: m1State === 'done' ? 'var(--primary)' : 'var(--text-muted)' }}>●</span>
                <div>
                  <div style={{ fontWeight: 600, fontSize: '14px', color: 'var(--text-main)' }}>
                    Revenue impact
                  </div>
                  <div style={{ fontSize: '12.5px', color: 'var(--text-muted)' }}>
                    Scenarios and price sensitivity calculated
                  </div>
                </div>
              </div>
              <StatusBadge status={m1State} />
            </div>

            {/* Step 2: Feature Audit */}
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', gap: '12px' }}>
                <span style={{ marginTop: '2px', color: m2State === 'done' ? 'var(--primary)' : 'var(--text-muted)' }}>●</span>
                <div>
                  <div style={{ fontWeight: 600, fontSize: '14px', color: 'var(--text-main)' }}>
                    Feature audit
                  </div>
                  <div style={{ fontSize: '12.5px', color: 'var(--text-muted)' }}>
                    Features classified across tiers (gatekeeper, blocker, etc.)
                  </div>
                </div>
              </div>
              <StatusBadge status={m2State} />
            </div>

            {/* Step 3: Competitor Benchmark */}
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', gap: '12px' }}>
                <span style={{ marginTop: '2px', color: m3State === 'done' ? 'var(--primary)' : 'var(--text-muted)' }}>●</span>
                <div>
                  <div style={{ fontWeight: 600, fontSize: '14px', color: 'var(--text-main)' }}>
                    Competitor benchmark
                  </div>
                  <div style={{ fontSize: '12.5px', color: 'var(--text-muted)' }}>
                    Comparing against tracked competitors
                  </div>
                </div>
              </div>
              <StatusBadge status={m3State} />
            </div>

            {/* Step 4: Recommendations */}
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', gap: '12px' }}>
                <span style={{ marginTop: '2px', color: m4State === 'done' ? 'var(--primary)' : 'var(--text-muted)' }}>●</span>
                <div>
                  <div style={{ fontWeight: 600, fontSize: '14px', color: 'var(--text-main)' }}>
                    Recommendations
                  </div>
                  <div style={{ fontSize: '12.5px', color: 'var(--text-muted)' }}>
                    Three alternative pricing strategies will be generated
                  </div>
                </div>
              </div>
              <StatusBadge status={m4State} />
            </div>

            {/* Step 5: Report */}
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', gap: '12px' }}>
                <span style={{ marginTop: '2px', color: reportState === 'done' ? 'var(--primary)' : 'var(--text-muted)' }}>●</span>
                <div>
                  <div style={{ fontWeight: 600, fontSize: '14px', color: 'var(--text-main)' }}>
                    Report
                  </div>
                  <div style={{ fontSize: '12.5px', color: 'var(--text-muted)' }}>
                    Saved to history with PDF export
                  </div>
                </div>
              </div>
              <StatusBadge status={reportState} />
            </div>
          </div>
        </div>

        {/* Right Column: Pre-flight Checklist (07-run-analysis.png) */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div className="card card-padded">
            <h3 className="card-title" style={{ marginBottom: '16px' }}>Before you start</h3>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', fontSize: '13.5px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>Tiers with prices</span>
                <span className={`badge ${tiersReady ? 'badge-success' : 'badge-danger'}`}>
                  {tiersReady ? 'Ready' : 'Missing'}
                </span>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>User counts</span>
                <span className={`badge ${usersReady ? 'badge-success' : 'badge-warning'}`}>
                  {usersReady ? 'Ready' : 'Recommended'}
                </span>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>Competitors fetched</span>
                <span className="badge badge-warning">
                  {compSuccessCount} of {competitors.length || 0}
                </span>
              </div>
            </div>
          </div>

          <div className="callout callout-info" style={{ borderRadius: 'var(--radius-md)', margin: 0 }}>
            <div>
              If a step fails or competitor scraping is blocked, the rest still complete and the report is marked partial.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
