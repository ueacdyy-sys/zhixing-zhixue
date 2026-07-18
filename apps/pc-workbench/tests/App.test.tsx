import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import App from '../src/App'

describe('App', () => {
  it('renders heading', () => {
    render(<App />)
    expect(screen.getByText('知行智学 - PC 工作台')).toBeDefined()
  })
})
