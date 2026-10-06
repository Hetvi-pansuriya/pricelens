import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { setupApi } from '../api/setup';
import { companiesApi } from '../api/companies';
import { tiersApi } from '../api/tiers';
import { competitorsApi } from '../api/competitors';
import { StatusBadge } from '../components/common/StatusBadge';
import { getCurrencySymbol, SUPPORTED_CURRENCIES } from '../utils/currency';

export const CompanySetup = () => {
  const navigate = useNavigate();

  // Wizard Step: 1 = Source, 2 = Review tiers, 3 = Competitors
  const [step, setStep] = useState(1);

  // Source selection: 'url' | 'text' | 'csv' | 'stripe' | 'manual'
  const [sourceType, setSourceType] = useState('url');

  // Form inputs
  const [url, setUrl] = useState('');
  const [text, setText] = useState('');
  const [csvFile, setCsvFile] = useState(null);
  const [stripeKey, setStripeKey] = useState('');
  const [companyName, setCompanyName] = useState('');
  const [industry, setIndustry] = useState('saas_b2b');
  const [currency, setCurrency] = useState('USD');
  const [description, setDescription] = useState('');

  // Extracted / Draft Data
  const [draftTiers, setDraftTiers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [warningMessage, setWarningMessage] = useState('');

  // Step 3 Competitors
  const [createdCompanyId, setCreatedCompanyId] = useState(null);
  const [competitorUrls, setCompetitorUrls] = useState(['']);

  // Handle Step 1 Submit
  const handleExtractSource = async (e) => {
    e.preventDefault();
    setError('');
    setWarningMessage('');
    setLoading(true);

    try {
      if (sourceType === 'url') {
        const res = await setupApi.importFromUrl(url);
        setCompanyName(res.company_name || companyName || 'My Product');
        setIndustry(res.industry || industry);
        if (res.currency) setCurrency(res.currency);
        setDescription(res.description || '');
        setDraftTiers(res.tiers || []);

        const unconfirmed = (res.tiers || []).filter(t => !t.verified_price);
        if (unconfirmed.length > 0) {
          setWarningMessage(
            `${unconfirmed.length} price needs confirmation. The ${unconfirmed.map(t => t.name).join(', ')} price was not found on the page text. Enter it or mark it as custom pricing.`
          );
        }
        setStep(2);
      } else if (sourceType === 'text') {
        const res = await setupApi.importFromText(text);
        setCompanyName(res.company_name || companyName || 'My Product');
        setIndustry(res.industry || industry);
        if (res.currency) setCurrency(res.currency);
        setDescription(res.description || '');
        setDraftTiers(res.tiers || []);
        setStep(2);
      } else if (sourceType === 'csv') {
        if (!csvFile) {
          setError('Please select a CSV file.');
          setLoading(false);
          return;
        }
        const res = await setupApi.parseCsv(csvFile);
        if (res.errors && res.errors.length > 0) {
          setError(`CSV validation errors: ${res.errors.map(e => e.error).join(', ')}`);
        }
        if (res.detected_currency) {
          setCurrency(res.detected_currency);
        }
        const mapped = (res.rows || []).map(r => ({
          name: r.name,
          price: r.price,
          billing_cycle: r.billing_cycle,
          user_count: r.user_count || 10,
          churn_rate: r.churn_rate ? r.churn_rate * 100 : 3.0,
          features: r.features || [],
          verified_price: true,
        }));
        setDraftTiers(mapped);
        setCompanyName(companyName || 'Imported Company');
        setStep(2);
      } else if (sourceType === 'stripe') {
        const res = await setupApi.importFromStripe(stripeKey);
        setCurrency(res.detected_currency || 'USD');
        setDraftTiers(res.tiers || []);
        setCompanyName(companyName || 'Stripe Connected Company');
        setStep(2);
      } else if (sourceType === 'manual') {
        if (!companyName.trim()) {
          setError('Please provide a company name.');
          setLoading(false);
          return;
        }
        setDraftTiers([
          { name: 'Starter', price: 29, billing_cycle: 'monthly', user_count: 100, churn_rate: 5.0, features: ['User management', 'Basic analytics', 'Email support'], verified_price: true },
          { name: 'Growth', price: 79, billing_cycle: 'monthly', user_count: 50, churn_rate: 3.0, features: ['Everything in Starter', 'API access', 'Priority support'], verified_price: true },
          { name: 'Enterprise', price: 199, billing_cycle: 'annual', user_count: 20, churn_rate: 1.0, features: ['Everything in Growth', 'SSO login', 'Audit logs'], verified_price: true },
        ]);
        setStep(2);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Extraction failed. Please verify your inputs or use manual setup.');
    } finally {
      setLoading(false);
    }
  };

  // Update draft tier inline
  const handleTierChange = (index, field, value) => {
    setDraftTiers(prev => {
      const copy = [...prev];
      copy[index] = { ...copy[index], [field]: value };
      return copy;
    });
  };

  // Step 2 Submit: Save company, tiers, and features to database
  const handleSaveCompany = async () => {
    setLoading(true);
    setError('');

    try {
      // 1. Create company
      const company = await companiesApi.create({
        name: companyName.trim() || 'New SaaS Company',
        industry,
        currency,
        description: description.trim() || undefined,
      });

      setCreatedCompanyId(company.id);

      // 2. Add tiers and features
      for (const t of draftTiers) {
        const priceNum = t.price !== null && t.price !== undefined ? parseFloat(t.price) : 0;
        const userCountNum = t.user_count ? parseInt(t.user_count, 10) : 0;
        const churnNum = t.churn_rate !== null && t.churn_rate !== undefined ? parseFloat(t.churn_rate) / 100 : null;

        const newTier = await tiersApi.addTier(company.id, {
          name: t.name || 'Tier',
          price: priceNum,
          billing_cycle: t.billing_cycle || 'monthly',
          user_count: userCountNum,
          churn_rate: churnNum,
        });

        // Add features if present
        if (t.features && t.features.length > 0) {
          await companiesApi.bulkAddFeatures(company.id, newTier.id, t.features);
        }
      }

      setStep(3);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save company and tiers.');
    } finally {
      setLoading(false);
    }
  };

  // Step 3 Submit: Add competitors and finish
  const handleFinishCompetitors = async () => {
    if (createdCompanyId) {
      for (const u of competitorUrls) {
        if (u && u.trim().startsWith('http')) {
          try {
            await competitorsApi.add(createdCompanyId, u.trim());
          } catch {
            // ignore individual competitor scrape error here
          }
        }
      }
      navigate(`/companies/${createdCompanyId}/tiers`);
    } else {
      navigate('/companies');
    }
  };

  return (
    <div>
      {/* Breadcrumb & Header */}
      <div className="breadcrumb-nav">
        <Link to="/companies">Companies</Link>
        <span className="breadcrumb-sep">/</span>
        <span>New</span>
      </div>

      <div className="page-header" style={{ marginBottom: '16px' }}>
        <div className="page-title-group">
          <h1>
            {step === 1 && 'Set up a company'}
            {step === 2 && 'Review imported tiers'}
            {step === 3 && 'Add competitors (Optional)'}
          </h1>
          <p className="page-subtitle">
            {step === 1 && 'Bring in your pricing the quickest way. You review everything before it is saved.'}
            {step === 2 && 'Edit anything that looks off. Unverified prices are marked so you can confirm them.'}
            {step === 3 && 'Track competitor pricing pages to benchmark your positioning.'}
          </p>
        </div>

        <div className="page-actions">
          {step === 1 && (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setupApi.downloadCsvTemplate()}
            >
              Download CSV template
            </button>
          )}
          {step === 2 && (
            <>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setStep(1)}
              >
                Back
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={loading}
                onClick={handleSaveCompany}
              >
                {loading ? 'Saving company...' : 'Save and continue'}
              </button>
            </>
          )}
          {step === 3 && (
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleFinishCompetitors}
            >
              Finish setup
            </button>
          )}
        </div>
      </div>

      {/* Stepper Progress (03-setup-import.png) */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '28px', fontSize: '13px' }}>
        <span style={{ fontWeight: step === 1 ? 700 : 500, color: step === 1 ? 'var(--primary)' : 'var(--text-secondary)' }}>
          <span style={{ display: 'inline-block', width: '20px', height: '20px', borderRadius: '50%', backgroundColor: step === 1 ? 'var(--primary)' : 'var(--bg-inset)', color: step === 1 ? '#fff' : 'var(--text-secondary)', textAlign: 'center', lineHeight: '20px', marginRight: '6px', fontSize: '11px', fontWeight: 700 }}>1</span>
          Source
        </span>
        <span style={{ color: 'var(--border-strong)' }}>—</span>
        <span style={{ fontWeight: step === 2 ? 700 : 500, color: step === 2 ? 'var(--primary)' : 'var(--text-secondary)' }}>
          <span style={{ display: 'inline-block', width: '20px', height: '20px', borderRadius: '50%', backgroundColor: step === 2 ? 'var(--primary)' : 'var(--bg-inset)', color: step === 2 ? '#fff' : 'var(--text-secondary)', textAlign: 'center', lineHeight: '20px', marginRight: '6px', fontSize: '11px', fontWeight: 700 }}>2</span>
          Review tiers
        </span>
        <span style={{ color: 'var(--border-strong)' }}>—</span>
        <span style={{ fontWeight: step === 3 ? 700 : 500, color: step === 3 ? 'var(--primary)' : 'var(--text-secondary)' }}>
          <span style={{ display: 'inline-block', width: '20px', height: '20px', borderRadius: '50%', backgroundColor: step === 3 ? 'var(--primary)' : 'var(--bg-inset)', color: step === 3 ? '#fff' : 'var(--text-secondary)', textAlign: 'center', lineHeight: '20px', marginRight: '6px', fontSize: '11px', fontWeight: 700 }}>3</span>
          Competitors
        </span>
      </div>

      {error && (
        <div className="callout callout-warning">
          {error}
        </div>
      )}

      {/* STEP 1: SOURCE SELECTION (03-setup-import.png) */}
      {step === 1 && (
        <div className="layout-columns">
          {/* Left Column: Source Selection List */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div
              className="card"
              style={{
                padding: '20px 24px',
                cursor: 'pointer',
                borderColor: sourceType === 'url' ? 'var(--primary)' : 'var(--border-card)',
                backgroundColor: sourceType === 'url' ? 'var(--bg-hover)' : 'var(--bg-card)',
                boxShadow: sourceType === 'url' ? '0 0 0 1px var(--primary)' : 'var(--shadow-sm)',
              }}
              onClick={() => setSourceType('url')}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                <h3 style={{ fontSize: '15px', color: 'var(--text-main)' }}>Import from your pricing page</h3>
                <span className="badge badge-neutral">URL</span>
              </div>
              <p style={{ fontSize: '13px', margin: 0 }}>
                Paste your public pricing URL. Tiers, prices and features are read and price-checked against the page text.
              </p>
            </div>

            <div
              className="card"
              style={{
                padding: '20px 24px',
                cursor: 'pointer',
                borderColor: sourceType === 'text' ? 'var(--primary)' : 'var(--border-card)',
                backgroundColor: sourceType === 'text' ? 'var(--bg-hover)' : 'var(--bg-card)',
                boxShadow: sourceType === 'text' ? '0 0 0 1px var(--primary)' : 'var(--shadow-sm)',
              }}
              onClick={() => setSourceType('text')}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                <h3 style={{ fontSize: '15px', color: 'var(--text-main)' }}>Paste pricing text</h3>
                <span className="badge badge-neutral">Text</span>
              </div>
              <p style={{ fontSize: '13px', margin: 0 }}>
                Copy the text from any pricing document or page.
              </p>
            </div>

            <div
              className="card"
              style={{
                padding: '20px 24px',
                cursor: 'pointer',
                borderColor: sourceType === 'csv' ? 'var(--primary)' : 'var(--border-card)',
                backgroundColor: sourceType === 'csv' ? 'var(--bg-hover)' : 'var(--bg-card)',
                boxShadow: sourceType === 'csv' ? '0 0 0 1px var(--primary)' : 'var(--shadow-sm)',
              }}
              onClick={() => setSourceType('csv')}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                <h3 style={{ fontSize: '15px', color: 'var(--text-main)' }}>Upload a CSV</h3>
                <span className="badge badge-neutral">CSV</span>
              </div>
              <p style={{ fontSize: '13px', margin: 0 }}>
                Use the template with tier, price, billing cycle, users, churn and features.
              </p>
            </div>

            <div
              className="card"
              style={{
                padding: '20px 24px',
                cursor: 'pointer',
                borderColor: sourceType === 'stripe' ? 'var(--primary)' : 'var(--border-card)',
                backgroundColor: sourceType === 'stripe' ? 'var(--bg-hover)' : 'var(--bg-card)',
                boxShadow: sourceType === 'stripe' ? '0 0 0 1px var(--primary)' : 'var(--shadow-sm)',
              }}
              onClick={() => setSourceType('stripe')}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                <h3 style={{ fontSize: '15px', color: 'var(--text-main)' }}>Connect Stripe</h3>
                <span className="badge badge-neutral">Stripe</span>
              </div>
              <p style={{ fontSize: '13px', margin: 0 }}>
                Read active subscription products with a restricted API key.
              </p>
            </div>

            <div
              className="card"
              style={{
                padding: '20px 24px',
                cursor: 'pointer',
                borderColor: sourceType === 'manual' ? 'var(--primary)' : 'var(--border-card)',
                backgroundColor: sourceType === 'manual' ? 'var(--bg-hover)' : 'var(--bg-card)',
                boxShadow: sourceType === 'manual' ? '0 0 0 1px var(--primary)' : 'var(--shadow-sm)',
              }}
              onClick={() => setSourceType('manual')}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                <h3 style={{ fontSize: '15px', color: 'var(--text-main)' }}>Enter manually</h3>
                <span className="badge badge-neutral">Manual</span>
              </div>
              <p style={{ fontSize: '13px', margin: 0 }}>
                Start from a blank company and add tiers yourself.
              </p>
            </div>
          </div>

          {/* Right Column: Source Action Form (03-setup-import.png) */}
          <div className="card card-padded">
            <form onSubmit={handleExtractSource}>
              {sourceType === 'url' && (
                <>
                  <div className="form-group">
                    <label className="form-label" htmlFor="pricing-url">
                      Pricing page URL
                    </label>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px' }}>
                      Only public pages are fetched.
                    </div>
                    <input
                      id="pricing-url"
                      type="url"
                      required
                      className="form-input"
                      placeholder="https://cloudhr.io/pricing"
                      value={url}
                      onChange={(e) => setUrl(e.target.value)}
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label" htmlFor="company-industry">
                      Industry
                    </label>
                    <select
                      id="company-industry"
                      className="form-select"
                      value={industry}
                      onChange={(e) => setIndustry(e.target.value)}
                    >
                      <option value="saas_b2b">SaaS B2B</option>
                      <option value="saas_b2c">SaaS B2C</option>
                      <option value="hr_software">HR Software</option>
                      <option value="project_management">Project Management</option>
                      <option value="analytics">Analytics</option>
                      <option value="crm">CRM</option>
                      <option value="payments">Payments</option>
                      <option value="ecommerce_tools">Ecommerce Tools</option>
                      <option value="other">Other</option>
                    </select>
                  </div>

                  <div className="form-group" style={{ marginBottom: '24px' }}>
                    <label className="form-label" htmlFor="company-currency">
                      Currency
                    </label>
                    <select
                      id="company-currency"
                      className="form-select"
                      value={currency}
                      onChange={(e) => setCurrency(e.target.value)}
                    >
                      {SUPPORTED_CURRENCIES.map(c => (
                        <option key={c.code} value={c.code}>{c.label}</option>
                      ))}
                    </select>
                  </div>

                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={loading}
                    style={{ width: '100%', padding: '11px', marginBottom: '16px' }}
                  >
                    {loading ? 'Reading pricing page...' : 'Read pricing page'}
                  </button>
                </>
              )}

              {sourceType === 'text' && (
                <>
                  <div className="form-group">
                    <label className="form-label" htmlFor="pricing-text">
                      Pasted pricing text
                    </label>
                    <textarea
                      id="pricing-text"
                      required
                      className="form-textarea"
                      style={{ minHeight: '130px' }}
                      placeholder="Paste plan names, prices, features and tiers from your site or document..."
                      value={text}
                      onChange={(e) => setText(e.target.value)}
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Industry</label>
                    <select
                      className="form-select"
                      value={industry}
                      onChange={(e) => setIndustry(e.target.value)}
                    >
                      <option value="saas_b2b">SaaS B2B</option>
                      <option value="saas_b2c">SaaS B2C</option>
                      <option value="hr_software">HR Software</option>
                      <option value="project_management">Project Management</option>
                      <option value="analytics">Analytics</option>
                      <option value="crm">CRM</option>
                      <option value="other">Other</option>
                    </select>
                  </div>

                  <div className="form-group" style={{ marginBottom: '24px' }}>
                    <label className="form-label">Currency</label>
                    <select
                      className="form-select"
                      value={currency}
                      onChange={(e) => setCurrency(e.target.value)}
                    >
                      {SUPPORTED_CURRENCIES.map(c => (
                        <option key={c.code} value={c.code}>{c.label}</option>
                      ))}
                    </select>
                  </div>

                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={loading}
                    style={{ width: '100%', padding: '11px', marginBottom: '16px' }}
                  >
                    {loading ? 'Extracting pricing...' : 'Extract tiers'}
                  </button>
                </>
              )}

              {sourceType === 'csv' && (
                <>
                  <div className="form-group">
                    <label className="form-label">Choose CSV file</label>
                    <input
                      type="file"
                      accept=".csv"
                      required
                      className="form-input"
                      onChange={(e) => setCsvFile(e.target.files[0])}
                    />
                  </div>

                  <div className="form-group" style={{ marginBottom: '24px' }}>
                    <label className="form-label">Fallback Currency</label>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px' }}>
                      Auto-detected if values include ₹, €, £, $, or select here:
                    </div>
                    <select
                      className="form-select"
                      value={currency}
                      onChange={(e) => setCurrency(e.target.value)}
                    >
                      {SUPPORTED_CURRENCIES.map(c => (
                        <option key={c.code} value={c.code}>{c.label}</option>
                      ))}
                    </select>
                  </div>

                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={loading}
                    style={{ width: '100%', padding: '11px', marginBottom: '16px' }}
                  >
                    {loading ? 'Parsing CSV...' : 'Parse & review tiers'}
                  </button>
                </>
              )}

              {sourceType === 'stripe' && (
                <>
                  <div className="form-group">
                    <label className="form-label">Stripe Restricted API Key</label>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px' }}>
                      Key with read-only permissions for Subscriptions & Prices. Never stored.
                    </div>
                    <input
                      type="password"
                      required
                      className="form-input"
                      placeholder="rk_live_..."
                      value={stripeKey}
                      onChange={(e) => setStripeKey(e.target.value)}
                    />
                  </div>

                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={loading}
                    style={{ width: '100%', padding: '11px', marginBottom: '16px' }}
                  >
                    {loading ? 'Connecting Stripe...' : 'Read Stripe plans'}
                  </button>
                </>
              )}

              {sourceType === 'manual' && (
                <>
                  <div className="form-group">
                    <label className="form-label">Company Name</label>
                    <input
                      type="text"
                      required
                      className="form-input"
                      placeholder="e.g. Acme Cloud"
                      value={companyName}
                      onChange={(e) => setCompanyName(e.target.value)}
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Industry</label>
                    <select
                      className="form-select"
                      value={industry}
                      onChange={(e) => setIndustry(e.target.value)}
                    >
                      <option value="saas_b2b">SaaS B2B</option>
                      <option value="saas_b2c">SaaS B2C</option>
                      <option value="hr_software">HR Software</option>
                      <option value="project_management">Project Management</option>
                      <option value="analytics">Analytics</option>
                      <option value="crm">CRM</option>
                      <option value="other">Other</option>
                    </select>
                  </div>

                  <div className="form-group" style={{ marginBottom: '24px' }}>
                    <label className="form-label">Currency</label>
                    <select
                      className="form-select"
                      value={currency}
                      onChange={(e) => setCurrency(e.target.value)}
                    >
                      {SUPPORTED_CURRENCIES.map(c => (
                        <option key={c.code} value={c.code}>{c.label}</option>
                      ))}
                    </select>
                  </div>

                  <button
                    type="submit"
                    className="btn btn-primary"
                    style={{ width: '100%', padding: '11px', marginBottom: '16px' }}
                  >
                    Continue to tiers
                  </button>
                </>
              )}

              <div style={{ fontSize: '12px', color: 'var(--text-muted)', lineHeight: 1.4 }}>
                Industry sets the price-sensitivity model used in the revenue analysis.
              </div>
            </form>
          </div>
        </div>
      )}

      {/* STEP 2: REVIEW IMPORTED TIERS (04-setup-review.png) */}
      {step === 2 && (
        <div>
          {warningMessage && (
            <div className="callout callout-warning">
              <span style={{ fontWeight: 600 }}>{warningMessage}</span>
            </div>
          )}

          <div className="layout-columns">
            {/* Left Column: Detected Tiers Table */}
            <div className="card">
              <div className="card-header">
                <h3 className="card-title">Detected tiers</h3>
              </div>

              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>TIER</th>
                      <th>PRICE ({getCurrencySymbol(currency)})</th>
                      <th>BILLING</th>
                      <th>USERS</th>
                      <th>CHURN</th>
                      <th style={{ width: '35%' }}>FEATURES</th>
                    </tr>
                  </thead>
                  <tbody>
                    {draftTiers.length === 0 ? (
                      <tr>
                        <td colSpan="6" style={{ textAlign: 'center', padding: '32px', color: 'var(--text-muted)' }}>
                          No tiers detected. Click Back to check your source.
                        </td>
                      </tr>
                    ) : (
                      draftTiers.map((t, idx) => (
                        <tr key={idx}>
                          <td>
                            <input
                              type="text"
                              className="form-input"
                              style={{ fontWeight: 600, padding: '6px 8px', fontSize: '13.5px' }}
                              value={t.name}
                              onChange={(e) => handleTierChange(idx, 'name', e.target.value)}
                            />
                          </td>
                          <td>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                              <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-muted)' }}>
                                {getCurrencySymbol(currency)}
                              </span>
                              <input
                                type="number"
                                step="any"
                                className="form-input mono"
                                style={{ width: '80px', padding: '6px 8px', fontSize: '13.5px' }}
                                value={t.price ?? ''}
                                onChange={(e) => handleTierChange(idx, 'price', e.target.value)}
                              />
                              {!t.verified_price && (
                                <span className="badge badge-warning" title="Price unverified on page">
                                  Confirm
                                </span>
                              )}
                            </div>
                          </td>
                          <td>
                            <select
                              className="form-select"
                              style={{ padding: '6px 8px', fontSize: '13px' }}
                              value={t.billing_cycle || 'monthly'}
                              onChange={(e) => handleTierChange(idx, 'billing_cycle', e.target.value)}
                            >
                              <option value="monthly">Monthly</option>
                              <option value="annual">Annual</option>
                            </select>
                          </td>
                          <td>
                            <input
                              type="number"
                              className="form-input mono"
                              style={{ width: '75px', padding: '6px 8px', fontSize: '13.5px' }}
                              placeholder="100"
                              value={t.user_count ?? ''}
                              onChange={(e) => handleTierChange(idx, 'user_count', e.target.value)}
                            />
                          </td>
                          <td>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                              <input
                                type="number"
                                step="0.1"
                                className="form-input mono"
                                style={{ width: '60px', padding: '6px 8px', fontSize: '13.5px' }}
                                placeholder="5.0"
                                value={t.churn_rate ?? ''}
                                onChange={(e) => handleTierChange(idx, 'churn_rate', e.target.value)}
                              />
                              <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>%</span>
                            </div>
                          </td>
                          <td style={{ fontSize: '12.5px', color: 'var(--text-secondary)' }}>
                            {t.features && t.features.length > 0 ? (
                              t.features.join(', ')
                            ) : (
                              <span style={{ fontStyle: 'italic', color: 'var(--text-muted)' }}>No features extracted</span>
                            )}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Right Column: Company Info and Missing Data Cards */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div className="card card-padded">
                <h3 className="card-title" style={{ marginBottom: '16px' }}>Company</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', fontSize: '13.5px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-muted)' }}>Name</span>
                    <span style={{ fontWeight: 600 }}>{companyName || 'CloudHR Pro'}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-muted)' }}>Industry</span>
                    <span style={{ fontWeight: 600 }}>{industry.toUpperCase().replace('_', ' ')}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ color: 'var(--text-muted)' }}>Currency</span>
                    <select
                      className="form-select"
                      style={{ width: 'auto', padding: '3px 8px', fontSize: '12px', fontWeight: 600 }}
                      value={currency}
                      onChange={(e) => setCurrency(e.target.value)}
                    >
                      {SUPPORTED_CURRENCIES.map(c => (
                        <option key={c.code} value={c.code}>{c.label}</option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>

              <div className="card card-padded">
                <h3 className="card-title" style={{ marginBottom: '8px', fontSize: '14.5px' }}>Missing data</h3>
                <p style={{ fontSize: '13px', margin: 0 }}>
                  User counts and churn are needed for revenue scenarios. Fill them in the table for accurate analysis results.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* STEP 3: COMPETITORS */}
      {step === 3 && (
        <div style={{ maxWidth: '640px', margin: '0 auto' }}>
          <div className="card card-padded">
            <h3 className="card-title" style={{ marginBottom: '12px' }}>
              Add competitor pricing pages
            </h3>
            <p style={{ fontSize: '13px', marginBottom: '20px' }}>
              PriceLens will fetch their public pricing to benchmark your value score. You can also skip this and add them later.
            </p>

            {competitorUrls.map((urlVal, i) => (
              <div key={i} className="form-group" style={{ marginBottom: '12px' }}>
                <input
                  type="url"
                  className="form-input"
                  placeholder="https://competitor.com/pricing"
                  value={urlVal}
                  onChange={(e) => {
                    const copy = [...competitorUrls];
                    copy[i] = e.target.value;
                    setCompetitorUrls(copy);
                  }}
                />
              </div>
            ))}

            <button
              type="button"
              className="btn btn-secondary btn-sm"
              style={{ marginBottom: '24px' }}
              onClick={() => setCompetitorUrls([...competitorUrls, ''])}
            >
              + Add another competitor URL
            </button>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => navigate(`/companies/${createdCompanyId}/tiers`)}
              >
                Skip for now
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleFinishCompetitors}
              >
                Save & Go to Dashboard
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
