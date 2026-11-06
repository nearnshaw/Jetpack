import ReactEcs, { ReactEcsRenderer, UiEntity, Label } from '@dcl/sdk/react-ecs'
import { Color4 } from '@dcl/sdk/math'
import { FUEL_SECONDS, jetpack } from './jetpack'

const ORANGE = Color4.fromHexString('#FF6A1FFF')
const RED = Color4.fromHexString('#E8402AFF')
const WHITE = Color4.fromHexString('#F4F2EEFF')
const TRACK = Color4.fromHexString('#2A2730CC')
const PANEL = Color4.fromHexString('#14121699')

const BAR_WIDTH = 320

export function setupUi() {
  ReactEcsRenderer.setUiRenderer(uiMenu, { virtualWidth: 1920, virtualHeight: 1080 })
}

// Fuel gauge, bottom centre: orange while usable, red while the thrusters cool down after running dry
export const uiMenu = () => {
  const fraction = jetpack.fuel / FUEL_SECONDS
  const status = jetpack.overheated ? 'OVERHEATED' : jetpack.thrusting ? 'THRUST' : 'F  TO FLY'
  return (
    <UiEntity
      uiTransform={{
        width: '100%',
        height: '100%',
        positionType: 'absolute',
        justifyContent: 'flex-end',
        alignItems: 'center',
        padding: { bottom: 150 }
      }}
    >
      <UiEntity
        uiTransform={{ width: BAR_WIDTH + 24, flexDirection: 'column', alignItems: 'center', padding: 10 }}
        uiBackground={{ color: PANEL }}
      >
        <UiEntity uiTransform={{ width: BAR_WIDTH, height: 26, justifyContent: 'space-between', flexDirection: 'row' }}>
          <Label value="JETPACK" fontSize={18} color={WHITE} uiTransform={{ height: 26 }} />
          <Label value={status} fontSize={18} color={jetpack.overheated ? RED : ORANGE} uiTransform={{ height: 26 }} />
        </UiEntity>
        <UiEntity uiTransform={{ width: BAR_WIDTH, height: 14, margin: { top: 4 } }} uiBackground={{ color: TRACK }}>
          <UiEntity
            uiTransform={{ width: Math.max(0, Math.round(BAR_WIDTH * fraction)), height: '100%' }}
            uiBackground={{ color: jetpack.overheated ? RED : ORANGE }}
          />
        </UiEntity>
      </UiEntity>
    </UiEntity>
  )
}
