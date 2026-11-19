// Vercel function: forwards weather requests to Open-Meteo from Vercel's network
// (backend setting OPEN_METEO_URL=https://<app>.vercel.app/api). See ../_forward.js.
import { forwardTo } from '../_forward.js'

export default forwardTo('https://api.open-meteo.com/v1/forecast', 'weather')
