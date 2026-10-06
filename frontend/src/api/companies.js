import apiClient from './client';

export const companiesApi = {
  list: async () => {
    const response = await apiClient.get('/companies');
    return response.data;
  },

  get: async (id) => {
    const response = await apiClient.get(`/companies/${id}`);
    return response.data;
  },

  create: async (companyData) => {
    const response = await apiClient.post('/companies', companyData);
    return response.data;
  },

  update: async (id, companyData) => {
    const response = await apiClient.put(`/companies/${id}`, companyData);
    return response.data;
  },

  delete: async (id) => {
    const response = await apiClient.delete(`/companies/${id}`);
    return response.data;
  },

  duplicate: async (id) => {
    const response = await apiClient.post(`/companies/${id}/duplicate`);
    return response.data;
  },

  suggestFeatures: async (companyId, tierId) => {
    const response = await apiClient.post(`/companies/${companyId}/tiers/${tierId}/features/suggest`);
    return response.data;
  },

  bulkAddFeatures: async (companyId, tierId, features) => {
    const response = await apiClient.post(`/companies/${companyId}/tiers/${tierId}/features/bulk`, {
      features,
    });
    return response.data;
  },
};
