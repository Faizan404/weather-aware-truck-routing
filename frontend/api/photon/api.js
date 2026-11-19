// Vercel function: forwards place search to Photon from Vercel's network
// (backend setting PHOTON_URL=https://<app>.vercel.app/api/photon). See ../_forward.js.
import { forwardTo } from '../_forward.js'

export default forwardTo('https://photon.komoot.io/api', 'place search')
