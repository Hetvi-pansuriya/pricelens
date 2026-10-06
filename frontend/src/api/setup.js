import apiClient from './client';

export const setupApi = {
  importFromUrl: async (url) => {
    const response = await apiClient.post('/setup/import-from-url', { url });
    return response.data;
  },

  importFromText: async (text) => {
    const response = await apiClient.post('/setup/import-from-text', { text });
    return response.data;
  },

  parseCsv: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await apiClient.post('/setup/parse-csv', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  downloadCsvTemplate: async () => {
    const response = await apiClient.get('/setup/csv-template', {
      responseType: 'blob',
    });
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', 'pricelens_tiers_template.csv');
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  },

  importFromStripe: async (stripeKey) => {
    const response = await apiClient.post('/setup/import-from-stripe', {
      stripe_key: stripeKey,
    });
    return response.data;
  },

  loadSampleCompany: async (force = false) => {
    const response = await apiClient.post(`/setup/sample-company?force=${force}`);
    return response.data;
  },
};
