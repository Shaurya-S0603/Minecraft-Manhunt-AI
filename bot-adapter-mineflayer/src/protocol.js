'use strict'

const CONTRACT_VERSION = '1'
const MESSAGE_TYPES = new Set([
  'observation',
  'action_request',
  'action_ack',
  'heartbeat',
  'match_state'
])
const MAX_MESSAGE_BYTES = 64 * 1024

class ProtocolError extends Error {
  constructor(message) {
    super(message)
    this.name = 'ProtocolError'
  }
}

function validateMessage(message, options = {}) {
  if (!message || typeof message !== 'object' || Array.isArray(message)) {
    throw new ProtocolError('Message must be an object')
  }

  const required = ['contract_version', 'message_type', 'sender', 'match_id', 'request_id', 'payload']
  const missing = required.filter((field) => !(field in message))
  if (missing.length > 0) {
    throw new ProtocolError(`Missing required fields: ${missing.join(', ')}`)
  }
  if (message.contract_version !== CONTRACT_VERSION) {
    throw new ProtocolError(`Unsupported contract version: ${message.contract_version}`)
  }
  if (!MESSAGE_TYPES.has(message.message_type)) {
    throw new ProtocolError(`Unsupported message type: ${message.message_type}`)
  }
  for (const field of ['sender', 'match_id', 'request_id']) {
    if (typeof message[field] !== 'string' || message[field].trim() === '') {
      throw new ProtocolError(`${field} must be a non-empty string`)
    }
  }
  if (options.expectedMatchId && message.match_id !== options.expectedMatchId) {
    throw new ProtocolError('Message belongs to a different match')
  }
  if (options.expectedSender && message.sender !== options.expectedSender) {
    throw new ProtocolError('Message sender is not authorized')
  }
  if (!message.payload || typeof message.payload !== 'object' || Array.isArray(message.payload)) {
    throw new ProtocolError('payload must be an object')
  }
  if (Buffer.byteLength(JSON.stringify(message), 'utf8') > (options.maxBytes || MAX_MESSAGE_BYTES)) {
    throw new ProtocolError('Message exceeds the maximum size')
  }
  if ('tick' in message && (!Number.isInteger(message.tick) || message.tick < 0)) {
    throw new ProtocolError('tick must be a non-negative integer')
  }
  return message
}

function createEnvelope(messageType, sender, matchId, payload, requestId, tick) {
  const message = {
    contract_version: CONTRACT_VERSION,
    message_type: messageType,
    sender,
    match_id: matchId,
    request_id: requestId || `${sender}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    payload: { ...payload }
  }
  if (tick !== undefined) message.tick = tick
  return validateMessage(message, { expectedMatchId: matchId })
}

module.exports = {
  CONTRACT_VERSION,
  MAX_MESSAGE_BYTES,
  MESSAGE_TYPES,
  ProtocolError,
  createEnvelope,
  validateMessage
}
