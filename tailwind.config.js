import defaultTheme from 'tailwindcss/defaultTheme';
import forms from '@tailwindcss/forms';

/** @type {import('tailwindcss').Config} */
export default {
    content: [
        './vendor/laravel/framework/src/Illuminate/Pagination/resources/views/*.blade.php',
        './storage/framework/views/*.php',
        './resources/views/**/*.blade.php',
    ],

    theme: {
        extend: {
            fontFamily: {
                sans: ['"Space Grotesk"', ...defaultTheme.fontFamily.sans],
            },
            colors: {
                terminal: {
                    bg: '#0b1221',
                    panel: '#0f172a',
                    accent: '#38bdf8',
                    success: '#22c55e',
                    danger: '#ef4444',
                    warn: '#f59e0b',
                },
            },
        },
    },

    plugins: [forms],
};
