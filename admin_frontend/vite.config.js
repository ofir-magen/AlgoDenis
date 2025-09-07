import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// אין צורך בהגדרות מיוחדות; אם תרצה בסיס שונה לפריסה שים base
export default defineConfig({
  plugins: [react()],
})
