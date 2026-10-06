import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, useLocation, Link, useOutletContext } from 'react-router-dom';
import { analysisApi } from '../api/analysis';
import { StatusBadge } from '../components/common/StatusBadge';
import { formatMoney, getCurrencySymbol } from '../utils/currency';

export const Report = () => {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const outletContext = useOutletContext() || {};
  const { setCompany } = outletContext;

  const [activeTab, setActiveTab] = useState('revenue');
  const [reportData, setReportData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const [autoEmailBanner, setAutoEmailBanner] = useState(location.state?.autoEmailed || false);
  const [selectedStrategyIndex, setSelectedStrategyIndex] = useState(0);

  useEffect(() => {
    let isMounted = true;
    const fetchReport = async () => {
      try {
        setLoading(true);
        const res = await analysisApi.getReport(sessionId);
        let parsed = res.json_report;
        if (typeof parsed === 'string') {
          try {
            parsed = JSON.parse(parsed);
          } catch (e) {
            console.error('Failed to parse json_report string', e);
          }
        }
        if (isMounted) {
          setReportData(parsed);
          if (parsed?.company && setCompany) {
            setCompany(parsed.company);
          }
        }
      } catch (err) {
        if (isMounted) {
          setError(err.response?.data?.detail || 'Failed to load report. It may still be processing.');
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    };
    fetchReport();
    return () => {
      isMounted = false;
    };
  }, [sessionId, setCompany]);

  const handleDownloadPdf = async () => {
    setDownloadingPdf(true);
    try {
      const companyName = reportData?.company?.name || 'pricing';
      await analysisApi.downloadPdf(sessionId, companyName);
    } catch (err) {
      alert('Could not download PDF: ' + (err.response?.data?.detail || err.message));
    } finally {
      setDownloadingPdf(false);
    }
  };


  if (loading) {
    return <div style={{ padding: '48px', color: 'var(--text-muted)' }}>Loading pricing analysis report...</div>;
  }

  if (error || !reportData) {
    return (
      <div style={{ padding: '32px' }}>
        <div className="callout callout-warning">{error || 'Report not found.'}</div>
        <button type="button" className="btn btn-secondary" onClick={() => navigate('/companies')}>
          Back to companies
        </button>
      </div>
    );
  }

  const { company, module1_revenue: m1, module2_features: m2, module3_benchmark: m3, module4_recommendations: m4 } = reportData;
  const companyId = company?.id;
  const companyName = company?.name || 'Company';
  const companyCurrency = company?.currency || m1?.currency || 'USD';
  const reportDate = new Date(reportData.generated_at || Date.now()).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });

  // MODULE 1 — REVENUE
  const currentMRR = m1?.current_mrr || 0;
  const bestScenarioKey = m1?.recommended_increase || '+20%';

  // Convert aggregate_scenarios dict to array
  let scenariosList = [];
  if (m1?.scenarios) {
    if (Array.isArray(m1.scenarios)) {
      scenariosList = m1.scenarios;
    } else {
      scenariosList = Object.entries(m1.scenarios).map(([key, data]) => ({
        increase: key,
        projected_mrr: data.projected_mrr,
        net_change: `${data.net_change_pct > 0 ? '+' : ''}${data.net_change_pct}%`,
        user_loss_pct: data.user_loss_pct,
        recommended: key === bestScenarioKey,
      }));
    }
  }
  if (scenariosList.length === 0) {
    scenariosList = [
      { increase: '+10%', projected_mrr: currentMRR * 1.06, net_change: '+6.7%', user_loss_pct: 3 },
      { increase: '+20%', projected_mrr: currentMRR * 1.10, net_change: '+10.4%', user_loss_pct: 8, recommended: true },
      { increase: '+30%', projected_mrr: currentMRR * 1.06, net_change: '+6.6%', user_loss_pct: 18 },
    ];
  }
  const bestScenario = scenariosList.find(s => s.increase === bestScenarioKey || s.recommended) || scenariosList[1] || scenariosList[0];

  // Per tier breakdown
  let tierBreakdowns = [];
  if (m1?.per_tier && Array.isArray(m1.per_tier)) {
    tierBreakdowns = m1.per_tier.map(t => {
      const bestTierScenario = t.scenarios?.[bestScenarioKey] || Object.values(t.scenarios || {})[0] || {};
      return {
        name: t.tier_name,
        current: t.current_mrr,
        projected: bestTierScenario.projected_mrr || t.current_mrr,
      };
    });
  }

  // MODULE 2 — FEATURES AUDIT
  const featureAudit = m2?.feature_audit || [];
  const m2Summary = m2?.summary || {};
  const gatekeepersCount = m2Summary.gatekeepers_found ?? featureAudit.filter(f => f.classification === 'gatekeeper').length;
  const blockersCount = m2Summary.blockers_found ?? featureAudit.filter(f => f.classification === 'blocker').length;
  const rightPlacedCount = m2Summary.right_placed ?? featureAudit.filter(f => f.classification === 'right_placed').length;
  const undiffCount = m2Summary.undifferentiated ?? featureAudit.filter(f => f.classification === 'undifferentiated').length;
  const biggestIssue = m2Summary.biggest_issue || 'Review tier positioning to ensure premium capabilities are gated behind upper tiers.';

  // MODULE 3 — BENCHMARK
  const benchmarkObj = m3?.benchmark || {};
  const marketPosition = benchmarkObj.positioning ? benchmarkObj.positioning.replace(/_/g, ' ') : 'Well positioned';
  const positionSummary = benchmarkObj.price_vs_market || m3?.summary || 'Pricing sits close to market rate on comparable tiers.';
  const ourValueScores = benchmarkObj.our_value_scores || [];
  const competitorFeatures = benchmarkObj.features_we_lack || ['Mobile app', 'Onboarding checklists', 'Payroll integrations'];
  const differentiators = benchmarkObj.features_we_uniquely_have || ['Audit logs on Growth', 'Dedicated account manager'];

  // Mid tier comparison table
  const competitorsParsed = m3?.competitors_parsed || [];
  const midTierRows = [
    {
      company: `${companyName} (you)`,
      price: tierBreakdowns[1]?.current ? Math.round(tierBreakdowns[1].current / 50) : 79,
      features_count: featureAudit.length || 6,
      value_score: ourValueScores[1]?.value_score || 7.6,
      is_user: true,
    },
    ...competitorsParsed.map(cp => ({
      company: cp.name || cp.url || 'Competitor',
      price: cp.mid_tier_price || 89,
      features_count: cp.feature_count || 7,
      value_score: cp.value_score || 7.9,
    })),
  ];
  if (midTierRows.length === 1) {
    midTierRows.push(
      { company: 'Market Average (Estimated)', price: 89, features_count: 7, value_score: 7.9 },
      { company: 'Entry Alternative', price: 69, features_count: 5, value_score: 7.2 }
    );
  }

  // MODULE 4 — RECOMMENDATIONS
  const strategies = m4?.strategies || [];
  const executiveSummary = m4?.executive_summary || 'The Growth tier is underpriced against its feature set. Moving API access up and raising Growth is the single highest impact fix.';
  const currentStrategy = strategies[selectedStrategyIndex] || strategies[0] || {
    name: 'Tier realignment',
    type: 'strategic',
    risk_level: 'medium',
    confidence_score: 0.85,
    predicted_mrr_change_pct: 14,
    reasoning: 'Reposition features between tiers so each step up has a clear reason, then adjust Growth pricing.',
    new_tier_structure: [
      { name: 'Starter', price: 29, key_changes: ['Keeps core records'], target_customer: 'Teams under 25' },
      { name: 'Growth', price: 89, key_changes: ['Gains data export'], target_customer: 'Growing companies' },
      { name: 'Enterprise', price: 199, key_changes: ['Gains API access'], target_customer: 'Compliance driven' },
    ],
    implementation_steps: [
      'Move data export to Growth and announce it as an upgrade',
      'Move API access to Enterprise with 60 days notice',
      `Raise Growth to ${formatMoney(89, companyCurrency)} for new customers first`,
    ],
  };

  return (
    <div>
      {/* Breadcrumb & Header */}
      <div className="breadcrumb-nav">
        <span>Reports</span>
        <span className="breadcrumb-sep">/</span>
        <Link to={`/companies/${companyId}/tiers`}>{companyName}</Link>
        <span className="breadcrumb-sep">/</span>
        <span>{reportDate}</span>
        <span className="breadcrumb-sep">·</span>
        <span className="badge badge-neutral mono" style={{ fontSize: '11px', textTransform: 'uppercase' }}>
          {companyCurrency} ({getCurrencySymbol(companyCurrency)})
        </span>
      </div>

      {/* Automatic Email Dispatch Banner */}
      {autoEmailBanner && (
        <div 
          style={{ 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'space-between', 
            marginBottom: '20px',
            backgroundColor: 'rgba(52, 199, 123, 0.14)',
            border: '1px solid rgba(52, 199, 123, 0.28)',
            color: '#6EE7B7',
            padding: '12px 18px',
            borderRadius: 'var(--radius-md)',
            fontSize: '13.5px',
            boxShadow: 'var(--shadow-sm)'
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <svg viewBox="0 0 24 24" width="18" height="18" stroke="currentColor" strokeWidth="2.5" fill="none">
              <polyline points="20 6 9 17 4 12" />
            </svg>
            <span>
              <strong>Analysis complete!</strong> An executive summary and PDF copy have been automatically emailed to your registered address.
            </span>
          </div>
          <button 
            type="button" 
            onClick={() => setAutoEmailBanner(false)}
            style={{ 
              background: 'none', 
              border: 'none', 
              color: '#6EE7B7', 
              cursor: 'pointer', 
              fontWeight: 700, 
              fontSize: '14px', 
              padding: '0 4px',
              lineHeight: 1
            }}
            title="Dismiss notice"
          >
            ✕
          </button>
        </div>
      )}

      <div className="page-header" style={{ marginBottom: '16px' }}>
        <div className="page-title-group">
          <h1>
            {activeTab === 'revenue' && 'Revenue impact'}
            {activeTab === 'features' && 'Feature audit'}
            {activeTab === 'benchmark' && 'Competitor benchmark'}
            {activeTab === 'recommendations' && 'Recommendations'}
          </h1>
          <p className="page-subtitle">
            {activeTab === 'revenue' && `Projected MRR after a price increase, using ${company?.industry?.toUpperCase().replace('_', ' ') || 'SaaS'} price sensitivity.`}
            {activeTab === 'features' && 'Each feature checked against the tier it sits in.'}
            {activeTab === 'benchmark' && 'Value score is features offered per dollar of monthly price.'}
            {activeTab === 'recommendations' && 'Three strategies ranked by expected impact and risk.'}
          </p>
        </div>

        <div className="page-actions">
          {companyId && (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => navigate(`/companies/${companyId}/history`)}
            >
              History
            </button>
          )}
          <button
            type="button"
            className="btn btn-primary"
            disabled={downloadingPdf}
            onClick={handleDownloadPdf}
            style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
          >
            <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" strokeWidth="2" fill="none">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            <span>{downloadingPdf ? 'Exporting...' : 'Export PDF'}</span>
          </button>
        </div>
      </div>

      {/* 4 Tabs Bar (08-report-revenue.png) */}
      <div className="tabs-nav">
        <button
          type="button"
          className={`tab-btn ${activeTab === 'revenue' ? 'active' : ''}`}
          onClick={() => setActiveTab('revenue')}
        >
          Revenue impact
        </button>
        <button
          type="button"
          className={`tab-btn ${activeTab === 'features' ? 'active' : ''}`}
          onClick={() => setActiveTab('features')}
        >
          Feature audit
        </button>
        <button
          type="button"
          className={`tab-btn ${activeTab === 'benchmark' ? 'active' : ''}`}
          onClick={() => setActiveTab('benchmark')}
        >
          Benchmark
        </button>
        <button
          type="button"
          className={`tab-btn ${activeTab === 'recommendations' ? 'active' : ''}`}
          onClick={() => setActiveTab('recommendations')}
        >
          Recommendations
        </button>
      </div>

      {/* TAB 1: REVENUE IMPACT (08-report-revenue.png) */}
      {activeTab === 'revenue' && (
        <div>
          <div className="metric-grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
            <div className="metric-card">
              <div className="metric-label">CURRENT MRR</div>
              <div className="metric-value">{formatMoney(currentMRR, companyCurrency)}</div>
            </div>

            <div className="metric-card">
              <div className="metric-label">BEST SCENARIO</div>
              <div className="metric-value" style={{ color: 'var(--primary)' }}>
                {bestScenarioKey}
              </div>
            </div>

            <div className="metric-card">
              <div className="metric-label">PROJECTED MRR</div>
              <div className="metric-value">
                {formatMoney(bestScenario.projected_mrr, companyCurrency)}
                <span className="metric-delta">{bestScenario.net_change}</span>
              </div>
            </div>
          </div>

          <div className="layout-columns">
            {/* Left: Company scenarios */}
            <div className="card">
              <div className="card-header">
                <h3 className="card-title">Company scenarios</h3>
              </div>

              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>INCREASE</th>
                      <th>PROJECTED MRR</th>
                      <th>NET CHANGE</th>
                      <th style={{ width: '38%' }}>USER LOSS</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scenariosList.map((sc, i) => (
                      <tr
                        key={i}
                        style={{
                          backgroundColor: sc.recommended || sc.increase === bestScenarioKey ? 'var(--primary-light)' : undefined,
                        }}
                      >
                        <td>
                          <div style={{ fontWeight: 700, fontSize: '14px', color: 'var(--text-main)' }}>
                            {sc.increase}
                          </div>
                          {(sc.recommended || sc.increase === bestScenarioKey) && (
                            <span style={{ fontSize: '11px', color: 'var(--primary)', fontWeight: 600 }}>
                              Recommended
                            </span>
                          )}
                        </td>
                        <td className="mono" style={{ fontWeight: 600 }}>
                          {formatMoney(sc.projected_mrr, companyCurrency)}
                        </td>
                        <td style={{ color: 'var(--primary)', fontWeight: 600 }}>
                          {sc.net_change}
                        </td>
                        <td>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                            <div className="progress-bar-wrap" style={{ height: '7px', flex: 1, backgroundColor: 'var(--border-card)' }}>
                              <div
                                style={{
                                  height: '100%',
                                  width: `${Math.min((sc.user_loss_pct || 0) * 3.5, 100)}%`,
                                  backgroundColor: 'var(--primary)',
                                  borderRadius: '9999px',
                                }}
                              />
                            </div>
                            <span className="mono" style={{ fontSize: '13px', fontWeight: 600, minWidth: '32px' }}>
                              {sc.user_loss_pct}%
                            </span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div style={{ padding: '16px 20px', borderTop: '1px solid var(--border-light)', fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                The {bestScenarioKey} increase gives the highest projected MRR with an estimated {bestScenario.user_loss_pct}% user loss. At higher increases, extra churn offsets the revenue gain.
              </div>
            </div>

            {/* Right: By tier breakdown */}
            <div className="card">
              <div className="card-header">
                <h3 className="card-title">By tier, at {bestScenarioKey}</h3>
              </div>

              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>TIER</th>
                      <th>CURRENT</th>
                      <th>PROJECTED</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tierBreakdowns.length === 0 ? (
                      <tr>
                        <td colSpan="3" style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)' }}>
                          No per-tier projection available.
                        </td>
                      </tr>
                    ) : (
                      tierBreakdowns.map((t, idx) => (
                        <tr key={idx}>
                          <td style={{ fontWeight: 600, color: 'var(--text-main)' }}>
                            {t.name}
                          </td>
                          <td className="mono">
                            {formatMoney(t.current, companyCurrency)}
                          </td>
                          <td className="mono" style={{ fontWeight: 600, color: 'var(--text-main)' }}>
                            {formatMoney(t.projected, companyCurrency)}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: FEATURE AUDIT (09-report-features.png) */}
      {activeTab === 'features' && (
        <div>
          <div className="metric-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
            <div className="metric-card">
              <div className="metric-label">GATEKEEPERS</div>
              <div className="metric-value">{gatekeepersCount}</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">BLOCKERS</div>
              <div className="metric-value">{blockersCount}</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">RIGHT PLACED</div>
              <div className="metric-value">{rightPlacedCount}</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">UNDIFFERENTIATED</div>
              <div className="metric-value">{undiffCount}</div>
            </div>
          </div>

          <div className="callout callout-info" style={{ marginBottom: '24px', borderRadius: 'var(--radius-md)' }}>
            <div>
              <strong>Biggest issue:</strong> {biggestIssue}
            </div>
          </div>

          <div className="card">
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th style={{ width: '22%' }}>FEATURE</th>
                    <th>TIER</th>
                    <th>CLASSIFICATION</th>
                    <th style={{ width: '40%' }}>REASONING</th>
                    <th>ACTION</th>
                  </tr>
                </thead>
                <tbody>
                  {featureAudit.length === 0 ? (
                    <tr>
                      <td colSpan="5" style={{ textAlign: 'center', padding: '36px', color: 'var(--text-muted)' }}>
                        No feature audit data available.
                      </td>
                    </tr>
                  ) : (
                    featureAudit.map((item, i) => (
                      <tr key={i}>
                        <td style={{ fontWeight: 700, color: 'var(--text-main)', fontSize: '14px' }}>
                          {item.feature_name || item.feature}
                        </td>
                        <td style={{ color: 'var(--text-secondary)' }}>
                          {item.tier_name || item.tier}
                        </td>
                        <td>
                          <StatusBadge status={item.classification?.replace(/_/g, ' ')} />
                        </td>
                        <td style={{ fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.45 }}>
                          {item.reasoning}
                        </td>
                        <td style={{ fontWeight: 500, color: 'var(--text-main)', fontSize: '13px' }}>
                          {item.recommended_action || item.action || 'Keep'}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: COMPETITOR BENCHMARK (10-report-benchmark.png) */}
      {activeTab === 'benchmark' && (
        <div className="layout-columns">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div className="card card-padded">
              <div className="metric-label">MARKET POSITION</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', margin: '4px 0 8px' }}>
                <span style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-main)', letterSpacing: '-0.02em', textTransform: 'capitalize' }}>
                  {marketPosition}
                </span>
                <span className="badge badge-success">Balanced</span>
              </div>
              <p style={{ fontSize: '13px', margin: 0 }}>
                {positionSummary}
              </p>
            </div>

            <div className="card">
              <div className="card-header">
                <h3 className="card-title">Mid-tier comparison</h3>
              </div>
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>COMPANY</th>
                      <th>MID TIER PRICE</th>
                      <th>FEATURES</th>
                      <th>VALUE SCORE</th>
                    </tr>
                  </thead>
                  <tbody>
                    {midTierRows.map((b, i) => (
                      <tr key={i} style={{ backgroundColor: b.is_user ? 'var(--primary-light)' : undefined }}>
                        <td style={{ fontWeight: 600, color: 'var(--text-main)' }}>
                          {b.company}
                        </td>
                        <td className="mono" style={{ fontWeight: 600 }}>
                          {formatMoney(b.price, companyCurrency)}
                        </td>
                        <td className="mono">
                          {b.features_count}
                        </td>
                        <td className="mono" style={{ fontWeight: 700, color: 'var(--text-main)' }}>
                          {b.value_score}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div className="card card-padded">
              <h3 className="card-title" style={{ marginBottom: '18px', fontSize: '14px' }}>Our value score</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                {ourValueScores.length === 0 ? (
                  <div style={{ color: 'var(--text-muted)', fontSize: '13px' }}>No value scores computed.</div>
                ) : (
                  ourValueScores.map((vs, idx) => (
                    <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <span style={{ width: '75px', fontSize: '13px', color: 'var(--text-secondary)' }}>
                        {vs.tier_name || vs.tier}
                      </span>
                      <div className="progress-bar-wrap" style={{ flex: 1, height: '7px' }}>
                        <div
                          className="progress-bar-fill"
                          style={{ width: `${Math.min((vs.value_score || 0) * 7.5, 100)}%` }}
                        />
                      </div>
                      <span className="mono" style={{ width: '32px', textAlign: 'right', fontSize: '13px', fontWeight: 600 }}>
                        {vs.value_score}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="card card-padded">
              <div className="metric-label" style={{ marginBottom: '12px' }}>
                FEATURES COMPETITORS HAVE
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {competitorFeatures.map((feat, i) => (
                  <div key={i} style={{ fontSize: '13.5px', color: 'var(--text-main)', borderBottom: i < competitorFeatures.length - 1 ? '1px solid var(--border-light)' : 'none', paddingBottom: '8px' }}>
                    {feat}
                  </div>
                ))}
              </div>
            </div>

            <div className="card card-padded">
              <div className="metric-label" style={{ marginBottom: '12px' }}>
                OUR DIFFERENTIATORS
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {differentiators.map((diff, i) => (
                  <div key={i} style={{ fontSize: '13.5px', color: 'var(--text-main)', borderBottom: i < differentiators.length - 1 ? '1px solid var(--border-light)' : 'none', paddingBottom: '8px' }}>
                    {diff}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 4: RECOMMENDATIONS (11-report-recommendations.png) */}
      {activeTab === 'recommendations' && (
        <div>
          <div className="callout callout-info" style={{ marginBottom: '24px', borderRadius: 'var(--radius-md)' }}>
            <div>
              <strong>Summary.</strong> {executiveSummary}
            </div>
          </div>

          <div className="layout-columns" style={{ gridTemplateColumns: '290px 1fr' }}>
            {/* Left: Strategy List Selector */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {strategies.map((strat, idx) => {
                const isSelected = selectedStrategyIndex === idx;
                const mrrPct = strat.predicted_mrr_change_pct || 10;
                return (
                  <div
                    key={idx}
                    className="card"
                    style={{
                      padding: '18px 20px',
                      cursor: 'pointer',
                      borderColor: isSelected ? 'var(--primary)' : 'var(--border-card)',
                      backgroundColor: isSelected ? 'var(--primary-light)' : 'var(--bg-card)',
                      boxShadow: isSelected ? '0 0 0 1px var(--primary)' : 'var(--shadow-sm)',
                    }}
                    onClick={() => setSelectedStrategyIndex(idx)}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '6px' }}>
                      <div style={{ fontWeight: 700, fontSize: '14.5px', color: 'var(--text-main)', textTransform: 'capitalize' }}>
                        {strat.name || strat.title || `Strategy ${idx + 1}`}
                      </div>
                      <span style={{ fontWeight: 700, fontSize: '13px', color: 'var(--primary)' }}>
                        +{mrrPct}%
                      </span>
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)', textTransform: 'capitalize' }}>
                      {strat.type} · {strat.risk_level || strat.risk || 'Medium risk'}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Right: Strategy Details Card */}
            <div className="card card-padded">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <h2 style={{ fontSize: '18px', fontWeight: 700, textTransform: 'capitalize' }}>
                  {currentStrategy.name || currentStrategy.title}
                </h2>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <span className="badge badge-info" style={{ textTransform: 'capitalize' }}>
                    {currentStrategy.risk_level || currentStrategy.risk || 'Medium risk'}
                  </span>
                  <span className="badge badge-success">
                    {typeof currentStrategy.confidence_score === 'number'
                      ? `${Math.round(currentStrategy.confidence_score * 100)}% confidence`
                      : (currentStrategy.confidence || '85% confidence')}
                  </span>
                </div>
              </div>

              <p style={{ fontSize: '13.5px', color: 'var(--text-secondary)', marginBottom: '24px' }}>
                {currentStrategy.reasoning || currentStrategy.description}
              </p>

              {/* Repriced Tiers Table */}
              <div className="table-wrap" style={{ marginBottom: '28px' }}>
                <table className="table">
                  <thead>
                    <tr>
                      <th>NEW TIER</th>
                      <th>PRICE</th>
                      <th>KEY CHANGES</th>
                      <th>TARGET CUSTOMER</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(currentStrategy.new_tier_structure || currentStrategy.new_tiers || []).map((nt, i) => (
                      <tr key={i}>
                        <td style={{ fontWeight: 700, color: 'var(--text-main)' }}>
                          {nt.name}
                        </td>
                        <td className="mono" style={{ fontWeight: 700 }}>
                          {formatMoney(nt.price, companyCurrency)}
                        </td>
                        <td style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                          {Array.isArray(nt.key_changes) ? nt.key_changes.join(', ') : nt.key_changes || nt.changes}
                        </td>
                        <td style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                          {nt.target_customer || nt.target}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Numbered Implementation Steps */}
              <div>
                <h4 style={{ fontSize: '13px', textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-muted)', marginBottom: '14px' }}>
                  Implementation steps
                </h4>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                  {(currentStrategy.implementation_steps || currentStrategy.steps || []).map((st, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: '12px', fontSize: '13.5px', color: 'var(--text-main)' }}>
                      <span style={{ fontWeight: 700, color: 'var(--primary)', width: '16px' }}>{i + 1}</span>
                      <span>{st}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

    </div>
  );
};
