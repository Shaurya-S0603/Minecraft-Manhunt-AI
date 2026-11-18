'use strict'

const { createEnvelope, validateMessage } = require('./protocol')

const ALLOWED_ACTIONS = new Set(['move-to', 'stop', 'look', 'jump', 'retreat', 'search', 'wait'])

class ActionDispatcher {
  constructor({ bot, matchId, sender = 'mineflayer-adapter', publish, movementDriver }) {
    if (!bot || !matchId || typeof publish !== 'function') {
      throw new TypeError('bot, matchId, and publish are required')
    }
    this.bot = bot
    this.matchId = matchId
    this.sender = sender
    this.publish = publish
    this.movementDriver = movementDriver
    this.phase = 'SETUP'
    this.currentRequestId = null
  }

  setPhase(phase) {
    this.phase = phase
  }

  dispatch(message) {
    validateMessage(message, { expectedMatchId: this.matchId })
    if (message.message_type !== 'action_request') {
      throw new Error('Expected an action_request message')
    }
    const action = message.payload.action || message.payload.name
    if (!ALLOWED_ACTIONS.has(action)) {
      return this.ack(message.request_id, 'rejected', `Unsupported action: ${action}`)
    }
    if (this.phase === 'SETUP' || this.phase === 'WORLD_READY') {
      return this.ack(message.request_id, 'rejected', `Actions are forbidden during ${this.phase}`)
    }
    if (this.currentRequestId) {
      return this.ack(message.request_id, 'rejected', 'Another action is already running')
    }
    this.currentRequestId = message.request_id
    return this.execute(action, message.payload, message.request_id)
  }

  async execute(action, payload, requestId) {
    try {
      if (action === 'stop') {
        this.movementDriver.stop()
      } else if (action === 'move-to' || action === 'retreat') {
        await this.movementDriver.moveTo(payload.target, payload.timeout_ms || 10000)
      } else if (action === 'jump') {
        this.bot.setControlState('jump', true)
        setTimeout(() => this.bot.setControlState('jump', false), 250)
      }
      return this.ack(requestId, 'succeeded', '')
    } catch (error) {
      return this.ack(requestId, 'failed', error.message)
    } finally {
      this.currentRequestId = null
    }
  }

  ack(requestId, status, reason) {
    const message = createEnvelope('action_ack', this.sender, this.matchId, {
      accepted: status !== 'rejected',
      status,
      reason
    }, requestId)
    this.publish(message)
    return message
  }
}

module.exports = { ActionDispatcher, ALLOWED_ACTIONS }
