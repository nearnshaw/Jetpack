/**
 * EDIT DECISION LISTS: one entry per post video. The composition id is the post id (promote/posts.json),
 * so `npx remotion render footage-02 ../videos/footage-02.mp4` renders that post's video.
 * All times are seconds from the start of the video. Paths are relative to public/, which links to the
 * kit's folders: images/ (renders, keyart, social), logo/, footage/ (recordings), clips/ (Blender camera
 * moves), music/ (creator-supplied, licensed).
 *
 * Sources, best first:
 *   { video: "footage/wind-take2.mp4", trimStart: 3.2 }   a recording from the Explorer
 *   { video: "clips/hero.mp4" }                           render_shots.py -- clip <shot>
 *   { image: "images/renders/hero.png", move: "push" }    a kit still with slow camera motion
 *   { placeholder: "RECORD: the turbine spinning up" }     nothing exists yet (shows a labelled slate)
 */
export type Source =
  | { video: string; trimStart?: number; rate?: number; focus?: [number, number] }
  | { image: string; move?: "push" | "pull" | "left" | "right" | "up" | "down"; focus?: [number, number] }
  | { placeholder: string };

/** How a shot arrives: hard cut, cut + camera slam, white flash, dip from black, horizontal whip. */
export type Fx = "cut" | "punch" | "flash" | "dip" | "whip";

export type Shot = {
  from: number;
  to: number;
  src: Source;
  fx?: Fx;
  /** Small lower-third label for the whole shot (a mechanic, a UI callout). */
  caption?: string;
  /** CSS filter for the look, e.g. "saturate(0.7) contrast(1.15)". */
  grade?: string;
};

export type Card = {
  /** Use \n for line breaks. About 6 words per card, verbatim lines from the post. */
  text: string;
  from: number;
  to: number;
  /** true: over the picture; false (default): on black, between shots. */
  over?: boolean;
  size?: "md" | "lg" | "xl";
  /** "text" (default), "accent" (brand.accent from posts.json) or any CSS colour. */
  color?: string;
  pos?: "center" | "lower" | "upper";
  /** fade: slow and creeping; slam: lands on a beat. */
  anim?: "fade" | "slam";
};

export type EndCard = {
  from: number;
  /** Transparent wordmark or the lockup on black, e.g. "logo/<slug>_lockup_on_black.png". */
  logo: string;
  /** One line under the logo: the tagline, "Coming soon", a date. */
  line?: string;
  /** The jump link, or "" / omitted when not published. */
  link?: string;
  /** Optional key art shown blurred behind the logo. */
  backdrop?: string;
};

export type Edit = {
  /** Post id from posts.json; becomes videos/<id>.mp4. Letters, digits and dashes only. */
  id: string;
  /** Total length in seconds. Footage posts 6-15 s; a trailer at most 30 s. */
  duration: number;
  shots: Shot[];
  cards: Card[];
  end?: EndCard;
  /** Only the scene's own audio or a file the creator supplied with its licence. Never downloaded music. */
  music?: { file: string; volume?: number; fadeOut?: number; trimStart?: number; loop?: boolean } | null;
  /** One-shot sounds at a given second (a stinger, a chime, an intercom line), same sourcing rule. */
  sounds?: { file: string; at: number; volume?: number }[];
  /** Also register <id>-9x16 (1080x1920) for reels and stories. */
  vertical?: boolean;
};

const GRADE = "brightness(1.12) contrast(1.08) saturate(1.05)";

export const EDITS: Edit[] = [
  // Marketplace video for the Retro Rocket Jetpack smart wearable (Builder: .mp4, max 250 MB).
  // footage/jetpack-flight.mp4 = the creator's Explorer recording (Downloads/jetpack.mov), cropped to 16:9.
  // The glider section of the recording (36-47 s) is the Explorer's own glide, not the wearable: kept out.
  {
    id: "marketplace",
    // Cut on the beat of music/jetpack_theme.wav (tools/make_music.py, 112.5 BPM: beat = 0.5333 s).
    // Cuts at beats 0, 6, 12, 16, 22, 32; ends at beat 38.
    duration: 20.267,
    shots: [
      // 14.2-22.7 s of the recording runs straight through: roof launch, the flight over the lattice building
      { from: 0, to: 3.2, src: { video: "footage/jetpack-flight.mp4", trimStart: 14.2 }, fx: "dip", grade: GRADE },
      { from: 3.2, to: 6.4, src: { video: "footage/jetpack-flight.mp4", trimStart: 17.4 }, fx: "cut", grade: GRADE },
      { from: 6.4, to: 8.533, src: { video: "footage/jetpack-flight.mp4", trimStart: 20.6 }, fx: "cut", grade: GRADE },
      // The liftoff up the white building: the clearest flames in the recording
      { from: 8.533, to: 11.733, src: { video: "footage/jetpack-flight.mp4", trimStart: 8.2 }, fx: "punch", grade: GRADE },
      { from: 11.733, to: 17.067, src: { video: "clips/turntable.mp4" }, fx: "flash", caption: "RACING SUIT + TWIN-ROCKET JETPACK" },
    ],
    cards: [
      // wearable.json description, verbatim
      { text: "PRESS F TO FLY.", from: 0.6, to: 3.0, over: true, size: "xl", pos: "upper", anim: "slam" },
      { text: "HOLD TO CLIMB\nUNTIL THE FUEL BAR RUNS DRY.", from: 3.5, to: 6.3, over: true, size: "lg", pos: "upper", anim: "fade" },
      // README: the flames, sparks and smoke are emote props, so nearby players see them too
      { text: "NEARBY PLAYERS\nSEE THE FLAMES TOO.", from: 8.7, to: 11.65, over: true, size: "lg", pos: "upper", anim: "slam" },
    ],
    end: { from: 17.067, logo: "logo/jetpack_hero.png", line: "RETRO ROCKET JETPACK", link: "SMART WEARABLE", backdrop: "images/backdrop.png" },
    // Original cue synthesised by tools/make_music.py: no samples, nothing downloaded.
    music: { file: "music/jetpack_theme.wav", volume: 0.75, fadeOut: 0.6 },
    // The wearable's own thrust loop (assets/sounds/jetpack_thrust.mp3), under the music where flames show
    sounds: [
      { file: "music/thrust_2.4s.mp3", at: 0.6, volume: 0.5 },
      { file: "music/thrust_2.4s.mp3", at: 9.13, volume: 0.5 },
    ],
  },
];

export const getEdit = (id: string): Edit => {
  const e = EDITS.find((x) => x.id === id);
  if (!e) throw new Error(`No edit with id ${id} in src/edits.ts`);
  return e;
};
