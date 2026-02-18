import axios from 'axios';

const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';
const baseURL = apiUrl.startsWith('http') ? apiUrl : `https://${apiUrl}`;

const api = axios.create({
  baseURL,
});

export const getProjects = async () => {
  const response = await api.get('/projects/');
  return response.data;
};

export const getProject = async (id: string) => {
  const response = await api.get(`/projects/${id}`);
  return response.data;
};

export const updateProject = async (id: string, data: { name?: string; description?: string }) => {
  const response = await api.put(`/projects/${id}`, data);
  return response.data;
};

export const createProject = async (data: { name: string; description?: string }) => {
  const response = await api.post('/projects/', data);
  return response.data;
};

export const deleteProject = async (id: string) => {
  const response = await api.delete(`/projects/${id}`);
  return response.data;
};

export const getRounds = async (projectId: string) => {
  const response = await api.get(`/projects/${projectId}/rounds/`);
  return response.data;
};

export const createRound = async (data: { project_id: string; name: string; order: number }) => {
  const response = await api.post('/rounds/', data);
  return response.data;
};

export const deleteRound = async (id: string) => {
  const response = await api.delete(`/rounds/${id}`);
  return response.data;
};

export const getBudgets = async (roundId: string) => {
  const response = await api.get(`/rounds/${roundId}/budgets/`);
  return response.data;
};

export const createBudget = async (data: FormData, customUrl?: string) => {
  if (customUrl) {
    // Use direct axios call for external URLs (n8n) to avoid baseURL and interceptors
    const response = await axios.post(customUrl, data, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  }

  const response = await api.post('/budgets/', data, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
};

export const deleteBudget = async (id: string) => {
  const response = await api.delete(`/budgets/${id}`);
  return response.data;
};

export const updateBudget = async (id: string, data: any) => {
  const response = await api.put(`/budgets/${id}`, data);
  return response.data;
};

export const createBudgetNote = async (id: string, content: string) => {
  const response = await api.post(`/budgets/${id}/notes/`, { content });
  return response.data;
};

export const getBudgetNotes = async (id: string) => {
  const response = await api.get(`/budgets/${id}/notes/`);
  return response.data;
};

export const promoteRound = async (data: { project_id: string; current_round_id: string; budget_ids: string[]; new_round_name: string }) => {
  const response = await api.post('/promote/', data);
  return response.data;
};

// Removed duplicate sendChatMessage


export const getChatHistory = async (projectId: string, sessionId?: string) => {
  const params = sessionId ? { session_id: sessionId } : {};
  const response = await api.get(`/projects/${projectId}/chat/`, { params });
  return response.data;
};

export const clearChatHistory = async (projectId: string) => {
  const response = await api.delete(`/projects/${projectId}/chat/`);
  return response.data;
};

export const getChatSessions = async (projectId: string) => {
    const response = await api.get(`/projects/${projectId}/sessions/`);
    return response.data;
};

export const createChatSession = async (projectId: string) => {
    const response = await api.post(`/projects/${projectId}/sessions/`);
    return response.data;
};

export const deleteChatSession = async (sessionId: string) => {
    const response = await api.delete(`/sessions/${sessionId}`);
    return response.data;
};

export const sendChatMessage = async (data: { project_id: string; message: string; session_id?: string }) => {
  const response = await api.post('/chat/', data);
  return response.data;
};

export const mergeRoundItems = async (roundId: string, data: { source_name: string; target_name: string; new_name: string }) => {
  const response = await api.post(`/rounds/${roundId}/merge-items`, data);
  return response.data;
};

export const detectDuplicates = async (roundId: string) => {
  const response = await api.post(`/rounds/${roundId}/detect-duplicates`);
  return response.data;
};

export const deleteDuplicate = async (duplicateId: string) => {
  const response = await api.delete(`/rounds/duplicates/${duplicateId}`);
  return response.data;
};

export const uploadBudgetExcel = async (data: FormData) => {
  const response = await api.post('/budgets/upload-excel', data, {
      headers: {
          'Content-Type': 'multipart/form-data',
      },
  });
  return response.data;
};

export const exportRoundPdf = async (roundId: string) => {
  const response = await api.get(`/rounds/${roundId}/export-pdf`, {
    responseType: 'blob',
  });
  
  // Vytvořit blob URL a stáhnout soubor
  const blob = new Blob([response.data], { type: 'application/pdf' });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `rozpocty_export_${roundId}.pdf`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
  
  return response.data;
};

