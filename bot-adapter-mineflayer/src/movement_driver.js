'use strict'

class MovementDriver {
  constructor(bot, options = {}) {
    if (!bot) throw new TypeError('bot is required')
    this.bot = bot
    this.pathfinder = options.pathfinder || bot.pathfinder
    this.goalFactory = options.goalFactory || null
    this.active = false
  }

  stop() {
    if (this.pathfinder && typeof this.pathfinder.stop === 'function') this.pathfinder.stop()
    for (const control of ['forward', 'back', 'left', 'right', 'jump', 'sprint']) {
      if (typeof this.bot.setControlState === 'function') this.bot.setControlState(control, false)
    }
    this.active = false
  }

  async moveTo(target, timeoutMs = 10000) {
    if (!Array.isArray(target) || target.length !== 3 || target.some((value) => !Number.isFinite(value))) {
      throw new TypeError('move-to target must be [x, y, z]')
    }
    if (!this.pathfinder || typeof this.pathfinder.setGoal !== 'function' || !this.goalFactory) {
      throw new Error('Pathfinder integration is not configured')
    }
    this.stop()
    this.active = true
    this.pathfinder.setGoal(this.goalFactory(...target))
    try {
      await new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error('movement timed out')), timeoutMs)
        const done = () => {
          clearTimeout(timer)
          resolve()
        }
        if (typeof this.pathfinder.once !== 'function') {
          clearTimeout(timer)
          reject(new Error('Pathfinder does not expose completion events'))
          return
        }
        this.pathfinder.once('goal_reached', done)
        this.pathfinder.once('path_reset', () => reject(new Error('path reset')))
      })
    } finally {
      this.stop()
    }
  }
}

module.exports = { MovementDriver }
