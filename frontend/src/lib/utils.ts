import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatTime(value: string | null | undefined): string {
  if (!value) return "Timestamp unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Timestamp unavailable";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
    timeZoneName: "short",
  }).format(date);
}

export function sourceUrl(reference: string): string | null {
  try {
    const url = new URL(reference);
    const hosts = [
      "api.weather.gov",
      "www.weather.gov",
      "waterdata.usgs.gov",
      "waterservices.usgs.gov",
      "api.waterdata.usgs.gov",
    ];
    return url.protocol === "https:" &&
      hosts.includes(url.hostname) &&
      !url.username &&
      !url.password
      ? url.href
      : null;
  } catch {
    return null;
  }
}
