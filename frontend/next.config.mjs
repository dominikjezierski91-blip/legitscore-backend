/** @type {import("next").NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async redirects() {
    return [
      {
        source: "/",
        destination: "/analyze",
        permanent: false,
      },
    ];
  },
};

export default nextConfig;

