"use client";

import { useEffect, useMemo, useState } from "react";
import { GoogleMap, Marker, InfoWindow, useLoadScript } from "@react-google-maps/api";
import { supabase } from "../lib/supabaseClient";

export default function Home() {
  const [rows, setRows] = useState([]);
  const [selected, setSelected] = useState(null);

  const { isLoaded } = useLoadScript({
    googleMapsApiKey: process.env.NEXT_PUBLIC_GOOGLE_MAPS_KEY,
  });

  const center = useMemo(() => ({ lat: 36.5, lng: -119.5 }), []);
  const mapStyle = { width: "100vw", height: "100vh" };

  useEffect(() => {
    async function loadData() {
      const { data, error } = await supabase
        .from("Wildfire_Sensor_Data")
        .select(
          'created_at, "Lat", "Long", "Temperature", "Humidity", "Pressure", "CO", "CO2", "Timestamp", "Fire"'
        )
        .order("created_at", { ascending: false })
        .limit(100);

      if (error) {
        console.error(error);
        return;
      }
      setRows(data ?? []);
    }

    loadData();
  }, []);

  if (!isLoaded) return <div style={{ padding: 20 }}>Loading map...</div>;

  const isFire = (v) => String(v).toLowerCase() === "fire";

  const fireIcon = {
    url: "https://maps.google.com/mapfiles/kml/shapes/firedept.png",
    scaledSize: new window.google.maps.Size(32, 32),
  };

  return (
    <GoogleMap mapContainerStyle={mapStyle} center={center} zoom={6}>
      {rows.map((r, i) =>
        r.Lat && r.Long ? (
          <Marker
            key={i}
            position={{ lat: r.Lat, lng: r.Long }}
            icon={isFire(r.Fire) ? fireIcon : undefined}
            onClick={() => setSelected(r)}
          />
        ) : null
      )}

{selected && (
  <InfoWindow
    position={{ lat: selected.Lat, lng: selected.Long }}
    onCloseClick={() => setSelected(null)}
  >
    <div style={{ color: "black", minWidth: 200, fontSize: 14 }}>
      <h3 style={{ margin: "0 0 8px 0" }}>Wildfire Sensor</h3>

      <p style={{ margin: "0 0 6px 0" }}>
        Status:{" "}
        <span
          style={{
            color: isFire(selected.Fire) ? "red" : "green",
            fontWeight: "700",
          }}
        >
          {isFire(selected.Fire) ? "🔥 FIRE" : "Normal"}
        </span>
      </p>

      <p style={{ margin: "0 0 6px 0" }}>
        Temperature: {selected.Temperature}
      </p>

      <p style={{ margin: "0 0 6px 0" }}>
        Humidity: {selected.Humidity}
      </p>

      <p style={{ margin: "0 0 6px 0" }}>
        CO₂: {selected.CO2}
      </p>

      <p style={{ margin: "0 0 0 0", fontSize: 12, color: "#555" }}>
        Time: {selected.Timestamp}
      </p>
    </div>
  </InfoWindow>
)}

    </GoogleMap>
  );
}
