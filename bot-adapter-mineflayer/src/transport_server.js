'use strict'

const { EventEmitter } = require('events')
const { validateMessage } = require('./protocol')

class TransportServer extends EventEmitter {
  constructor({ matchId, sender = 'mineflayer-adapter', maxQueue = 128 }) {
    super()
    if (!matchId) throw new TypeError('matchId is required')
    this.matchId = matchId
    this.sender = sender
    this.maxQueue = maxQueue
    this.connected = false
    this.queue = []
  }

  start() {
    this.connected = true
    this.emit('connected')
  }

  stop() {
    this.connected = false
    this.queue = []
    this.emit('disconnected')
  }

  send(message) {
    if (!this.connected) throw new Error('Transport is not started')
    validateMessage(message, { expectedMatchId: this.matchId })
    if (this.queue.length >= this.maxQueue) throw new Error('Transport queue is full')
    this.queue.push(message)
    this.emit('message', message)
    return message
  }

  receive(message) {
    validateMessage(message, { expectedMatchId: this.matchId })
    this.emit('incoming', message)
    return message
  }
}

module.exports = { TransportServer }
