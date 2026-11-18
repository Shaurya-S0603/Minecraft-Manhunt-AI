'use strict'

class ConnectionHealth {
  constructor(timeoutMs = 5000, clock = () => Date.now()) {
    if (timeoutMs <= 0) throw new TypeError('timeoutMs must be positive')
    this.timeoutMs = timeoutMs
    this.clock = clock
    this.lastHeartbeat = null
  }

  record(heartbeat) {
    this.lastHeartbeat = { ...heartbeat, receivedAt: this.clock() }
  }

  isHealthy(now = this.clock()) {
    return Boolean(this.lastHeartbeat && now - this.lastHeartbeat.receivedAt <= this.timeoutMs)
  }

  status(now = this.clock()) {
    return this.isHealthy(now) ? 'healthy' : 'stale'
  }
}

module.exports = { ConnectionHealth }
