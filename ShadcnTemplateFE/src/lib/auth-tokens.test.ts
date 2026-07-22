import { afterEach, describe, expect, it } from 'vitest'
import { clearTokens, isAccessTokenFresh, storeTokens } from './auth-tokens'

function token(exp: number) {
  return `header.${window.btoa(JSON.stringify({ exp })).replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_')}.signature`
}

describe('access token freshness', () => {
  afterEach(() => clearTokens())

  it('accepts a token that remains valid beyond the safety window', () => {
    storeTokens(token(Math.floor(Date.now() / 1000) + 120), 'refresh-token-value-long-enough', false)
    expect(isAccessTokenFresh()).toBe(true)
  })

  it('rejects expired, near-expiry and malformed tokens', () => {
    storeTokens(token(Math.floor(Date.now() / 1000) + 10), 'refresh-token-value-long-enough', false)
    expect(isAccessTokenFresh()).toBe(false)
    storeTokens('not-a-jwt', 'refresh-token-value-long-enough', false)
    expect(isAccessTokenFresh()).toBe(false)
  })
})
