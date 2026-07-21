import { FormEvent, useEffect, useState } from 'react'
import './workbench.css'

type TimelineEntry = { event_id: string; phase_id: string; event_type: string; start_ts: string; end_ts: string; quality_flags: string[]; replay_uri: string }
type Timeline = { phases: Array<{ phase_id: string; phase_type: string; started_at: string; ended_at: string }>; entries: TimelineEntry[] }
type Dashboard = {
  active_task: { session_id: string; task_id: string; task_type: string; goal: string; knowledge_tags: string[]; status: string } | null
  capture: { status: string; quality_flags: string[] }
  timeline: Timeline | null
  phone_candidates: Array<{ candidate_id: string; status: string; evidence_refs?: string[] }>
}

const emptyDashboard: Dashboard = { active_task: null, capture: { status: 'IDLE', quality_flags: [] }, timeline: null, phone_candidates: [] }

async function requestApi<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  const payload = (await response.json()) as T & { error?: { message?: string } }
  if (!response.ok) throw new Error(payload.error?.message ?? '本机工作台请求失败。')
  return payload
}

function formatTime(timestamp: string): string {
  return new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function App() {
  const [dashboard, setDashboard] = useState<Dashboard>(emptyDashboard)
  const [goal, setGoal] = useState('')
  const [taskType, setTaskType] = useState('video_course')
  const [tags, setTags] = useState('')
  const [phaseType, setPhaseType] = useState('watch')
  const [message, setMessage] = useState('连接本机工作台后可开始采集。')

  const refresh = async () => {
    try {
      setDashboard(await requestApi<Dashboard>('/api/dashboard'))
    } catch {
      setMessage('本机中枢未连接：请先启动 PC 工作台服务。')
    }
  }

  useEffect(() => {
    void refresh()
    const timer = window.setInterval(() => void refresh(), 2000)
    return () => window.clearInterval(timer)
  }, [])

  const startTask = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    try {
      const response = await requestApi<{ dashboard: Dashboard }>('/api/tasks', 'POST', {
        task_type: taskType, goal, knowledge_tags: tags.split(',').map((tag) => tag.trim()).filter(Boolean), phase_type: phaseType,
      })
      setDashboard(response.dashboard)
      setMessage('任务已开始：仅在本机采集前台窗口与进程事实。')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '任务未能开始。')
    }
  }

  const changePhase = async () => {
    try {
      const response = await requestApi<{ dashboard: Dashboard }>('/api/phases', 'POST', { phase_type: phaseType })
      setDashboard(response.dashboard)
      setMessage('已切换为“' + phaseType + '”阶段。')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '阶段未能切换。')
    }
  }

  const stopTask = async () => {
    try {
      const response = await requestApi<{ dashboard: Dashboard }>('/api/tasks/stop', 'POST', {})
      setDashboard(response.dashboard)
      setMessage('任务已结束，前台窗口采集已停止。')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '任务未能结束。')
    }
  }

  const active = dashboard.active_task?.status === 'ACTIVE'
  return (
    <main className="workbench-shell">
      <header className="topbar glass">
        <div><p className="eyebrow">知行智学 · 本地可信中枢</p><h1>PC 学习工作台</h1></div>
        <div className={'capture-pill ' + (active ? 'is-active' : '')}><span className="status-dot" />{dashboard.capture.status === 'ACTIVE' ? '正在本机采集前台事实' : '未采集'}</div>
      </header>
      <p className="privacy-note">{message}</p>
      <section className="workspace-grid">
        <article className="panel task-panel glass">
          <p className="section-label">PC 独立学习入口</p>
          <h2>{active ? dashboard.active_task?.goal : '开始一段 PC 学习任务'}</h2>
          {!active ? (
            <form onSubmit={startTask}>
              <label>学习目标<textarea value={goal} onChange={(event) => setGoal(event.target.value)} required placeholder="例如：完成算法课程第 3 节并整理疑问" /></label>
              <div className="form-row">
                <label>场景<select value={taskType} onChange={(event) => setTaskType(event.target.value)}><option value="video_course">网课</option><option value="reading">阅读</option><option value="research">检索</option><option value="writing">写作</option><option value="practice">做题</option><option value="project">项目实践</option></select></label>
                <label>起始阶段<select value={phaseType} onChange={(event) => setPhaseType(event.target.value)}><option value="watch">观看</option><option value="read">阅读</option><option value="search">检索</option><option value="write">写作</option><option value="practice">练习</option><option value="project">项目</option></select></label>
              </div>
              <label>知识标签（逗号分隔）<input value={tags} onChange={(event) => setTags(event.target.value)} required placeholder="算法,复杂度" /></label>
              <button className="primary-button" type="submit">开始本机任务采集</button>
            </form>
          ) : (
            <div className="active-task">
              <p>任务类型：{dashboard.active_task?.task_type}</p><p>知识标签：{dashboard.active_task?.knowledge_tags.join(' · ')}</p>
              <div className="form-row"><label>当前阶段<select value={phaseType} onChange={(event) => setPhaseType(event.target.value)}><option value="watch">观看</option><option value="read">阅读</option><option value="search">检索</option><option value="write">写作</option><option value="practice">练习</option><option value="project">项目</option></select></label><button className="secondary-button" type="button" onClick={changePhase}>切换阶段</button></div>
              <button className="danger-button" type="button" onClick={stopTask}>结束任务并停止采集</button>
            </div>
          )}
          <p className="boundary-copy">不截图、不记录键盘/剪贴板/浏览历史；窗口标题与进程元数据仅保存在本机证据账本。</p>
        </article>
        <article className="panel glass">
          <p className="section-label">PC 过程时间线</p><h2>前台窗口事实</h2>
          {dashboard.timeline?.entries.length ? <ol className="timeline">{dashboard.timeline.entries.map((entry) => <li key={entry.event_id}><time>{formatTime(entry.start_ts)}</time><div><strong>前台窗口发生变化</strong><p>{entry.replay_uri}</p>{entry.quality_flags.length > 0 && <small>质量标记：{entry.quality_flags.join('、')}</small>}</div></li>)}</ol> : <p className="empty-state">任务开始后，前台窗口发生变化会在这里形成可回放的本机事实。</p>}
        </article>
        <article className="panel phone-panel glass">
          <p className="section-label">跨端联查</p><h2>手机候选证据</h2><p className="boundary-copy">仅展示由学生明确关联到同一会话的 CANDIDATE_ONLY 候选，不会自动升级为学习阶段。</p>
          {dashboard.phone_candidates.length ? <ul className="candidate-list">{dashboard.phone_candidates.map((candidate) => <li key={candidate.candidate_id}><strong>{candidate.candidate_id}</strong><span>{candidate.status}</span></li>)}</ul> : <p className="empty-state">当前会话尚无已关联的手机候选证据。</p>}
        </article>
      </section>
    </main>
  )
}

export default App
