import { setupJetpack } from './jetpack'
import { setupUi } from './ui'


export function main() {
    // Smart wearable: runs as a portable experience for the player wearing the jetpack
    setupJetpack()
    setupUi()
}
