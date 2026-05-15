import axios from 'axios'

// import.meta.env.BASE_URL = '/digital-employee/' in production (set by vite.config.js base)
// and '/' in Vite dev mode only if base were unset — here it's always '/digital-employee/'
export const api = axios.create({ baseURL: import.meta.env.BASE_URL + 'api' })

export const agentApi = {
  list: () => api.get('/agents').then(r => r.data),
  listOffboarded: () => api.get('/agents/offboarded').then(r => r.data),
  create: (data) => api.post('/agents', data).then(r => r.data),
  get: (id) => api.get(`/agents/${id}`).then(r => r.data),
  update: (id, data) => api.put(`/agents/${id}`, data).then(r => r.data),
  offboard: (id) => api.patch(`/agents/${id}/offboard`).then(r => r.data),
  delete: (id) => api.delete(`/agents/${id}`),
  updateRanking: (id, ranking) => api.patch(`/agents/${id}/ranking`, { ranking }).then(r => r.data),
  listConversations: (id) => api.get(`/agents/${id}/conversations`).then(r => r.data),
  createConversation: (id) => api.post(`/agents/${id}/conversations`).then(r => r.data),
  getKbStatus: (id) => api.get(`/agents/${id}/knowledge`).then(r => r.data),
  mergeToMain: (id, sources) => api.post(`/agents/${id}/knowledge/merge`, { sources }).then(r => r.data),
}

export const promptApi = {
  list:     (agentId, type = 'base')  => api.get(`/agents/${agentId}/prompts`, { params: { type } }).then(r => r.data),
  getActive:(agentId, type = 'base')  => api.get(`/agents/${agentId}/prompts/active`, { params: { type } }).then(r => r.data),
  save:     (agentId, payload)        => api.post(`/agents/${agentId}/prompts`, payload).then(r => r.data),
  activate: (agentId, versionId)      => api.post(`/agents/${agentId}/prompts/${versionId}/activate`).then(r => r.data),
}

export const convApi = {
  get:       (id)        => api.get(`/conversations/${id}`).then(r => r.data),
  rename:    (id, title) => api.patch(`/conversations/${id}`, { title }).then(r => r.data),
  delete:    (id)        => api.delete(`/conversations/${id}`),
  saveToKb:  (id)        => api.post(`/conversations/${id}/save-to-kb`).then(r => r.data),
}

export const auditApi = {
  list: (params) => api.get('/audit', { params }).then(r => r.data),
  summary: (params) => api.get('/audit/summary', { params }).then(r => r.data),
}

export const examApi = {
  list:             ()                       => api.get('/exams').then(r => r.data),
  get:              (filename)               => api.get(`/exams/${filename}`).then(r => r.data),
  create:           (payload)               => api.post('/exams', payload).then(r => r.data),
  update:           (filename, payload)     => api.put(`/exams/${filename}`, payload).then(r => r.data),
  delete:           (filename)              => api.delete(`/exams/${filename}`),
  startRun:         (agentId, examFile)     => api.post(`/agents/${agentId}/exam-runs`, { exam_file: examFile }).then(r => r.data),
  listRuns:         (agentId)               => api.get(`/agents/${agentId}/exam-runs`).then(r => r.data),
  getRun:           (runId)                 => api.get(`/exam-runs/${runId}`).then(r => r.data),
  submitMentorScore:(runId, scores)         => api.patch(`/exam-runs/${runId}/mentor`, { scores }).then(r => r.data),
  compare:          (agentIds)              => api.get('/exam-runs/compare', { params: { agent_ids: agentIds.join(',') } }).then(r => r.data),
  versionMatrix:    (agentId)              => api.get(`/agents/${agentId}/exam-runs/version-matrix`).then(r => r.data),
  suggest:          (runId)               => api.post(`/exam-runs/${runId}/suggest`).then(r => r.data),
  applysuggestion:  (runId)               => api.post(`/exam-runs/${runId}/suggest/apply`).then(r => r.data),
  examDrafts: {
    list:    ()         => api.get('/exam-drafts').then(r => r.data),
    publish: (examId)   => api.post(`/exam-drafts/${examId}/publish`).then(r => r.data),
    discard: (examId)   => api.delete(`/exam-drafts/${examId}`).then(r => r.data),
  },
}

