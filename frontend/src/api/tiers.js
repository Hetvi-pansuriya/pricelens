import apiClient from './client';

export const tiersApi = {
  addTier: async (companyId, tierData) => {
    const response = await apiClient.post(`/companies/${companyId}/tiers`, tierData);
    return response.data;
  },

  updateTier: async (companyId, tierId, tierData) => {
    const response = await apiClient.put(`/companies/${companyId}/tiers/${tierId}`, tierData);
    return response.data;
  },

  deleteTier: async (companyId, tierId) => {
    const response = await apiClient.delete(`/companies/${companyId}/tiers/${tierId}`);
    return response.data;
  },

  addFeature: async (companyId, tierId, featureData) => {
    const response = await apiClient.post(
      `/companies/${companyId}/tiers/${tierId}/features`,
      featureData
    );
    return response.data;
  },

  deleteFeature: async (companyId, tierId, featureId) => {
    const response = await apiClient.delete(
      `/companies/${companyId}/tiers/${tierId}/features/${featureId}`
    );
    return response.data;
  },
};
