// Shared Tailwind Play CDN config — design tokens for all JobCraft mockups.
// Loaded AFTER the Tailwind CDN script so `tailwind.config` is picked up.
tailwind.config = {
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eef2ff', 100: '#e0e7ff', 600: '#4f46e5', 700: '#4338ca',
        },
        // The one calibrated signal scale: low -> mid -> high.
        signal: { low: '#f43f5e', mid: '#f59e0b', high: '#10b981' },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
    },
  },
};
