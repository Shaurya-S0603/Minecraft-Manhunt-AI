'use strict'

const assert = require('assert')
const { EventEmitter } = require('events')
const { ActionDispatcher } = require('../src/action_dispatcher')
const { ObservationPublisher } = require('../src/observation_publisher')
const { TransportServer } = require('../src/transport_server')
const { validateMessage } = require('../src/protocol')

function fakeBot() {
  const bot = new EventEmitter()
  bot.username = 'bot-1'
  bot.entities = {}
  bot.entity = { position: { x: 1, y: 64, z: 2 } }
  bot.game = { dimension: 'overworld' }
  bot.health = 20
  bot.food = 20
  bot.setControlState = () => {}
  return bot
}

async function main() {
  const bot = fakeBot()
  const published = []
  const publisher = new ObservationPublisher({
    bot,
    matchId: 'match-1',
    publish: (message) => published.push(message)
  })
  publisher.publishNow()
  assert.strictEqual(published[0].message_type, 'observation')
  assert.strictEqual(published[0].payload.position[0], 1)

  const dispatcher = new ActionDispatcher({
    bot,
    matchId: 'match-1',
    publish: (message) => published.push(message),
    movementDriver: { stop() {}, moveTo: async () => {} }
  })
  dispatcher.setPhase('ACTIVE')
  const result = await dispatcher.dispatch({
    contract_version: '1',
    message_type: 'action_request',
    sender: 'ai-controller',
    match_id: 'match-1',
    request_id: 'request-1',
    payload: { action: 'stop' }
  })
  assert.strictEqual(result.message_type, 'action_ack')
  assert.strictEqual(result.payload.status, 'succeeded')

  const transport = new TransportServer({ matchId: 'match-1' })
  transport.start()
  transport.send(published[0])
  assert.strictEqual(validateMessage(published[0]).match_id, 'match-1')
  console.log('adapter tests passed')
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
