import { API } from '../constants/api'
import { apiRequest } from './http'

export const fetchTodayReport = () => apiRequest(API.DAILY_REPORTS.TODAY)
export const fetchDailyReportUsers = () => apiRequest(API.DAILY_REPORTS.USERS)

export const saveDailyTasks = (reportDate, tasks) => apiRequest(API.DAILY_REPORTS.TASKS, {
  method: 'PUT',
  body: JSON.stringify({ report_date: reportDate, tasks }),
})

export const saveAndCopyTodayReport = (reportDate, tasks) => apiRequest(API.DAILY_REPORTS.COPY, {
  method: 'POST',
  body: JSON.stringify({ report_date: reportDate, tasks }),
})

export const fetchDailyReports = (filters = {}) => {
  const params = new URLSearchParams(Object.entries(filters).filter(([, value]) => value !== '' && value != null))
  return apiRequest(`${API.DAILY_REPORTS.ROOT}${params.size ? `?${params}` : ''}`)
}
