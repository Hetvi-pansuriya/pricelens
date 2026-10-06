import apiClient from './client';

export const analysisApi = {
  start: async (companyId) => {
    const response = await apiClient.post(`/analysis/start/${companyId}`);
    return response.data;
  },

  getTicket: async (sessionId) => {
    const response = await apiClient.post(`/analysis/progress-ticket/${sessionId}`);
    return response.data;
  },

  getReport: async (sessionId) => {
    const response = await apiClient.get(`/analysis/report/${sessionId}`);
    return response.data;
  },

  downloadPdf: async (sessionId, companyName = 'company') => {
    const response = await apiClient.get(`/analysis/report/${sessionId}/pdf`, {
      responseType: 'blob',
    });
    const url = window.URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `${companyName}-pricing-report.pdf`);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  },

  emailReport: async (sessionId) => {
    const response = await apiClient.post(`/analysis/report/${sessionId}/email`);
    return response.data;
  },

  history: async (companyId) => {
    const response = await apiClient.get(`/analysis/history/${companyId}`);
    return response.data;
  },
};
