import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link, useOutletContext } from 'react-router-dom';
import { companiesApi } from '../api/companies';
import { tiersApi } from '../api/tiers';
import { getIndustryFeatures } from '../data/industryFeatures';
import { formatMoney, getCurrencySymbol } from '../utils/currency';

export const PricingTiers = () => {
  const { companyId } = useParams();
  const navigate = useNavigate();
  const { company, setCompany, counts, setCounts } = useOutletContext();

  const [loading, setLoading] = useState(!company);
  const [selectedTierId, setSelectedTierId] = useState(null);
  const [bulkFeaturesText, setBulkFeaturesText] = useState('');
  const [addingFeatures, setAddingFeatures] = useState(false);
  const [suggestedFeatures, setSuggestedFeatures] = useState([]);
  const [showAddTierModal, setShowAddTierModal] = useState(false);
  const [newTier, setNewTier] = useState({
    name: '',
    price: '',
    billing_cycle: 'monthly',
    user_count: '',
    churn_rate: '',
  });
  const [error, setError] = useState('');

  const loadCompanyData = async () => {
    try {
      setLoading(true);
      const data = await companiesApi.get(companyId);
      setCompany(data);
      if (data.tiers && data.tiers.length > 0 && !selectedTierId) {
        setSelectedTierId(data.tiers[0].id);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load company tiers.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCompanyData();
  }, [companyId]);

  // Load feature suggestions
  useEffect(() => {
    if (company && selectedTierId) {
      companiesApi.suggestFeatures(company.id, selectedTierId)
        .then((res) => {
          if (res?.suggestions?.length > 0) {
            setSuggestedFeatures(res.suggestions);
          } else {
            const fallback = getIndustryFeatures(company.industry);
            setSuggestedFeatures(fallback.slice(0, 5));
          }
        })
        .catch(() => {
          const fallback = getIndustryFeatures(company.industry);
          setSuggestedFeatures(fallback.slice(0, 5));
        });
    }
  }, [company, selectedTierId]);

  const handleDuplicate = async () => {
    try {
      const dup = await companiesApi.duplicate(companyId);
      navigate(`/companies/${dup.id}/tiers`);
    } catch (err) {
      alert('Failed to duplicate company: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleAddTier = async (e) => {
    e.preventDefault();
    try {
      await tiersApi.addTier(companyId, {
        name: newTier.name,
        price: parseFloat(newTier.price) || 0,
        billing_cycle: newTier.billing_cycle,
        user_count: parseInt(newTier.user_count, 10) || 0,
        churn_rate: newTier.churn_rate ? parseFloat(newTier.churn_rate) / 100 : null,
      });
      setShowAddTierModal(false);
      setNewTier({ name: '', price: '', billing_cycle: 'monthly', user_count: '', churn_rate: '' });
      await loadCompanyData();
    } catch (err) {
      alert('Failed to add tier: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleDeleteTier = async (tierId) => {
    if (window.confirm('Delete this tier and all its features?')) {
      try {
        await tiersApi.deleteTier(companyId, tierId);
        await loadCompanyData();
      } catch (err) {
        alert('Failed to delete tier: ' + (err.response?.data?.detail || err.message));
      }
    }
  };

  const handleAddBulkFeatures = async (e) => {
    e.preventDefault();
    if (!selectedTierId || !bulkFeaturesText.trim()) return;

    const list = bulkFeaturesText
      .split('\n')
      .map(s => s.trim())
      .filter(Boolean);

    setAddingFeatures(true);
    try {
      await companiesApi.bulkAddFeatures(companyId, selectedTierId, list);
      setBulkFeaturesText('');
      await loadCompanyData();
    } catch (err) {
      alert('Failed to add features: ' + (err.response?.data?.detail || err.message));
    } finally {
      setAddingFeatures(false);
    }
  };

  const handleAddSingleSuggestedFeature = async (featureName) => {
    if (!selectedTierId) return;
    try {
      await companiesApi.bulkAddFeatures(companyId, selectedTierId, [featureName]);
      setSuggestedFeatures(prev => prev.filter(f => f !== featureName));
      await loadCompanyData();
    } catch (err) {
      alert('Failed to add feature: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleDeleteFeature = async (tierId, featureId) => {
    try {
      await tiersApi.deleteFeature(companyId, tierId, featureId);
      await loadCompanyData();
    } catch (err) {
      alert('Failed to delete feature: ' + (err.response?.data?.detail || err.message));
    }
  };

  if (loading && !company) {
    return <div style={{ padding: '40px', color: 'var(--text-muted)' }}>Loading pricing tiers...</div>;
  }

  const tiers = company?.tiers || [];

  // Metrics calculations (05-pricing-tiers.png)
  let currentMRR = 0;
  let totalSubscribers = 0;
  let totalFeaturesCount = 0;
  const churnList = [];

  tiers.forEach((t) => {
    const users = t.user_count || 0;
    const price = t.price || 0;
    const monthlyPrice = t.billing_cycle === 'annual' ? price / 12 : price;
    currentMRR += monthlyPrice * users;
    totalSubscribers += users;
    totalFeaturesCount += t.features?.length || 0;
    if (t.churn_rate !== null && t.churn_rate !== undefined) {
      churnList.push(`${t.name} ${(t.churn_rate * 100).toFixed(1)}%`);
    }
  });

  const blendedARPU = totalSubscribers > 0 ? (currentMRR / totalSubscribers).toFixed(1) : '0.0';

  const selectedTier = tiers.find(t => t.id === selectedTierId) || tiers[0];

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
          <h1>Pricing tiers</h1>
          <p className="page-subtitle">
            {company?.name} · {company?.industry?.toUpperCase().replace('_', ' ')} · {company?.currency || 'USD'}
          </p>
        </div>

        <div className="page-actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={handleDuplicate}
          >
            Duplicate
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => navigate(`/companies/${companyId}/analysis`)}
          >
            Run analysis
          </button>
        </div>
      </div>

      {error && <div className="callout callout-warning">{error}</div>}

      {/* 4 Metric Cards (05-pricing-tiers.png) */}
      <div className="metric-grid">
        <div className="metric-card">
          <div className="metric-label">CURRENT MRR</div>
          <div className="metric-value">{formatMoney(currentMRR, company?.currency)}</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">SUBSCRIBERS</div>
          <div className="metric-value">{totalSubscribers.toLocaleString()}</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">BLENDED ARPU</div>
          <div className="metric-value">{formatMoney(blendedARPU, company?.currency)}</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">FEATURES TRACKED</div>
          <div className="metric-value">{totalFeaturesCount}</div>
        </div>
      </div>

      {/* Two Column Layout (05-pricing-tiers.png) */}
      <div className="layout-columns">
        {/* Left Column: Tiers and Features Table */}
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">Tiers and features</h3>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => setShowAddTierModal(true)}
            >
              Add tier
            </button>
          </div>

          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>TIER</th>
                  <th>PRICE / MO</th>
                  <th>USERS</th>
                  <th>MRR</th>
                  <th style={{ width: '42%' }}>FEATURES</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {tiers.length === 0 ? (
                  <tr>
                    <td colSpan="6" style={{ textAlign: 'center', padding: '36px', color: 'var(--text-muted)' }}>
                      No pricing tiers configured. Click "Add tier" to get started.
                    </td>
                  </tr>
                ) : (
                  tiers.map((t) => {
                    const priceMo = t.billing_cycle === 'annual' ? (t.price / 12) : t.price;
                    const tierMRR = Math.round(priceMo * (t.user_count || 0));

                    return (
                      <tr
                        key={t.id}
                        style={{
                          backgroundColor: selectedTierId === t.id ? 'var(--bg-hover)' : undefined,
                        }}
                      >
                        <td>
                          <div style={{ fontWeight: 700, color: 'var(--text-main)', fontSize: '14px' }}>
                            {t.name}
                          </div>
                          {t.billing_cycle === 'annual' && (
                            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Billed annually</span>
                          )}
                        </td>
                        <td className="mono" style={{ fontWeight: 600 }}>
                          {formatMoney(priceMo, company?.currency)}
                        </td>
                        <td className="mono">
                          {t.user_count?.toLocaleString() || 0}
                        </td>
                        <td className="mono" style={{ fontWeight: 600 }}>
                          {formatMoney(tierMRR, company?.currency)}
                        </td>
                        <td>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px' }}>
                            {t.features && t.features.length > 0 ? (
                              t.features.map((feat) => (
                                <span
                                  key={feat.id}
                                  style={{
                                    display: 'inline-flex',
                                    alignItems: 'center',
                                    gap: '4px',
                                    fontSize: '12px',
                                    padding: '2px 7px',
                                    borderRadius: 'var(--radius-sm)',
                                    backgroundColor: 'var(--bg-inset)',
                                    color: 'var(--text-body)',
                                  }}
                                >
                                  {feat.feature_name}
                                  <button
                                    type="button"
                                    onClick={() => handleDeleteFeature(t.id, feat.id)}
                                    style={{ color: 'var(--text-muted)', fontSize: '11px' }}
                                    title="Delete feature"
                                  >
                                    ✕
                                  </button>
                                </span>
                              ))
                            ) : (
                              <span style={{ color: 'var(--text-muted)', fontSize: '12px', fontStyle: 'italic' }}>
                                No features listed
                              </span>
                            )}
                          </div>
                        </td>
                        <td style={{ textAlign: 'right' }}>
                          <button
                            type="button"
                            className="btn-ghost"
                            style={{ color: 'var(--danger-text)', padding: '4px 8px' }}
                            onClick={() => handleDeleteTier(t.id)}
                            title="Delete tier"
                          >
                            ✕
                          </button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {churnList.length > 0 && (
            <div style={{ padding: '14px 20px', borderTop: '1px solid var(--border-light)', fontSize: '12.5px', color: 'var(--text-muted)' }}>
              Churn: {churnList.join(' · ')}
            </div>
          )}
        </div>

        {/* Right Column: Add features & Industry suggestions (05-pricing-tiers.png) */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Add Features Box */}
          <div className="card card-padded">
            <h3 className="card-title" style={{ marginBottom: '4px' }}>Add features</h3>
            <p style={{ fontSize: '12.5px', marginBottom: '14px' }}>
              Add to{' '}
              <select
                className="form-select"
                style={{ display: 'inline-block', width: 'auto', padding: '3px 8px', fontSize: '12px', marginLeft: '4px' }}
                value={selectedTierId || ''}
                onChange={(e) => setSelectedTierId(e.target.value)}
              >
                {tiers.map(t => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
              , one per line.
            </p>

            <form onSubmit={handleAddBulkFeatures}>
              <div className="form-group" style={{ marginBottom: '14px' }}>
                <textarea
                  className="form-textarea"
                  style={{ minHeight: '85px', fontSize: '13px' }}
                  placeholder="Webhook support&#10;Role-based access control&#10;Audit logs"
                  value={bulkFeaturesText}
                  onChange={(e) => setBulkFeaturesText(e.target.value)}
                />
              </div>

              <button
                type="submit"
                className="btn btn-secondary"
                disabled={addingFeatures || !bulkFeaturesText.trim()}
                style={{ width: '100%', fontSize: '13px' }}
              >
                {addingFeatures ? 'Adding...' : 'Add features'}
              </button>
            </form>
          </div>

          {/* Industry Suggestions Card */}
          <div className="card card-padded">
            <h3 className="card-title" style={{ marginBottom: '14px', fontSize: '14px' }}>
              Suggested for {company?.industry?.toUpperCase().replace('_', ' ') || 'SaaS'}
            </h3>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {suggestedFeatures.map((feat, i) => (
                <div
                  key={i}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '8px 10px',
                    borderRadius: 'var(--radius-sm)',
                    backgroundColor: 'var(--bg-subtle)',
                    fontSize: '13px',
                  }}
                >
                  <span style={{ color: 'var(--text-main)' }}>{feat}</span>
                  <button
                    type="button"
                    style={{ color: 'var(--primary)', fontWeight: 600, fontSize: '12px' }}
                    onClick={() => handleAddSingleSuggestedFeature(feat)}
                  >
                    Add
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Add Tier Modal */}
      {showAddTierModal && (
        <div className="modal-backdrop" onClick={() => setShowAddTierModal(false)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="card-header">
              <h3 className="card-title">Add Pricing Tier</h3>
              <button className="btn-ghost" onClick={() => setShowAddTierModal(false)}>✕</button>
            </div>

            <form onSubmit={handleAddTier}>
              <div className="card-padded" style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                <div className="form-group">
                  <label className="form-label">Tier Name</label>
                  <input
                    type="text"
                    required
                    className="form-input"
                    placeholder="e.g. Pro, Scale, Enterprise"
                    value={newTier.name}
                    onChange={(e) => setNewTier({ ...newTier, name: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Price ({company?.currency || 'USD'} · {getCurrencySymbol(company?.currency)})</label>
                  <input
                    type="number"
                    step="any"
                    required
                    className="form-input mono"
                    placeholder="49"
                    value={newTier.price}
                    onChange={(e) => setNewTier({ ...newTier, price: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Billing Cycle</label>
                  <select
                    className="form-select"
                    value={newTier.billing_cycle}
                    onChange={(e) => setNewTier({ ...newTier, billing_cycle: e.target.value })}
                  >
                    <option value="monthly">Monthly</option>
                    <option value="annual">Annual</option>
                  </select>
                </div>

                <div className="form-group">
                  <label className="form-label">Active Users / Subscribers</label>
                  <input
                    type="number"
                    className="form-input mono"
                    placeholder="100"
                    value={newTier.user_count}
                    onChange={(e) => setNewTier({ ...newTier, user_count: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Monthly Churn Rate (%)</label>
                  <input
                    type="number"
                    step="0.1"
                    className="form-input mono"
                    placeholder="3.5"
                    value={newTier.churn_rate}
                    onChange={(e) => setNewTier({ ...newTier, churn_rate: e.target.value })}
                  />
                </div>
              </div>

              <div style={{ padding: '14px 24px', backgroundColor: 'var(--bg-subtle)', borderTop: '1px solid var(--border-light)', display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowAddTierModal(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  Save tier
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
