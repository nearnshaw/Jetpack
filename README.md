# Retro Rocket Jetpack — smart wearable

An `upper_body` smart wearable: a white-and-orange racing suit with a retro twin-rocket jetpack.
Press **F** to fire the thrusters. Hold it to keep climbing until the fuel bar runs dry; the thrusters
then stay locked until the bar refills to 25%.

While thrusting, the wearer plays an upper-body scene emote that carries the exhaust as emote props, so nearby
players see it too. The exhaust is smoke puffs only, with no flame cone: emote props hang off the avatar's root
rather than a bone, and the upper-body mask leaves the hips to the Explorer's jump animation, so the pack can sit
5-6 cm off where the puffs were baked, and a crisp flame showed that gap. The puffs are born 2.5 cm above each
nozzle exit and drift at most 22 cm below it. Since rising straight up and rising while steering hold the pack
differently, there are two variants with the same avatar clip and the puffs baked for each pose:
`jetpack_thrust_emote.glb` (straight up) and `jetpack_thrust_move_emote.glb` (steering). `src/jetpack.ts` swaps
them by horizontal speed.

## Try it out

    npm run start

## Pack & publish

    npm run pack        # -> smart-wearable.zip (must stay under 2 MB)

Then upload `smart-wearable.zip` in the Builder (Collections → New item).

## Files

| Path | What |
| --- | --- |
| `wearable.json` | Wearable metadata (male + female representations) |
| `models/{male,female}/jetpack_suit.glb` | Skinned suit + pack, one per body shape. A small mount shaped to each body's back joins the pack to the suit |
| `assets/emotes/jetpack_thrust{,_move}_emote.glb` | Looping thrust emote, two variants: `Jetpack_Avatar` + `Jetpack_Prop` clips |
| `assets/sounds/jetpack_thrust.mp3` | Thrust loop, played locally (only the wearer hears it; scene emotes can't carry audio) |
| `src/jetpack.ts` | Input, impulses, fuel/cooldown, emote control. Tuning constants at the top |
| `src/ui.tsx` | Fuel bar |
| `blender/` | Build scripts and editable `.blend` files (excluded from the package). `texturing.py` paints the 1024px suit and pack textures (supersampled, with seams, stitching, wear and baked AO) |

## Rebuilding the models

The scripts run headless Blender against the base files of the
[Decentraland Tools add-on](https://github.com/decentraland/dcl-blender-toolkit) (`assets/`):

    B=/Applications/Blender.app/Contents/MacOS/Blender
    T=<dcl-blender-toolkit>/assets
    $B --background $T/AvatarShape_B.blend --python blender/build_wearable.py -- male   blender/out
    $B --background $T/AvatarShape_A.blend --python blender/build_wearable.py -- female blender/out
    $B --background $T/Avatar_File.blend   --python blender/build_emote.py    -- blender/out blender/out/info_male.json
    $B --background $T/Avatar_File.blend   --python blender/build_emote.py    -- blender/out blender/out/info_male.json move
    $B --background blender/out/jetpack_suit_male.blend --python blender/render_wearable.py -- blender/out/renders "$PWD/thumbnail.png"

Then copy `blender/out/jetpack_suit_{male,female}.glb` to `models/{male,female}/jetpack_suit.glb`
and `blender/out/jetpack_thrust{,_move}_emote.glb` to `assets/emotes/`.
