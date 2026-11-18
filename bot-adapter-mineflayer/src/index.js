'use strict'

const { ActionDispatcher } = require('./action_dispatcher')
const { BotConnection } = require('./bot_connection')
const { MovementDriver } = require('./movement_driver')
const { ObservationPublisher } = require('./observation_publisher')
const { TransportServer } = require('./transport_server')

function createAdapter(options = {}) {
  const transport = options.transport || new TransportServer({
    matchId: options.matchId,
    sender: options.sender || 'mineflayer-adapter'
  })
  const connection = new BotConnection({
    username: options.username,
    host: options.host,
    port: options.port,
    version: options.version || '1.21.11',
    auth: options.auth,
    createBot: options.createBot
  })

  let publisher = null
  let dispatcher = null
  let movement = null
  connection.on('connected', (bot) => {
    movement = new MovementDriver(bot, {
      pathfinder: options.pathfinder,
      goalFactory: options.goalFactory
    })
    publisher = new ObservationPublisher({
      bot,
      matchId: options.matchId,
      agentId: options.agentId || options.username,
      publish: (message) => transport.send(message)
    })
    dispatcher = new ActionDispatcher({
      bot,
      matchId: options.matchId,
      publish: (message) => transport.send(message),
      movementDriver: movement
    })
    publisher.start()
    transport.on('incoming', (message) => {
      if (dispatcher) dispatcher.dispatch(message)
    })
  })

  return {
    connection,
    transport,
    get dispatcher() { return dispatcher },
    get publisher() { return publisher },
    start() {
      transport.start()
      return connection.connect()
    },
    stop() {
      if (publisher) publisher.stop()
      transport.stop()
      connection.disconnect()
    }
  }
}

module.exports = {
  createAdapter,
  ActionDispatcher,
  BotConnection,
  MovementDriver,
  ObservationPublisher,
  TransportServer
}
