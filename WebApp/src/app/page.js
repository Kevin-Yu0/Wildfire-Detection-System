"use client";

import { useEffect, useMemo, useState } from "react";
import { GoogleMap, Marker, InfoWindow, useLoadScript } from "@react-google-maps/api";
import { supabase } from "../lib/supabaseClient";

export default function Home() {
  const [rows, setRows] = useState([]);
  const [selected, setSelected] = useState(null);

  // Filters
  const [fireOnly, setFireOnly] = useState(false);
  const [fromDT, setFromDT] = useState("");
  const [toDT, setToDT] = useState("");
  const [latMin, setLatMin] = useState("");
  const [latMax, setLatMax] = useState("");
  const [lngMin, setLngMin] = useState("");
  const [lngMax, setLngMax] = useState("");

  const { isLoaded } = useLoadScript({
    googleMapsApiKey: process.env.NEXT_PUBLIC_GOOGLE_MAPS_KEY,
  });

  const mapCenter = useMemo(() => ({ lat: 36.5, lng: -119.5 }), []);

  // Fire detection helper
  const isFire = (v) => Number(v) === 1;


  // Fire icon
  const fireIcon = useMemo(() => {
    if (!isLoaded) return undefined;
    return {
      url: "https://maps.google.com/mapfiles/kml/shapes/firedept.png",
      scaledSize: new window.google.maps.Size(32, 32),
    };
  }, [isLoaded]);

  // Convert datetime-local → ISO
  const toISO = (dtLocal) => {
    if (!dtLocal) return null;
    return new Date(dtLocal).toISOString();
  };

  async function loadData() {
    let q = supabase
      .from("Wildfire_Sensor_Data")
      .select(
        'created_at, "Lat", "Long", "Temperature", "Humidity", "Pressure", "CO", "CO2", "Timestamp", "Fire"'
      )
      .order("created_at", { ascending: false })
      .limit(500);

    // Time window filter
    const fromISO = toISO(fromDT);
    const toISOv = toISO(toDT);

    if (fromISO) q = q.gte("created_at", fromISO);
    if (toISOv) q = q.lte("created_at", toISOv);

    // Fire-only filter
    if (fireOnly) {
      q = q.eq("Fire", 1);
    }

    // Bounding box filter
    if (latMin !== "") q = q.gte("Lat", Number(latMin));
    if (latMax !== "") q = q.lte("Lat", Number(latMax));
    if (lngMin !== "") q = q.gte("Long", Number(lngMin));
    if (lngMax !== "") q = q.lte("Long", Number(lngMax));

    const { data, error } = await q;

    if (error) {
      console.error("Supabase error:", error);
      return;
    }

    setRows(data ?? []);
  }

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!isLoaded) {
    return <div style={{ padding: 20 }}>Loading map...</div>;
  }

  return (
    <div style={{ width: "100vw", height: "100vh", position: "relative" }}>
      {/* MAP */}
      <div style={{ position: "absolute", inset: 0 }}>
        <GoogleMap mapContainerStyle={{ width: "100%", height: "100%" }} center={mapCenter} zoom={6}>
          {rows.map((r, i) => {
            const lat = Number(r.Lat);
            const lng = Number(r.Long);

            if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;

            return (
              <Marker
                key={r.created_at + "-" + i}
                position={{ lat, lng }}
                icon={isFire(r.Fire) ? fireIcon : undefined}
                onClick={() => setSelected(r)}
              />
            );
          })}

          {selected && (
            <InfoWindow
              position={{
                lat: Number(selected.Lat),
                lng: Number(selected.Long),
              }}
              onCloseClick={() => setSelected(null)}
            >
              <div style={{ color: "black", minWidth: 220 }}>
                <h3 style={{ margin: "0 0 8px 0" }}>Wildfire Sensor</h3>

                <p style={{ margin: "0 0 6px 0" }}>
                  Status:{" "}
                  <span
                    style={{
                      color: isFire(selected.Fire) ? "red" : "green",
                      fontWeight: 700,
                    }}
                  >
                    {isFire(selected.Fire) ? "🔥 FIRE" : "Normal"}
                  </span>
                </p>

                <p style={{ margin: "0 0 6px 0" }}>Temperature: {selected.Temperature}</p>
                <p style={{ margin: "0 0 6px 0" }}>Humidity: {selected.Humidity}</p>
                <p style={{ margin: "0 0 6px 0" }}>CO₂: {selected.CO2}</p>

                <p style={{ margin: "0", fontSize: 12, color: "#555" }}>
                  created_at: {selected.created_at}
                </p>
              </div>
            </InfoWindow>
          )}
        </GoogleMap>
      </div>

      {/* FILTER PANEL */}
      <div style={{ position: "absolute", top: 12, left: 12, zIndex: 999999 }}>
        <div
          style={{
            width: 340,
            background: "white",
            color: "black",
            padding: 12,
            borderRadius: 12,
            boxShadow: "0 10px 30px rgba(0,0,0,0.2)",
            fontSize: 13,
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <strong>Filters</strong>
            <button
              onClick={loadData}
              style={{
                padding: "6px 10px",
                borderRadius: 8,
                border: "1px solid #ddd",
                background: "#f7f7f7",
                cursor: "pointer",
              }}
            >
              Apply / Refresh
            </button>
          </div>

          <div style={{ marginTop: 10 }}>
            <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input
                type="checkbox"
                checked={fireOnly}
                onChange={(e) => setFireOnly(e.target.checked)}
              />
              Fire only
            </label>
          </div>

          <div style={{ marginTop: 10 }}>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>Time Range</div>
            <div style={{ display: "grid", gap: 6 }}>
              <label>
                From:
                <input
                  type="datetime-local"
                  value={fromDT}
                  onChange={(e) => setFromDT(e.target.value)}
                  style={{ width: "100%" }}
                />
              </label>

              <label>
                To:
                <input
                  type="datetime-local"
                  value={toDT}
                  onChange={(e) => setToDT(e.target.value)}
                  style={{ width: "100%" }}
                />
              </label>
            </div>
          </div>

          <div style={{ marginTop: 10 }}>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>Location Bounds</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
              <input placeholder="Lat min" value={latMin} onChange={(e) => setLatMin(e.target.value)} />
              <input placeholder="Lat max" value={latMax} onChange={(e) => setLatMax(e.target.value)} />
              <input placeholder="Lng min" value={lngMin} onChange={(e) => setLngMin(e.target.value)} />
              <input placeholder="Lng max" value={lngMax} onChange={(e) => setLngMax(e.target.value)} />
            </div>

            <div style={{ marginTop: 6, color: "#666" }}>
              CA bounds tip: Lat 32–42, Lng -125–-114
            </div>
          </div>

          <div style={{ marginTop: 10 }}>
            Showing: <strong>{rows.length}</strong> rows
          </div>
        </div>
      </div>
    </div>
  );
}
