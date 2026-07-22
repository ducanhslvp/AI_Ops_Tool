import axios from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ensureAccessToken } from './api-client'
import { clearTokens, getAccessToken, isAccessTokenFresh, storeTokens } from './auth-tokens'

function token(exp: number) {
  return `header.${window.btoa(JSON.stringify({ exp })).replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_')}.signature`
}

describe('idle session recovery', () => {
  afterEach(() => {
    clearTokens()
    vi.restoreAllMocks()
  })

  it('rotates an expired access token before protected screens load', async () => {
    const freshToken = token(Math.floor(Date.now() / 1000) + 300)
    storeTokens(token(Math.floor(Date.now() / 1000) - 30), 'valid-refresh-token-for-test', true)
    const refresh = vi.spyOn(axios, 'post').mockResolvedValue({ data: {
      access_token: freshToken,
      refresh_token: 'rotated-refresh-token-for-test',
    } })

    await expect(ensureAccessToken()).resolves.toBe(true)
    expect(refresh).toHaveBeenCalledTimes(1)
    expect(getAccessToken()).toBe(freshToken)
    expect(isAccessTokenFresh()).toBe(true)
  })
})
