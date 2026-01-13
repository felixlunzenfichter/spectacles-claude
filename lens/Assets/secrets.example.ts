// Example secrets - Copy this to secrets.ts and fill in your values
// DO NOT put real secrets in this file

// Device secret - Generate a UUID and share it with your Mac server
// Both the Spectacles client and Mac server must use the SAME secret
// to find each other via the relay server
export const DEVICE_SECRET = "your-uuid-here";

// Relay server URL - The relay server that connects Spectacles to Mac
export const RELAY_URL = "https://your-project.deno.dev";
