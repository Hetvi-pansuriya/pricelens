import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { ProtectedRoute } from './components/layout/ProtectedRoute';
import { AppLayout } from './components/layout/AppLayout';

import { Login } from './pages/Login';
import { Signup } from './pages/Signup';
import { ForgotPassword } from './pages/ForgotPassword';
import { ResetPassword } from './pages/ResetPassword';
import { Companies } from './pages/Companies';
import { CompanySetup } from './pages/CompanySetup';
import { PricingTiers } from './pages/PricingTiers';
import { Competitors } from './pages/Competitors';
import { RunAnalysis } from './pages/RunAnalysis';
import { Report } from './pages/Report';
import { CompanyReports } from './pages/CompanyReports';
import { AnalysisHistory } from './pages/AnalysisHistory';

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public Auth Routes */}
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />

          {/* Authenticated Dashboard & Company Routes */}
          <Route element={<ProtectedRoute />}>
            <Route element={<AppLayout />}>
              <Route path="/" element={<Navigate to="/companies" replace />} />
              <Route path="/companies" element={<Companies />} />
              <Route path="/companies/new" element={<CompanySetup />} />

              {/* Company context subpages */}
              <Route path="/companies/:companyId/tiers" element={<PricingTiers />} />
              <Route path="/companies/:companyId/competitors" element={<Competitors />} />
              <Route path="/companies/:companyId/analysis" element={<RunAnalysis />} />
              <Route path="/companies/:companyId/reports" element={<CompanyReports />} />
              <Route path="/companies/:companyId/history" element={<AnalysisHistory />} />

              {/* Direct Report View */}
              <Route path="/reports/:sessionId" element={<Report />} />
            </Route>
          </Route>

          {/* Fallback */}
          <Route path="*" element={<Navigate to="/companies" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
