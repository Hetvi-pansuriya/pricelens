import apiClient from './client';

export const competitorsApi = {
  list: async (companyId) => {
    const response = await apiClient.get(`/companies/${companyId}/competitors`);
    return response.data;
  },

  add: async (companyId, url) => {
    const response = await apiClient.post(`/companies/${companyId}/competitors`, { url });
    return response.data;
  },

  manualText: async (companyId, competitorId, text) => {
    const response = await apiClient.patch(
      `/companies/${companyId}/competitors/${competitorId}/manual`,
      { text }
    );
    return response.data;
  },

  delete: async (companyId, competitorId) => {
    const response = await apiClient.delete(
      `/companies/${companyId}/competitors/${competitorId}`
    );
    return response.data;
  },

  suggest: async (companyId) => {
    const response = await apiClient.post(`/companies/${companyId}/competitors/suggest`);
    return response.data;
  },

  refresh: async (companyId, competitorId) => {
    const response = await apiClient.post(
      `/companies/${companyId}/competitors/${competitorId}/refresh`
    );
    return response.data;
  },
};
