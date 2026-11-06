import {
  AssetLoad,
  assetLoadLoadingStateSystem,
  AudioSource,
  AvatarAnchorPointType,
  AvatarAttach,
  AvatarMask,
  engine,
  Entity,
  InputAction,
  inputSystem,
  LoadingState,
  Physics,
  Transform
} from '@dcl/sdk/ecs'
import { Vector3 } from '@dcl/sdk/math'
import { stopEmote, triggerSceneEmote } from '~system/RestrictedActions'

// --- tuning -------------------------------------------------------------------------------------
// The character's mass is 1, so an impulse magnitude is the velocity change in m/s.
export const FUEL_SECONDS = 3 // seconds of continuous thrust from a full tank
const REFILL_SECONDS = 4 // time to refill from empty to full
const REFILL_DELAY = 0.6 // pause after releasing F before the tank starts refilling
const OVERHEAT_UNLOCK = 0.25 // after running dry, thrusters stay locked until the tank is back at this fraction
const LAUNCH_IMPULSE = 6 // kick on each new press of F
const LAUNCH_FUEL_COST = 0.3 // seconds of fuel charged per press, so tapping F isn't free
const SUSTAIN_IMPULSE = 0.8 // added every SUSTAIN_INTERVAL while F is held: settles into a ~4-5 m/s climb
const SUSTAIN_INTERVAL = 0.1
const MIN_BURN_SECONDS = 0.4 // keep the exhaust up at least this long, so a quick tap still reads to onlookers

// Emote props hang off the avatar's root, not a bone, and the upper-body mask leaves the hips to the
// Explorer's jump animation, which sits 5-6 cm differently when rising straight up and when rising while
// steering. Each variant bakes the exhaust puffs for one of the two, so swap with horizontal speed.
const EMOTE_SRC = 'assets/emotes/jetpack_thrust_emote.glb' // rising straight up
const EMOTE_SRC_MOVE = 'assets/emotes/jetpack_thrust_move_emote.glb' // rising while steering
const STEER_ON_SPEED = 5.5 // m/s horizontal: the Explorer's rise animation is past halfway to the jog/run pose
const STEER_OFF_SPEED = 4.5
const MIN_VARIANT_SECONDS = 0.3 // don't swap emotes faster than this

// Scene emotes can't carry sound yet (the Explorer drops audio for them), so the emote is silent for
// everyone. Instead, play the thrust sound with an AudioSource: only the wearer hears it.
const LOCAL_SOUND_FALLBACK = true
const SOUND_SRC = 'assets/sounds/jetpack_thrust.mp3'

// --- state (read by the UI) ---------------------------------------------------------------------
export const jetpack = {
  fuel: FUEL_SECONDS,
  overheated: false,
  thrusting: false
}

let burning = false // emote currently playing
let burnTime = 0
let sustainTimer = 0
let sinceRelease = REFILL_DELAY
let soundEntity: Entity | undefined
let steering = false // horizontal speed above the threshold (with hysteresis)
let emoteSrc = '' // variant currently playing
let sinceSwap = 0
let lastPosition: Vector3 | undefined
let horizontalSpeed = 0

function playEmote(src: string) {
  emoteSrc = src
  sinceSwap = 0
  triggerSceneEmote({ src, loop: true, mask: AvatarMask.AM_UPPER_BODY }).catch((e) =>
    console.error('jetpack: emote failed', e)
  )
}

function startBurn() {
  burning = true
  burnTime = 0
  playEmote(steering ? EMOTE_SRC_MOVE : EMOTE_SRC)
  if (soundEntity) AudioSource.getMutable(soundEntity).playing = true
}

function updateSteering(dt: number) {
  const transform = Transform.getOrNull(engine.PlayerEntity)
  if (!transform || dt <= 0) return
  const p = transform.position
  if (lastPosition) {
    const speed = Math.hypot(p.x - lastPosition.x, p.z - lastPosition.z) / dt
    horizontalSpeed += (speed - horizontalSpeed) * Math.min(1, dt * 10) // smooth out frame jitter
  }
  lastPosition = { x: p.x, y: p.y, z: p.z }
  if (!steering && horizontalSpeed > STEER_ON_SPEED) steering = true
  else if (steering && horizontalSpeed < STEER_OFF_SPEED) steering = false
}

function stopBurn() {
  burning = false
  stopEmote({}).catch((e) => console.error('jetpack: stopEmote failed', e))
  if (soundEntity) AudioSource.getMutable(soundEntity).playing = false
}

function jetpackSystem(dt: number) {
  updateSteering(dt)
  const held = inputSystem.isPressed(InputAction.IA_SECONDARY)
  const canFire = !jetpack.overheated && jetpack.fuel > 0

  if (held && canFire) {
    if (!jetpack.thrusting) {
      // new press: launch kick
      jetpack.thrusting = true
      jetpack.fuel = Math.max(0, jetpack.fuel - LAUNCH_FUEL_COST)
      sustainTimer = 0
      Physics.applyImpulseToPlayer(Vector3.Up(), LAUNCH_IMPULSE)
      if (!burning) startBurn()
    }
    jetpack.fuel = Math.max(0, jetpack.fuel - dt)
    sustainTimer += dt
    while (sustainTimer >= SUSTAIN_INTERVAL) {
      sustainTimer -= SUSTAIN_INTERVAL
      Physics.applyImpulseToPlayer(Vector3.Up(), SUSTAIN_IMPULSE)
    }
    sinceRelease = 0
    if (jetpack.fuel <= 0) {
      jetpack.overheated = true
      jetpack.thrusting = false
    }
  } else {
    jetpack.thrusting = false
    sinceRelease += dt
    if (sinceRelease >= REFILL_DELAY) {
      jetpack.fuel = Math.min(FUEL_SECONDS, jetpack.fuel + (dt * FUEL_SECONDS) / REFILL_SECONDS)
    }
    if (jetpack.overheated && jetpack.fuel >= FUEL_SECONDS * OVERHEAT_UNLOCK) {
      jetpack.overheated = false
    }
  }

  if (burning) {
    burnTime += dt
    sinceSwap += dt
    if (!jetpack.thrusting && burnTime >= MIN_BURN_SECONDS) stopBurn()
    else {
      const wanted = steering ? EMOTE_SRC_MOVE : EMOTE_SRC
      if (wanted !== emoteSrc && sinceSwap >= MIN_VARIANT_SECONDS) playEmote(wanted)
    }
  }
}

// Fetch the emotes and the sound up front, so the first thrust doesn't wait on a download
function preloadAssets() {
  const preloader = engine.addEntity()
  const emotes = [EMOTE_SRC, EMOTE_SRC_MOVE]
  const assets = LOCAL_SOUND_FALLBACK ? [...emotes, SOUND_SRC] : emotes
  AssetLoad.create(preloader, { assets })
  assetLoadLoadingStateSystem.registerAssetLoadLoadingStateEntity(preloader, ({ asset, currentState }) => {
    if (currentState === LoadingState.FINISHED_WITH_ERROR || currentState === LoadingState.NOT_FOUND) {
      console.error('jetpack: failed to preload', asset, currentState)
    }
  })
}

export function setupJetpack() {
  preloadAssets()
  if (LOCAL_SOUND_FALLBACK) {
    soundEntity = engine.addEntity()
    Transform.create(soundEntity)
    AvatarAttach.create(soundEntity, { anchorPointId: AvatarAnchorPointType.AAPT_POSITION })
    AudioSource.create(soundEntity, { audioClipUrl: SOUND_SRC, loop: true, playing: false, volume: 0.8 })
  }
  engine.addSystem(jetpackSystem)
}