export const groupApi = {
  list:   ()           => api.get('/group-chats').then(r => r.data),
  create: (data)       => api.post('/group-chats', data).then(r => r.data),
  get:    (id)         => api.get(`/group-chats/${id}`).then(r => r.data),
  rename: (id, title)  => api.patch(`/group-chats/${id}`, { title }).then(r => r.data),
  delete: (id)         => api.delete(`/group-chats/${id}`),
}

export const permissionApi = {
  get:          ()                    => api.get('/permissions').then(r => r.data),
  updateTool:   (toolName, riskLevel) => api.put(`/permissions/tools/${toolName}`, { risk_level: riskLevel }).then(r => r.data),
  updateRanking:(ranking, ceiling)    => api.put(`/permissions/rankings/${ranking}`, { ceiling }).then(r => r.data),
  reset:        ()                    => api.post('/permissions/reset').then(r => r.data),
}

export const rolePromptApi = {
  list:   ()             => api.get('/role-prompts').then(r => r.data),
  get:    (role)         => api.get(`/role-prompts/${role}`).then(r => r.data),
  update: (role, content) => api.put(`/role-prompts/${role}`, { content }).then(r => r.data),
  reset:  (role)         => api.post(`/role-prompts/${role}/reset`).then(r => r.data),
}

export const testSuiteApi = {
  listForAgent:   (agentId)           => api.get(`/agents/${agentId}/test-suites`).then(r => r.data),
  listAll:        (filters = {})      => api.get('/test-suites', { params: filters }).then(r => r.data),
  listComponents: ()                  => api.get('/test-suites/components').then(r => r.data),
  create:         (agentId, payload)  => api.post(`/agents/${agentId}/test-suites`, payload).then(r => r.data),
  get:            (suiteId)           => api.get(`/test-suites/${suiteId}`).then(r => r.data),
  update:         (suiteId, payload)  => api.put(`/test-suites/${suiteId}`, payload).then(r => r.data),
  delete:         (suiteId)           => api.delete(`/test-suites/${suiteId}`),
  addCase:        (suiteId, payload)  => api.post(`/test-suites/${suiteId}/cases`, payload).then(r => r.data),
  updateCase:     (suiteId, caseId, payload) => api.put(`/test-suites/${suiteId}/cases/${caseId}`, payload).then(r => r.data),
  deleteCase:     (suiteId, caseId)   => api.delete(`/test-suites/${suiteId}/cases/${caseId}`),
  exportMarkdown: (suiteId)           => api.get(`/test-suites/${suiteId}/export/markdown`).then(r => r.data),
  exportXMind:    (suiteId)           => api.get(`/test-suites/${suiteId}/export/xmind`, { responseType: 'blob' }).then(r => r.data),
}

export const testRunApi = {
  start:       (payload)         => api.post('/test-runs', payload).then(r => r.data),
  list:        (filters = {})    => api.get('/test-runs', { params: filters }).then(r => r.data),
  get:         (runId)           => api.get(`/test-runs/${runId}`).then(r => r.data),
  analytics:   ()                => api.get('/test-runs/analytics').then(r => r.data),
  screenshots: (runId, caseId)   => api.get(`/test-runs/${runId}/cases/${caseId}/screenshots`).then(r => r.data),
  terminate:   (runId)           => api.post(`/test-runs/${runId}/terminate`).then(r => r.data),
}

export const testPlanApi = {
  list:    ()                    => api.get('/test-plans').then(r => r.data),
  create:  (payload)             => api.post('/test-plans', payload).then(r => r.data),
  get:     (planId)              => api.get(`/test-plans/${planId}`).then(r => r.data),
  update:  (planId, payload)     => api.put(`/test-plans/${planId}`, payload).then(r => r.data),
  delete:  (planId)              => api.delete(`/test-plans/${planId}`),
  execute: (planId, payload)     => api.post(`/test-plans/${planId}/execute`, payload).then(r => r.data),
}

export function createGroupWebSocket(groupId) {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const host = window.location.host
  const base = import.meta.env.BASE_URL.replace(/\/$/, '')
  return new WebSocket(`${proto}://${host}${base}/api/group-chats/${groupId}/ws`)
}

export function createWebSocket(convId) {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const host = window.location.host
  const base = import.meta.env.BASE_URL.replace(/\/$/, '')
  return new WebSocket(`${proto}://${host}${base}/api/conversations/${convId}/ws`)
}
