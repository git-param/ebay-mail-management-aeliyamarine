import { useEffect, useState } from 'react'
import AppLayout from '../layouts/app_layout'
import { exportMessageReport, fetchMessageReport, fetchMessageTypeTree } from '../services/messageTypeApi'
import { fetchUsers } from '../services/userApi'
import { fetchEbayAccounts } from '../services/ebayAccountApi'
import { normalizeRole } from '../utils/roles'

export default function MessageReports({ currentUser, onLogout }) 
{
  const isAgent = normalizeRole(currentUser?.role) === 'AGENT'
  const [copied,setCopied]=useState(false)
  const [filters,setFilters]=useState({date_from:'',date_to:'',seller_account_id:'',user_id:'',category_id:'',subcategory_id:'',search:''}); const [data,setData]=useState(null); const [types,setTypes]=useState([]); const [users,setUsers]=useState([]); const [accounts,setAccounts]=useState([]); const [error,setError]=useState(''); const category=types.find((x)=>x.id===filters.category_id)
  async function load(next=filters)
  {
    try
      {
        setData(await fetchMessageReport(next));
        setError('')
      }
      catch(e)
      {
        setError(e.message)
      }
    }
  useEffect(()=>{
    const timer=window.setTimeout(()=>{load(); 
    Promise.allSettled([fetchMessageTypeTree(),isAgent?Promise.resolve([]):fetchUsers(),fetchEbayAccounts()])
    .then(([t,u,a])=>{
      if(t.status==='fulfilled')
        setTypes(t.value||[]);
      if(u.status==='fulfilled')
        setUsers(u.value.items||u.value||[]);
      if(a.status==='fulfilled')
        setAccounts(a.value.items||a.value||[])})
      },0);
    return()=>window.clearTimeout(timer)
  },[])
  function update(key,value)
  {
    setFilters((f)=>(
    {
      ...f,[key]:value,...(key==='category_id'?{subcategory_id:''}:{})
    }))
  }
  async function download()
  {
    try
    {
      const blob=await exportMessageReport(filters);
      const url=URL.createObjectURL(blob);
      const link=document.createElement('a');
      link.href=url;
      link.download=`message_report_${new Date().toISOString().slice(0,10).replaceAll('-','_')}.xlsx`;
      link.click();
      URL.revokeObjectURL(url)
    }
    catch(e)
    {
      setError(e.message)
    }
  }
  function reportPeriod()
  {
    const format=(value)=>value?value.split('-').reverse().join('-'):''
    if(filters.date_from&&filters.date_to)
      return filters.date_from===filters.date_to?format(filters.date_from):`${format(filters.date_from)} - ${format(filters.date_to)}`
    if(filters.date_from||filters.date_to)
      return format(filters.date_from||filters.date_to)
    return 'All Time'
  }
  async function copyStats()
  {
    const reports=data?.employee_category_reports||[]
    const text=reports.map((report)=>[
      `Work Report: ${reportPeriod()}`,
      '',
      ...(!isAgent&&!filters.user_id?[`Employee: ${report.employee}`,'']:[]),
      ...report.categories.map((item)=>`${item.label} - ${item.value}`),
    ].join('\n')).join('\n\n\n')
    if(!text)
    {
      setError('No report statistics are available to copy.')
      return
    }
    try
    {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setError('')
      window.setTimeout(()=>setCopied(false),2000)
    }
    catch
    {
      setError('Unable to copy report statistics to the clipboard.')
    }
  }
  return <AppLayout activePage="Message Reports" currentUser={currentUser} onLogout={onLogout}><main className="management-page"><div className="page-header"><div><h1>Messaging Analytics</h1><p>Internal reply classifications and productivity.</p></div><div className="page-header-actions"><button className="secondary-button compact-action" type="button" onClick={copyStats}>{copied?'Copied!':'Copy Stats'}</button><button className="secondary-button compact-action" type="button" onClick={download}>Export Excel</button></div></div><form className="analytics-filter-bar" onSubmit={(e)=>{e.preventDefault();load()}}>{[['date_from','From','date'],['date_to','To','date'],['search','Search','search']].map(([k,l,t])=><label className="field" key={k}><span>{l}</span><input type={t} value={filters[k]} onChange={(e)=>update(k,e.target.value)}/></label>)}<label className="field"><span>Seller</span><select value={filters.seller_account_id} onChange={(e)=>update('seller_account_id',e.target.value)}><option value="">All</option>{accounts.map((x)=><option key={x.id} value={x.id}>{x.store_name||x.account_name}</option>)}</select></label>{!isAgent?<label className="field"><span>Employee</span><select value={filters.user_id} onChange={(e)=>update('user_id',e.target.value)}><option value="">All</option>{users.map((x)=><option key={x.id} value={x.id}>{x.full_name||x.email}</option>)}</select></label>:null}<label className="field"><span>Category</span><select value={filters.category_id} onChange={(e)=>update('category_id',e.target.value)}><option value="">All</option>{types.map((x)=><option key={x.id} value={x.id}>{x.name}</option>)}</select></label>{category?.children?.length?<label className="field"><span>Sub Category</span><select value={filters.subcategory_id} onChange={(e)=>update('subcategory_id',e.target.value)}><option value="">All</option>{category.children.map((x)=><option key={x.id} value={x.id}>{x.name}</option>)}</select></label>:null}<button className="primary-button compact" type="submit">Apply</button></form>{error?<p className="form-message error">{error}</p>:null}<section className="stats-grid analytics-stats-grid">{(data?.summary||[]).slice(0,9).map((x)=><article className="stat-card" key={x.label}><div><p>{x.label}</p><strong>{x.value}</strong></div></article>)}</section><section className="analytics-panel"><div className="report-table-wrap"><table><thead><tr><th>Date</th><th>Time</th><th>Seller</th><th>Conversation</th><th>Buyer</th><th>Agent</th><th>Category</th><th>Sub Category</th><th>Preview</th><th>Message ID</th></tr></thead><tbody>{(data?.items||[]).map((x)=><tr key={x.id}><td>{new Date(x.created_at).toLocaleDateString()}</td><td>{new Date(x.created_at).toLocaleTimeString()}</td><td>{x.seller}</td><td>{x.provider_conversation_id}</td><td>{x.buyer}</td><td>{x.agent}</td><td>{x.category}</td><td>{x.subcategory||'—'}</td><td>{x.message_preview}</td><td>{x.conversation_message_id}</td></tr>)}</tbody></table></div></section></main></AppLayout>
}
