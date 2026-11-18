'use strict'

const { createEnvelope } = require('./protocol')

function positionOf(entity) {
  if (!entity || !entity.position) return null
  return [entity.position.x, entity.position.y, entity.position.z]
}

class ObservationPublisher {
  constructor({ bot, matchId, sender = 'mineflayer-adapter', agentId, publish, intervalMs = 250 }) {
    if (!bot || !matchId || typeof publish !== 'function') {
      throw new TypeError('bot, matchId, and publish are required')
    }
    this.bot = bot
    this.matchId = matchId
    this.sender = sender
    this.agentId = agentId || bot.username || 'unknown'
    this.publish = publish
    this.intervalMs = intervalMs
    this.tick = 0
    this.timer = null
    this.boundPublish = () => this.publishNow()
  }

  start() {
    if (this.timer) return
    this.bot.on('spawn', this.boundPublish)
    this.timer = setInterval(this.boundPublish, this.intervalMs)
    this.publishNow()
  }

  stop() {
    if (this.timer) clearInterval(this.timer)
    this.timer = null
    if (typeof this.bot.removeListener === 'function') {
      this.bot.removeListener('spawn', this.boundPublish)
    }
  }

  buildObservation() {
    const entities = {}
    for (const entity of Object.values(this.bot.entities || {})) {
      if (!entity.username || entity.username === this.bot.username) continue
      const position = positionOf(entity)
      if (position) entities[entity.username] = position
    }
    return {
      agent_id: this.agentId,
      player_id: this.agentId,
      tick: this.tick,
      position: positionOf(this.bot.entity) || [0, 0, 0],
      dimension: this.bot.game && this.bot.game.dimension ? this.bot.game.dimension : 'overworld',
      health: typeof this.bot.health === 'number' ? this.bot.health : 20,
      hunger: typeof this.bot.food === 'number' ? this.bot.food : 20,
      visible_entities: entities,
      inventory: {},
      terrain: {},
      events: []
    }
  }

  publishNow() {
    const message = createEnvelope(
      'observation',
      this.sender,
      this.matchId,
      this.buildObservation(),
      undefined,
      this.tick++
    )
    this.publish(message)
    return message
  }
}

module.exports = { ObservationPublisher, positionOf }
