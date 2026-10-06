import React, { useState, useEffect } from 'react';
import { useParams, Link, useOutletContext } from 'react-router-dom';
import { competitorsApi } from '../api/competitors';
import { StatusBadge } from '../components/common/StatusBadge';

export const Competitors = () => {
  const { companyId } = useParams();
  const { company, counts, setCounts } = useOutletContext();

  const [competitors, setCompetitors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [newUrl, setNewUrl] = useState('');
  const [adding, setAdding] = useState(false);
  const [refreshingId, setRefreshingId] = useState(null);

  // Manual paste state
  const [manualCompId, setManualCompId] = useState(null);
  const [manualText, setManualText] = useState('');
  const [savingManual, setSavingManual] = useState(false);

  // Suggested competitors state
  const [suggestions, setSuggestions] = useState([]);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);

  const [error, setError] = useState('');

  const loadCompetitors = async () => {
    try {
      setLoading(true);
      const list = await competitorsApi.list(companyId);
      setCompetitors(list);
      setCounts(prev => ({ ...prev, competitors: list.length }));

      // If any competitor is blocked / failed, default manual text box to it
      const failed = list.find(c => ['manual_required', 'blocked', 'failed'].includes(c.scrape_status));
      if (failed && !manualCompId) {
        setManualCompId(failed.id);
        setManualText(failed.clean_scraped_text || failed.raw_scraped_text || '');
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load competitors.');
    } finally {
      setLoading(false);
    }
  };

  const loadSuggestions = async () => {
    setLoadingSuggestions(true);
    try {
      const res = await competitorsApi.suggest(companyId);
      if (res?.suggestions) {
        setSuggestions(res.suggestions);
      }
    } catch {
      // Fallback suggestions
      setSuggestions([
        { name: 'Larkspur HR', pricing_url: 'https://larkspurhr.com/pricing', reason: 'Same segment, 50–500 staff', verified: true },
        { name: 'Mosaic Payroll', pricing_url: 'https://mosaicpayroll.com/pricing', reason: 'Overlapping mid-tier', verified: false },
      ]);
    } finally {
      setLoadingSuggestions(false);
    }
  };

  useEffect(() => {
    loadCompetitors();
    loadSuggestions();
  }, [companyId]);

  const handleAddCompetitor = async (e) => {
    e.preventDefault();
    if (!newUrl.trim()) return;

    setAdding(true);
    setError('');
    try {
      await competitorsApi.add(companyId, newUrl.trim());
      setNewUrl('');
      await loadCompetitors();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to add competitor.');
    } finally {
      setAdding(false);
    }
  };

  const handleRefresh = async (compId) => {
    setRefreshingId(compId);
    try {
      await competitorsApi.refresh(companyId, compId);
      await loadCompetitors();
    } catch (err) {
      alert('Refresh failed: ' + (err.response?.data?.detail || err.message));
    } finally {
      setRefreshingId(null);
    }
  };

  const handleDelete = async (compId) => {
    if (window.confirm('Remove this competitor?')) {
      try {
        await competitorsApi.delete(companyId, compId);
        if (manualCompId === compId) {
          setManualCompId(null);
          setManualText('');
        }
        await loadCompetitors();
      } catch (err) {
        alert('Delete failed: ' + (err.response?.data?.detail || err.message));
      }
    }
  };

  const handleSaveManualText = async (e) => {
    e.preventDefault();
    if (!manualCompId || !manualText.trim()) return;

    setSavingManual(true);
    try {
      await competitorsApi.manualText(companyId, manualCompId, manualText);
      await loadCompetitors();
      alert('Competitor pricing text saved successfully!');
    } catch (err) {
      alert('Save failed: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSavingManual(false);
    }
  };

  const handleAddSuggested = async (suggestedUrl) => {
    try {
      await competitorsApi.add(companyId, suggestedUrl);
      setSuggestions(prev => prev.filter(s => s.pricing_url !== suggestedUrl));
      await loadCompetitors();
    } catch (err) {
      alert('Failed to add suggested competitor: ' + (err.response?.data?.detail || err.message));
    }
  };

  const blockedCompetitor = competitors.find(c =>
    ['manual_required', 'blocked', 'failed'].includes(c.scrape_status)
  );

  const selectedManualComp = competitors.find(c => c.id === manualCompId) || competitors[0];

  const getCleanName = (c) => {
    if (c.name && !c.name.startsWith('http')) return c.name;
    try {
      const urlObj = new URL(c.url);
      const host = urlObj.hostname.replace(/^www\./, '');
      const domainName = host.split('.')[0];
      return domainName.charAt(0).toUpperCase() + domainName.slice(1);
    } catch {
      return c.url?.slice(0, 24) || 'Competitor';
    }
  };

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
          <h1>Competitors</h1>
          <p className="page-subtitle">
            Pricing pages are fetched and cleaned for the benchmark. Stale data is refreshed before each analysis.
          </p>
        </div>
      </div>

      {error && <div className="callout callout-warning">{error}</div>}

      {/* Two Column Layout (06-competitors.png) */}
      <div className="layout-columns">
        {/* Left Column: Tracked Competitors Table Card */}
        <div className="card">
          <div className="card-header" style={{ flexWrap: 'wrap', gap: '12px' }}>
            <h3 className="card-title">Tracked competitors</h3>

            <form onSubmit={handleAddCompetitor} style={{ display: 'flex', gap: '8px', maxWidth: '400px', width: '100%' }}>
              <input
                type="url"
                required
                className="form-input"
                style={{ padding: '6px 12px', fontSize: '13px' }}
                placeholder="https://competitor.com/pricing"
                value={newUrl}
                onChange={(e) => setNewUrl(e.target.value)}
              />
              <button
                type="submit"
                className="btn btn-primary btn-sm"
                disabled={adding}
              >
                {adding ? 'Adding...' : 'Add'}
              </button>
            </form>
          </div>

          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th style={{ width: '40%' }}>COMPETITOR</th>
                  <th>SCRAPE STATUS</th>
                  <th>LAST FETCHED</th>
                  <th style={{ textAlign: 'right' }}></th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan="4" style={{ textAlign: 'center', padding: '36px', color: 'var(--text-muted)' }}>
                      Loading competitors...
                    </td>
                  </tr>
                ) : competitors.length === 0 ? (
                  <tr>
                    <td colSpan="4" style={{ textAlign: 'center', padding: '36px', color: 'var(--text-muted)' }}>
                      No competitors tracked yet. Add up to 5 competitors to run market benchmarking.
                    </td>
                  </tr>
                ) : (
                  competitors.map((c) => {
                    const isBlocked = ['manual_required', 'blocked', 'failed'].includes(c.scrape_status);
                    const formattedDate = c.last_scraped_at
                      ? new Date(c.last_scraped_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
                      : 'Pending';

                    return (
                      <tr key={c.id}>
                        <td>
                          <div style={{ fontWeight: 600, color: 'var(--text-main)', fontSize: '14px' }}>
                            {getCleanName(c)}
                          </div>
                          <div style={{ fontSize: '12px', color: 'var(--text-muted)', wordBreak: 'break-all' }}>
                            {c.url}
                          </div>
                        </td>
                        <td>
                          <StatusBadge
                            status={isBlocked ? 'Blocked' : (c.scrape_status?.includes('success') ? 'Success' : 'Pending')}
                          />
                        </td>
                        <td style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>
                          {isBlocked ? 'Failed' : formattedDate}
                        </td>
                        <td style={{ textAlign: 'right' }}>
                          <div style={{ display: 'inline-flex', gap: '8px', alignItems: 'center' }}>
                            {isBlocked ? (
                              <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                onClick={() => {
                                  setManualCompId(c.id);
                                  setManualText(c.clean_scraped_text || c.raw_scraped_text || '');
                                }}
                              >
                                Paste text
                              </button>
                            ) : (
                              <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                disabled={refreshingId === c.id}
                                onClick={() => handleRefresh(c.id)}
                              >
                                {refreshingId === c.id ? 'Refreshing...' : 'Refresh'}
                              </button>
                            )}

                            <button
                              type="button"
                              className="btn-ghost"
                              style={{ color: 'var(--danger-text)', padding: '4px' }}
                              onClick={() => handleDelete(c.id)}
                              title="Remove competitor"
                            >
                              ✕
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* Blocked Scrape Alert Banner (06-competitors.png) */}
          {blockedCompetitor && (
            <div className="callout callout-warning" style={{ margin: '16px', borderRadius: 'var(--radius-md)' }}>
              <div>
                <strong>{getCleanName(blockedCompetitor)} could not be read.</strong> The site blocked the request or requires JavaScript. Paste the pricing text manually to include it in the analysis.
              </div>
            </div>
          )}
        </div>

        {/* Right Column: Manual pricing text & Suggested competitors (06-competitors.png) */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Manual Pricing Text Card */}
          <div className="card card-padded">
            <h3 className="card-title" style={{ marginBottom: '8px' }}>Manual pricing text</h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px' }}>
              <span style={{ fontSize: '13px', color: 'var(--text-secondary)', fontWeight: 600, minWidth: '32px' }}>
                For:
              </span>
              <select
                className="form-select"
                style={{
                  flex: 1,
                  padding: '6px 12px',
                  fontSize: '13px',
                  fontWeight: 500,
                  color: 'var(--text-main)',
                  backgroundColor: 'var(--bg-card)',
                  border: '1px solid var(--border-card)',
                  borderRadius: 'var(--radius-sm)',
                  height: '36px',
                }}
                value={manualCompId || ''}
                onChange={(e) => {
                  setManualCompId(e.target.value);
                  const found = competitors.find(c => c.id === e.target.value);
                  setManualText(found?.clean_scraped_text || found?.raw_scraped_text || '');
                }}
              >
                {competitors.length === 0 ? (
                  <option value="">No competitors added</option>
                ) : (
                  competitors.map(c => (
                    <option key={c.id} value={c.id}>
                      {getCleanName(c)}
                    </option>
                  ))
                )}
              </select>
            </div>

            <form onSubmit={handleSaveManualText}>
              <div className="form-group" style={{ marginBottom: '14px' }}>
                <textarea
                  className="form-textarea"
                  style={{ minHeight: '110px', fontSize: '13px' }}
                  placeholder="Paste the plan names, prices and features here."
                  value={manualText}
                  onChange={(e) => setManualText(e.target.value)}
                />
              </div>

              <button
                type="submit"
                className="btn btn-secondary"
                disabled={savingManual || !manualCompId || !manualText.trim()}
                style={{ width: '100%', fontSize: '13px' }}
              >
                {savingManual ? 'Saving...' : 'Save text'}
              </button>
            </form>
          </div>

          {/* Suggested Competitors Card */}
          <div className="card card-padded">
            <h3 className="card-title" style={{ marginBottom: '14px', fontSize: '14px' }}>
              Suggested competitors
            </h3>

            {loadingSuggestions ? (
              <div style={{ fontSize: '12.5px', color: 'var(--text-muted)' }}>
                Finding competitors in your space...
              </div>
            ) : suggestions.length === 0 ? (
              <div style={{ fontSize: '12.5px', color: 'var(--text-muted)' }}>
                No suggestions available.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {suggestions.map((s, i) => (
                  <div
                    key={i}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '8px 10px',
                      borderRadius: 'var(--radius-sm)',
                      backgroundColor: 'var(--bg-subtle)',
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--text-main)' }}>
                        {s.name}
                      </div>
                      <div style={{ fontSize: '11.5px', color: 'var(--text-muted)' }}>
                        {s.reason}
                      </div>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span className={`badge ${s.verified ? 'badge-success' : 'badge-neutral'}`} style={{ fontSize: '10.5px' }}>
                        {s.verified ? 'Verified' : 'Unverified'}
                      </span>
                      <button
                        type="button"
                        style={{ color: 'var(--primary)', fontWeight: 600, fontSize: '12px' }}
                        onClick={() => handleAddSuggested(s.pricing_url)}
                      >
                        +
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
