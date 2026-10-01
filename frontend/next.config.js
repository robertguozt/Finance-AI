/** @type {import('next').NextConfig} */
const nextConfig = {
  swcMinify: true,
  compiler: {
    removeConsole: process.env.NODE_ENV === 'production',
  },
  experimental: {
    optimizeCss: true,
  },
  
  pageExtensions: ['tsx', 'ts', 'jsx', 'js'], 
  trailingSlash: true,
  skipTrailingSlashRedirect: true,
}

module.exports = nextConfig
