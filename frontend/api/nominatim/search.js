// Vercel function: forwards place search to Nominatim from Vercel's network
// (backend setting NOMINATIM_URL=https://<app>.vercel.app/api/nominatim). See ../_forward.js.
import { forwardTo } from '../_forward.js'

export default forwardTo('https://nominatim.openstreetmap.org/search', 'place search')
