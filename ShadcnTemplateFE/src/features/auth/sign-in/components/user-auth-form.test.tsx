import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, type RenderResult } from 'vitest-browser-react'
import { type Locator, userEvent } from 'vitest/browser'
import { UserAuthForm } from './user-auth-form'

const FORM_MESSAGES = {
  emailEmpty: 'Please enter your email.',
  passwordEmpty: 'Please enter your password.',
  passwordShort: 'Password must be at least 8 characters long.',
} as const

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  setUser: vi.fn(),
  setSession: vi.fn(),
  reset: vi.fn(),
  post: vi.fn(),
  get: vi.fn(),
}))

const apiUser = {
  id: 'user-1',
  email: 'a@b.com',
  full_name: 'API User',
  is_active: true,
  role: { name: 'Viewer', permissions: [] },
}

vi.mock('@/stores/auth-store', () => ({
  useAuthStore: () => ({
    auth: {
      setUser: mocks.setUser,
      setSession: mocks.setSession,
      reset: mocks.reset,
    },
  }),
}))

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return {
    ...actual,
    useNavigate: () => mocks.navigate,
  }
})

vi.mock('@/lib/api-client', () => ({
  apiClient: { post: mocks.post, get: mocks.get },
}))

describe('UserAuthForm', () => {
  describe('Rendering without redirectTo', () => {
    let screen: RenderResult
    let emailInput: Locator
    let passwordInput: Locator
    let signInButton: Locator

    beforeEach(async () => {
      vi.clearAllMocks()
      mocks.post.mockResolvedValue({
        data: { access_token: 'access-token', refresh_token: 'refresh-token' },
      })
      mocks.get.mockResolvedValue({ data: apiUser })
      screen = await render(<UserAuthForm />)
      emailInput = screen.getByRole('textbox', { name: /^Email$/i })
      passwordInput = screen.getByLabelText(/^Password$/i)
      signInButton = screen.getByRole('button', { name: /^Sign in$/i })
    })

    it('renders fields and submit button', async () => {
      await expect.element(emailInput).toBeInTheDocument()
      await expect.element(passwordInput).toBeInTheDocument()
      await expect.element(signInButton).toBeInTheDocument()
    })

    it('shows validation messages when submitting empty form', async () => {
      await userEvent.click(signInButton)

      await expect
        .element(screen.getByText(FORM_MESSAGES.emailEmpty))
        .toBeInTheDocument()
      await expect
        .element(screen.getByText(FORM_MESSAGES.passwordEmpty))
        .toBeInTheDocument()
    })

    it('authenticates and navigates to default route on success', async () => {
      await userEvent.fill(emailInput, 'a@b.com')
      await userEvent.fill(passwordInput, '12345678')

      await userEvent.click(signInButton)

      await vi.waitFor(() => expect(mocks.setUser).toHaveBeenCalledOnce())
      expect(mocks.setUser).toHaveBeenCalledWith(apiUser)
      expect(mocks.setSession).toHaveBeenCalledWith(
        'access-token',
        'refresh-token',
        false
      )

      await vi.waitFor(() =>
        expect(mocks.navigate).toHaveBeenCalledWith({ to: '/', replace: true })
      )
    })
  })

  it('navigates to redirectTo when provided', async () => {
    vi.clearAllMocks()
    mocks.post.mockResolvedValue({
      data: { access_token: 'access-token', refresh_token: 'refresh-token' },
    })
    mocks.get.mockResolvedValue({ data: apiUser })

    const { getByRole, getByLabelText } = await render(
      <UserAuthForm redirectTo='/settings' />
    )

    await userEvent.fill(getByRole('textbox', { name: /Email/i }), 'a@b.com')
    await userEvent.fill(getByLabelText('Password'), '12345678')

    await userEvent.click(getByRole('button', { name: /Sign in/i }))

    await vi.waitFor(() => expect(mocks.setUser).toHaveBeenCalledOnce())
    expect(mocks.setSession).toHaveBeenCalledOnce()

    await vi.waitFor(() =>
      expect(mocks.navigate).toHaveBeenCalledWith({
        to: '/settings',
        replace: true,
      })
    )
  })
})
