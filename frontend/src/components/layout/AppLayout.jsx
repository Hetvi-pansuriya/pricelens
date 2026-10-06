import React, { useState, useEffect } from 'react';
import { Outlet, useParams, useLocation } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { AccountModal } from '../common/AccountModal';
import { companiesApi } from '../../api/companies';
import { analysisApi } from '../../api/analysis';

export const AppLayout = () => {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [company, setCompany] = useState(null);
  const [counts, setCounts] = useState({ tiers: 0, competitors: 0, reports: 0 });
  const { companyId } = useParams();
  const location = useLocation();

  useEffect(() => {
    let isMounted = true;
    if (companyId) {
      companiesApi.get(companyId)
        .then((data) => {
          if (isMounted) {
            setCompany(data);
            const tiersCount = data.tiers?.length || 0;
            const compCount = data.competitors?.length || 0;
            
            // fetch history to know reports count
            analysisApi.history(companyId)
              .then((hist) => {
                if (isMounted) {
                  const reportsCount = (hist || []).filter(h => h.report_id || h.status === 'completed').length;
                  setCounts({ tiers: tiersCount, competitors: compCount, reports: reportsCount });
                }
              })
              .catch(() => {
                if (isMounted) {
                  setCounts({ tiers: tiersCount, competitors: compCount, reports: 0 });
                }
              });
          }
        })
        .catch(() => {
          if (isMounted) setCompany(null);
        });
    } else {
      setCompany(null);
    }
    return () => {
      isMounted = false;
    };
  }, [companyId, location.pathname]);

  return (
    <div className="app-shell">
      <Sidebar 
        company={company} 
        counts={counts} 
        onOpenSettings={() => setSettingsOpen(true)} 
      />
      <main className="app-main">
        <Outlet context={{ company, setCompany, counts, setCounts }} />
      </main>
      <AccountModal 
        isOpen={settingsOpen} 
        onClose={() => setSettingsOpen(false)} 
      />
    </div>
  );
};
