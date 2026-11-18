'use strict'

const { EventEmitter } = require('events')

class BotConnection extends EventEmitter {
  constructor(options = {}) {
    super()
    if (!options.username || !options.host || !options.version) {
      throw new TypeError('username, host, and version are required')
    }
    this.options = { ...options }
    this.bot = null
    this.state = 'disconnected'
    this.createBot = options.createBot
  }

  async connect() {
    if (typeof this.createBot !== 'function') {
      throw new Error('A Mineflayer createBot function must be provided')
    }
    this.state = 'connecting'
    this.bot = await Promise.resolve(this.createBot({
      username: this.options.username,
      host: this.options.host,
      port: this.options.port,
      version: this.options.version,
      auth: this.options.auth
    }))
    this.bot.once('login', () => {
      this.state = 'connected'
      this.emit('connected', this.bot)
    })
    this.bot.on('end', (reason) => {
      this.state = 'disconnected'
      this.emit('disconnected', reason)
    })
    this.bot.on('error', (error) => this.emit('error', error))
    return this.bot
  }

  disconnect(reason = 'requested') {
    if (this.bot && typeof this.bot.quit === 'function') this.bot.quit(reason)
    this.state = 'disconnected'
  }
}

module.exports = { BotConnection }
