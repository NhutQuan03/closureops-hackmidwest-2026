import { useEffect, useRef, useState } from "react";
import { Crosshair, Layers, LoaderCircle, MapPin } from "lucide-react";
import type { Map as MapLibreMap } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import type { Facility } from "../api/schemas";
import { formatTime } from "../lib/utils";
import { Card, CardHeader } from "./ui/card";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import "maplibre-gl/dist/maplibre-gl.css";

interface Props {
  facilities: Facility[];
  selected: Facility | null;
  onSelect: (id: string) => void;
}
export default function FacilityMap({ facilities, selected, onSelect }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const selectRef = useRef(onSelect);
  const [status, setStatus] = useState<"loading" | "ready" | "unavailable">(
    "loading",
  );
  selectRef.current = onSelect;
  const referenceFacility = facilities.find(
    (f) => f.id === "jefferson-research",
  );
  useEffect(() => {
    if (!container.current || !referenceFacility) return;
    const element = container.current;
    let disposed = false;
    let tileError = false;
    setStatus("loading");
    let timer: ReturnType<typeof setTimeout>;
    let marker: import("maplibre-gl").Marker | undefined;
    void import("maplibre-gl")
      .then(({ Map, Marker, NavigationControl, setWorkerUrl }) => {
        if (disposed) return;
        // Vite must bundle the worker explicitly for vector tile rendering.
        setWorkerUrl(workerUrl);
        const map = new Map({
          container: element,
          center: [
            referenceFacility.coordinates.longitude,
            referenceFacility.coordinates.latitude,
          ],
          zoom: 8.3,
          attributionControl: { compact: true },
          // Basemap only: no hazard/risk data. MapLibre retains the style's attribution.
          style: "https://tiles.openfreemap.org/styles/dark",
        });
        mapRef.current = map;
        map.addControl(
          new NavigationControl({ showCompass: false }),
          "top-left",
        );
        map.scrollZoom.disable();
        const markerButton = document.createElement("button");
        markerButton.type = "button";
        markerButton.className = "facility-marker";
        markerButton.setAttribute(
          "aria-label",
          `Select ${referenceFacility.name}, SIMULATED DEMO location`,
        );
        markerButton.textContent = "J";
        markerButton.addEventListener("click", () =>
          selectRef.current(referenceFacility.id),
        );
        marker = new Marker({ element: markerButton })
          .setLngLat([
            referenceFacility.coordinates.longitude,
            referenceFacility.coordinates.latitude,
          ])
          .addTo(map);
        map.on("error", () => {
          tileError = true;
          // Keep the synthetic marker and facility selection usable if the
          // style, vector tiles, sprites, or glyphs cannot be loaded.
          if (!disposed) setStatus("unavailable");
        });
        map.on("idle", () => {
          if (!disposed && !tileError && map.areTilesLoaded()) {
            clearTimeout(timer);
            setStatus("ready");
          }
        });
        timer = setTimeout(() => {
          if (!disposed) setStatus("unavailable");
        }, 10000);
      })
      .catch(() => {
        if (!disposed) setStatus("unavailable");
      });
    return () => {
      disposed = true;
      clearTimeout(timer);
      marker?.remove();
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, [referenceFacility]);
  return (
    <Card className="map-card" aria-labelledby="map-title">
      <CardHeader>
        <h2 id="map-title">
          <MapPin size={17} /> Facility risk map
        </h2>
        <Badge tone="neutral">
          <Layers size={11} /> REFERENCE ONLY
        </Badge>
      </CardHeader>
      <div className="map-viewport">
        <div
          ref={container}
          className="map-canvas"
          aria-label="Interactive reference location map"
        />
        <div className="map-context">
          <span>MISSOURI · MIDWEST</span>
          <Badge tone="purple">SIMULATED DEMO</Badge>
        </div>
        <Button
          variant="outline"
          size="icon"
          className="map-recenter"
          aria-label="Recenter facility map"
          disabled={!referenceFacility || status === "unavailable"}
          onClick={() => {
            if (referenceFacility)
              mapRef.current?.jumpTo({
                center: [
                  referenceFacility.coordinates.longitude,
                  referenceFacility.coordinates.latitude,
                ],
                zoom: 8.3,
              });
          }}
        >
          <Crosshair size={17} />
        </Button>
        {referenceFacility ? (
          <button
            className="map-facility-label"
            onClick={() => onSelect(referenceFacility.id)}
          >
            <span className="map-label-icon">
              <MapPin size={17} />
            </span>
            <span>
              <strong>{referenceFacility.name}</strong>
              <small>
                {selected?.id === referenceFacility.id
                  ? "Selected"
                  : "Select facility"}{" "}
                · Columbia reference point
              </small>
            </span>
          </button>
        ) : (
          <div className="map-empty">
            <MapPin size={27} />
            <strong>Awaiting facility catalog</strong>
            <span>The map uses the configured synthetic location.</span>
          </div>
        )}
        {referenceFacility && status !== "ready" && (
          <div className="map-state" role="status">
            {status === "loading" ? (
              <>
                <LoaderCircle size={14} className="spin" /> Loading reference
                map tiles…
              </>
            ) : (
              <>
                <Layers size={14} /> Basemap unavailable. Facility coordinates
                remain accessible below.
              </>
            )}
          </div>
        )}
      </div>
      <div className="map-footer">
        <span>
          <i className="location-dot" /> Synthetic location{" "}
          <span className="separator">/</span> Risk unavailable
        </span>
        {selected && (
          <span className="coordinates">
            {selected.coordinates.latitude.toFixed(4)}° N,{" "}
            {Math.abs(selected.coordinates.longitude).toFixed(4)}°{" "}
            {selected.coordinates.longitude < 0 ? "W" : "E"}
          </span>
        )}
      </div>
      <p className="source-note">
        {referenceFacility ? (
          <>
            Source: {referenceFacility.source} ·{" "}
            {formatTime(referenceFacility.source_timestamp)}
          </>
        ) : (
          "Source: facility catalog unavailable · Timestamp unavailable"
        )}
        <br />
        Regional gauges do not establish facility flood exposure.
      </p>
    </Card>
  );
}
