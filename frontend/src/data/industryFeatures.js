export const INDUSTRY_FEATURES = {
  saas_b2b: [
    "Team management", "Role-based access control", "SSO / SAML login",
    "API access", "Custom reports", "Audit logs", "Third-party integrations",
    "Priority support", "Dedicated account manager", "Custom workflows",
    "Advanced analytics", "Data export", "Webhook support", "SLA guarantee",
    "White labeling", "Multi-org support", "IP allowlisting",
    "SCIM provisioning", "Custom fields", "Onboarding assistance",
    "99.9% uptime SLA", "GDPR compliance tools", "Data residency options"
  ],
  saas_b2c: [
    "User profiles", "Mobile app (iOS/Android)", "Personalization",
    "Push notifications", "Offline mode", "Family sharing", "Ad-free experience",
    "Priority support", "Cloud sync", "Dark mode", "Multiple accounts",
    "Import/export data", "2FA security", "Custom themes", "Unlimited storage",
    "Early access to features", "Usage analytics", "Referral rewards",
    "Advanced search", "Custom notifications", "Archive access"
  ],
  project_management: [
    "Task management", "Kanban boards", "Time tracking", "Gantt charts",
    "Team collaboration", "File sharing", "Automations", "Portfolio reporting",
    "Recurring tasks", "Subtasks", "Custom statuses", "Workload management",
    "Calendar view", "Timeline view", "Guest access", "Templates library",
    "Dependency tracking", "Milestones", "Sprint planning", "Burndown charts",
    "API access", "Integrations (Slack, GitHub, Jira)", "Advanced search"
  ],
  hr_software: [
    "Employee profiles", "Attendance tracking", "Payroll processing",
    "Performance reviews", "Leave management", "Recruitment pipeline",
    "SSO login", "Audit logs", "Expense management", "Onboarding workflows",
    "Offboarding workflows", "Training management", "Benefits administration",
    "Compliance reporting", "Org chart", "Employee self-service portal",
    "360-degree feedback", "Goal tracking (OKRs)", "HR analytics dashboard",
    "Multi-location support", "Custom HR forms", "Digital document signing",
    "Dedicated HR consultant"
  ],
  analytics: [
    "Dashboards", "Custom reports", "Data exports (CSV/PDF)", "Real-time analytics",
    "Forecasting", "API access", "Data connectors", "Scheduled reports",
    "Funnel analysis", "Cohort analysis", "A/B test tracking", "Heatmaps",
    "User segmentation", "Custom events tracking", "Retention analysis",
    "Revenue analytics", "Multi-source data blending", "SQL query editor",
    "White-label reports", "Alerting and anomaly detection", "Data governance",
    "Unlimited data history", "Embedded analytics"
  ],
  crm: [
    "Contact management", "Sales pipeline", "Email integration",
    "Lead scoring", "Workflow automation", "Sales forecasting",
    "Custom fields", "Advanced reporting", "Email sequences",
    "Call logging", "Meeting scheduling", "Document management",
    "Deal tracking", "Territory management", "Quote and proposal builder",
    "Revenue attribution", "Account-based marketing", "Duplicate detection",
    "Custom dashboards", "Mobile CRM app", "API access",
    "LinkedIn integration", "Customer health scores"
  ],
  payments: [
    "Recurring billing", "Invoicing", "Multi-currency support", "Fraud detection",
    "Tax calculations", "Payment links", "Customer portal", "Webhooks",
    "Custom checkout", "Subscription metrics", "Dunning management",
    "Reconciliation reports", "Dispute management", "Payout scheduling"
  ],
  ecommerce_tools: [
    "Product catalog", "Inventory tracking", "Order management", "Discount codes",
    "Shipping calculators", "Cart recovery", "Customer accounts", "Reviews management",
    "Multi-store sync", "POS integration", "Tax automation", "Return management"
  ],
  other: [
    "User management", "Basic analytics", "Email notifications", "Data export",
    "API access", "Standard support", "Priority support", "Audit logging",
    "Custom configurations", "Daily backups", "SSO integration"
  ]
};

export const getIndustryFeatures = (industry) => {
  const key = industry ? industry.toLowerCase().replace(/[\s-]/g, '_') : 'other';
  return INDUSTRY_FEATURES[key] || INDUSTRY_FEATURES['other'];
};
