import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import App from '../src/App'

describe('App', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('renders a real PC task entry point and local privacy boundary', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          active_task: null,
          capture: { status: 'IDLE', quality_flags: [] },
          timeline: null,
          phone_candidates: [],
        }),
      }),
    )
    render(<App />)

    await waitFor(() => expect(fetch).toHaveBeenCalledWith('/api/dashboard', expect.any(Object)))
    expect(screen.getByRole('heading', { name: 'PC 学习工作台' })).toBeDefined()
    expect(screen.getByRole('button', { name: '开始本机任务采集' })).toBeDefined()
    expect(screen.getByText(/不截图、不记录键盘/)).toBeDefined()
  })
})
