'use strict'

function configurePathfinder(bot, options = {}) {
  if (!bot) throw new TypeError('bot is required')
  if (!options.pathfinderModule) {
    throw new Error('pathfinderModule is required for Mineflayer pathfinding')
  }
  const { pathfinder, Movements, goals } = options.pathfinderModule
  if (typeof bot.loadPlugin !== 'function' || typeof pathfinder !== 'function') {
    throw new Error('Invalid pathfinder module')
  }
  bot.loadPlugin(pathfinder)
  const movements = Movements ? new Movements(bot) : null
  if (movements && bot.pathfinder && typeof bot.pathfinder.setMovements === 'function') {
    bot.pathfinder.setMovements(movements)
  }
  return {
    pathfinder: bot.pathfinder,
    goalFactory: goals && goals.GoalNear
      ? (x, y, z) => new goals.GoalNear(x, y, z, 1)
      : null
  }
}

module.exports = { configurePathfinder }
