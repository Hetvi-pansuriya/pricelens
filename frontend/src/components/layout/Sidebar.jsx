import React from 'react';
import { NavLink, useNavigate, useParams, useLocation } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';

export const Sidebar = ({ company, counts, onOpenSettings }) => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const params = useParams();

  // If companyId is in route params or passed as prop
  const activeCompanyId = company?.id || params.companyId;

  return (
    <aside className="app-sidebar">
      <div className="sidebar-top">
        {/* Brand Logo */}
        <div 
          className="brand-logo" 
          style={{ cursor: 'pointer' }} 
          onClick={() => navigate('/companies')}
        >
          <svg className="brand-icon-svg" viewBox="0 0 24 24">
            <circle cx="10" cy="10" r="7" />
            <path d="m21 21-6-6" />
            <circle cx="10" cy="10" r="2.5" fill="var(--primary)" opacity="0.4" />
          </svg>
          <span>PriceLens</span>
        </div>

        {/* Global Navigation */}
        <nav className="sidebar-nav-section">
          <NavLink
            to="/companies"
            end
            className={({ isActive }) =>
              `sidebar-nav-link ${isActive && !activeCompanyId ? 'active' : ''}`
            }
          >
            <span>Companies</span>
          </NavLink>

          {/* Company-specific Context Menu */}
          {activeCompanyId && (
            <div style={{ marginTop: '16px' }}>
              <div className="sidebar-section-title">
                {company?.name || 'COMPANY'}
              </div>

              <NavLink
                to={`/companies/${activeCompanyId}/tiers`}
                className={({ isActive }) =>
                  `sidebar-nav-link ${isActive ? 'active' : ''}`
                }
              >
                <span>Pricing tiers</span>
                {counts?.tiers !== undefined && (
                  <span className="nav-link-badge">{counts.tiers}</span>
                )}
              </NavLink>

              <NavLink
                to={`/companies/${activeCompanyId}/competitors`}
                className={({ isActive }) =>
                  `sidebar-nav-link ${isActive ? 'active' : ''}`
                }
              >
                <span>Competitors</span>
                {counts?.competitors !== undefined && (
                  <span className="nav-link-badge">{counts.competitors}</span>
                )}
              </NavLink>

              <NavLink
                to={`/companies/${activeCompanyId}/analysis`}
                className={({ isActive }) =>
                  `sidebar-nav-link ${isActive ? 'active' : ''}`
                }
              >
                <span>Run analysis</span>
              </NavLink>

              <NavLink
                to={`/companies/${activeCompanyId}/reports`}
                className={({ isActive }) =>
                  `sidebar-nav-link ${isActive || location.pathname.includes('/reports') ? 'active' : ''}`
                }
              >
                <span>Reports</span>
                {counts?.reports !== undefined && counts.reports > 0 && (
                  <span className="nav-link-badge">{counts.reports}</span>
                )}
              </NavLink>

              <NavLink
                to={`/companies/${activeCompanyId}/history`}
                className={({ isActive }) =>
                  `sidebar-nav-link ${isActive ? 'active' : ''}`
                }
              >
                <span>History</span>
              </NavLink>
            </div>
          )}
        </nav>
      </div>

      {/* Sidebar Footer */}
      <div className="sidebar-footer">
        <div className="sidebar-user-row">
          <div className="user-avatar-badge" title={user?.email || 'Account'}>
            <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" strokeWidth="2" fill="none">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
              <circle cx="12" cy="7" r="4" />
            </svg>
          </div>
          <button 
            type="button" 
            className="user-settings-btn"
            onClick={onOpenSettings}
            title="Account settings"
          >
            Account settings
          </button>
        </div>

        <button 
          type="button" 
          className="sidebar-signout-btn"
          onClick={logout}
        >
          <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" strokeWidth="2" fill="none">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
            <polyline points="16 17 21 12 16 7" />
            <line x1="21" y1="12" x2="9" y2="12" />
          </svg>
          <span>Sign out</span>
        </button>
      </div>
    </aside>
  );
};
