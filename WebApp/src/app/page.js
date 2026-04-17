"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import {
  GoogleMap,
  Marker,
  InfoWindow,
  useLoadScript,
} from "@react-google-maps/api";
import { supabase } from "../lib/supabaseClient";

/* ── helpers ── */
const isFire = (v) => Number(v) === 1;
const toISO = (dt) => (dt ? new Date(dt).toISOString() : null);
const fmt = (iso) => {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-US", {
    month: "short", day: "numeric", year: "numeric",
    hour: "numeric", minute: "2-digit",
  });
};
const coord = (n) => (n != null ? Number(n).toFixed(4) : "—");

/* ── SVG icons (inline so no extra files needed) ── */
const ExpandIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
    strokeLinecap="round" strokeLinejoin="round">
    <polyline points="15 3 21 3 21 9" /><polyline points="9 21 3 21 3 15" />
    <line x1="21" y1="3" x2="14" y2="10" /><line x1="3" y1="21" x2="10" y2="14" />
  </svg>
);
const ShrinkIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
    strokeLinecap="round" strokeLinejoin="round">
    <polyline points="4 14 10 14 10 20" /><polyline points="20 10 14 10 14 4" />
    <line x1="14" y1="10" x2="21" y2="3" /><line x1="3" y1="21" x2="10" y2="14" />
  </svg>
);

/* ═══════════════════════════════════════════════════════
   COMPONENT
   ═══════════════════════════════════════════════════════ */
export default function Home() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [mapExpanded, setMapExpanded] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);

  /* fire detail modal */
  const [fireDetail, setFireDetail] = useState(null); // the clicked fire row
  const [chartData, setChartData] = useState([]);     // historical data for that location
  const [chartLoading, setChartLoading] = useState(false);
  const [activeChart, setActiveChart] = useState("Temperature"); // which metric to show

  /* chart-specific time filters (inside modal only) */
  const [chartFromDT, setChartFromDT] = useState("");
  const [chartToDT, setChartToDT] = useState("");

  /* sidebar filters (location only — no time range) */
  const [latMin, setLatMin] = useState("");
  const [latMax, setLatMax] = useState("");
  const [lngMin, setLngMin] = useState("");
  const [lngMax, setLngMax] = useState("");

  const { isLoaded } = useLoadScript({
    googleMapsApiKey: process.env.NEXT_PUBLIC_GOOGLE_MAPS_KEY,
  });

  const mapCenter = useMemo(() => ({ lat: 36.5, lng: -119.5 }), []);

  const fireIcon = useMemo(() => {
    if (!isLoaded) return undefined;
    return {
      url: "https://maps.google.com/mapfiles/kml/shapes/firedept.png",
      scaledSize: new window.google.maps.Size(30, 30),
    };
  }, [isLoaded]);

  /* ── fetch ── */
  const loadData = useCallback(async (showSpinner = false) => {
    if (showSpinner) setLoading(true);

    const fields = 'created_at, "Lat", "Long", "Temperature", "Humidity", "Pressure", "CO", "CO2", "Timestamp", "Fire"';

    // Query 1: get latest 500 readings (for table + stats)
    let q = supabase
      .from("Wildfire_Sensor_Data")
      .select(fields)
      .order("created_at", { ascending: false })
      .limit(500);

    if (latMin !== "") q = q.gte("Lat", Number(latMin));
    if (latMax !== "") q = q.lte("Lat", Number(latMax));
    if (lngMin !== "") q = q.gte("Long", Number(lngMin));
    if (lngMax !== "") q = q.lte("Long", Number(lngMax));

    // Query 2: ALWAYS get ALL fire rows (so map never misses a fire)
    const fireQ = supabase
      .from("Wildfire_Sensor_Data")
      .select(fields)
      .eq("Fire", 1);

    const [mainResult, fireResult] = await Promise.all([q, fireQ]);

    if (mainResult.error) console.error("Supabase error:", mainResult.error);
    if (fireResult.error) console.error("Supabase fire query error:", fireResult.error);

    const mainData = mainResult.data ?? [];
    const fireData = fireResult.data ?? [];

    // Merge: add any fire rows not already in mainData
    const mainKeys = new Set(mainData.map((r) => r.created_at));
    const merged = [...mainData];
    for (const fr of fireData) {
      if (!mainKeys.has(fr.created_at)) {
        merged.push(fr);
      }
    }

    setRows(merged);
    setLoading(false);
    setLastUpdated(new Date());
  }, [latMin, latMax, lngMin, lngMax]);

  /* ── auto-refresh: poll every 5 seconds ── */
  useEffect(() => {
    loadData(true); // initial load with spinner
    const interval = setInterval(() => {
      loadData(false); // silent refresh
    }, 5000);
    return () => clearInterval(interval);
  }, [loadData]);

  /* ── Supabase realtime: instant updates on INSERT/UPDATE/DELETE ── */
  useEffect(() => {
    const channel = supabase
      .channel("wildfire-realtime")
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "Wildfire_Sensor_Data" },
        () => {
          loadData(false); // re-fetch on any change
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [loadData]);

  /* ── derived stats ── */
  const stats = useMemo(() => {
    const n = rows.length;
    const fires = rows.filter((r) => isFire(r.Fire)).length;
    const avgTemp = n ? (rows.reduce((s, r) => s + (Number(r.Temperature) || 0), 0) / n).toFixed(1) : "—";
    const maxCO2 = n ? Math.max(...rows.map((r) => Number(r.CO2) || 0)).toFixed(0) : "—";
    const avgHum = n ? (rows.reduce((s, r) => s + (Number(r.Humidity) || 0), 0) / n).toFixed(1) : "—";
    const maxTemp = n ? Math.max(...rows.map((r) => Number(r.Temperature) || 0)).toFixed(1) : "—";
    return { n, fires, avgTemp, maxCO2, avgHum, maxTemp };
  }, [rows]);

  /* ── all fire incidents (for history list) ── */
  const fireHistory = useMemo(() => {
    return rows
      .filter((r) => isFire(r.Fire))
      .sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
  }, [rows]);

  const resetFilters = () => {
    setLatMin(""); setLatMax(""); setLngMin(""); setLngMax("");
  };

  /* ── fetch chart data for a fire location ── */
  const fetchChartData = useCallback(async (row, from, to) => {
    setChartLoading(true);
    const lat = Number(row.Lat);
    const lng = Number(row.Long);

    let q = supabase
      .from("Wildfire_Sensor_Data")
      .select('created_at, "Temperature", "Humidity", "Pressure", "CO", "CO2", "Fire"')
      .gte("Lat", lat - 0.05)
      .lte("Lat", lat + 0.05)
      .gte("Long", lng - 0.05)
      .lte("Long", lng + 0.05)
      .order("created_at", { ascending: true })
      .limit(500);

    // Apply chart time filters
    const f = toISO(from);
    const t = toISO(to);
    if (f) q = q.gte("created_at", f);
    if (t) q = q.lte("created_at", t);

    const { data, error } = await q;
    if (error) console.error("Chart data error:", error);
    setChartData(data ?? []);
    setChartLoading(false);
  }, []);

  /* ── open fire detail modal ── */
  const openFireDetail = useCallback((row) => {
    setFireDetail(row);
    setActiveChart("Temperature");
    setChartFromDT("");
    setChartToDT("");
    fetchChartData(row, "", "");
  }, [fetchChartData]);

  /* ── refresh chart with new time filters ── */
  const refreshChart = useCallback(() => {
    if (fireDetail) {
      fetchChartData(fireDetail, chartFromDT, chartToDT);
    }
  }, [fireDetail, chartFromDT, chartToDT, fetchChartData]);

  const closeFireDetail = () => {
    setFireDetail(null);
    setChartData([]);
    setChartFromDT("");
    setChartToDT("");
  };

  /* ESC to close expanded map or modal */
  useEffect(() => {
    const handler = (e) => {
      if (e.key === "Escape") {
        if (fireDetail) closeFireDetail();
        else setMapExpanded(false);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [fireDetail]);

  /* lock body scroll when map is expanded */
  useEffect(() => {
    document.body.style.overflow = mapExpanded ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [mapExpanded]);

  /* ── loading ── */
  if (!isLoaded) {
    return (
      <div className="loader-screen">
        <div className="spinner" />
        <div style={{ fontFamily: "var(--font-display)", fontSize: 18, color: "var(--navy)" }}>
          Loading Wildfire Dashboard…
        </div>
      </div>
    );
  }

  /* ── shared map element (rendered once, placed in card) ── */
  const mapElement = (
    <GoogleMap
      mapContainerClassName="map-google"
      center={mapCenter}
      zoom={6}
      options={{
        styles: [
          { featureType: "water", stylers: [{ color: "#cad2d9" }] },
          { featureType: "landscape", stylers: [{ color: "#e8e5df" }] },
          { featureType: "poi", stylers: [{ visibility: "off" }] },
          { featureType: "transit", stylers: [{ visibility: "off" }] },
          { featureType: "road", stylers: [{ color: "#d6d1ca" }] },
          { featureType: "administrative", elementType: "labels.text.fill", stylers: [{ color: "#6b7280" }] },
        ],
        disableDefaultUI: false,
        zoomControl: true,
        streetViewControl: false,
        mapTypeControl: false,
        fullscreenControl: false, // we have our own
      }}
    >
      {rows.map((r, i) => {
        const lat = Number(r.Lat);
        const lng = Number(r.Long);
        if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
        if (lat === 0 && lng === 0) return null;
        if (!isFire(r.Fire)) return null; // only show fires on the map
        return (
          <Marker
            key={r.created_at + "-" + i}
            position={{ lat, lng }}
            icon={fireIcon}
            onClick={() => openFireDetail(r)}
          />
        );
      })}

      {selected && (
        <InfoWindow
          position={{ lat: Number(selected.Lat), lng: Number(selected.Long) }}
          onCloseClick={() => setSelected(null)}
        >
          <div className="iw" style={{ minWidth: 230 }}>
            <h4>{isFire(selected.Fire) ? "🔥 Fire Detected" : "✅ Normal Reading"}</h4>
            <p><span className="lbl">Temperature</span> {selected.Temperature}</p>
            <p><span className="lbl">Humidity</span> {selected.Humidity}</p>
            <p><span className="lbl">Pressure</span> {selected.Pressure}</p>
            <p><span className="lbl">CO</span> {selected.CO}</p>
            <p><span className="lbl">CO₂</span> {selected.CO2}</p>
            <p style={{ marginTop: 8, fontSize: 11, color: "#888" }}>{fmt(selected.created_at)}</p>
          </div>
        </InfoWindow>
      )}
    </GoogleMap>
  );

  /* ═══════════════════════════════════════
     RENDER
     ═══════════════════════════════════════ */
  return (
    <>
      {/* ───── NAVBAR ───── */}
      <nav className="navbar">
        <div className="navbar-inner">
          <a href="/" className="navbar-brand">
            <div className="brand-logo-wrap">
              <img src="/emberwatch-logo.png" alt="EmberWatch" />
            </div>
            <span className="brand-text">
              <span className="brand-title">EmberWatch</span>
              <span className="brand-sub">Wildfire Detection System</span>
            </span>
          </a>
          <div className="navbar-links">
            <a href="/" className="active">Incidents</a>
            <a href="#data-table">Data</a>
            <button className="nav-emergency">Emergency? Call 911</button>
          </div>
        </div>
      </nav>

      {/* ───── HERO STATS ───── */}
      <section className="hero">
        <div className="hero-inner">
          <h1 className="fade-in">Current Incidents</h1>
          <p className="hero-sub fade-in d1">
            Live wildfire sensor readings across California — fire detections, temperature,
            CO₂, and environmental data from the sensor network.
          </p>
          <div className="stats-row">
            <div className="stat-pill fade-in d1">
              <div className="stat-val">{stats.n}</div>
              <div className="stat-lbl">Total Readings</div>
            </div>
            <div className="stat-pill alert fade-in d2">
              <div className="stat-val">{stats.fires}</div>
              <div className="stat-lbl">Fire Detections</div>
            </div>
            <div className="stat-pill fade-in d3">
              <div className="stat-val">{stats.avgTemp}°</div>
              <div className="stat-lbl">Avg Temp</div>
            </div>
            <div className="stat-pill fade-in d4">
              <div className="stat-val">{stats.maxCO2}</div>
              <div className="stat-lbl">Peak CO₂</div>
            </div>
            <div className="stat-pill fade-in d5">
              <div className="stat-val">{stats.avgHum}%</div>
              <div className="stat-lbl">Avg Humidity</div>
            </div>
          </div>
        </div>
      </section>

      {/* ───── BODY ───── */}
      <div className="page-body">

        {/* ── TOP ROW: Map + Sidebar ── */}
        <div className="top-row">

          {/* MAP CARD */}
          <div className={`map-card${mapExpanded ? " expanded" : ""}`}>
            {mapElement}

            {/* Toolbar: expand / collapse */}
            <div className="map-toolbar">
              <button
                className="map-btn"
                onClick={() => setMapExpanded(!mapExpanded)}
                title={mapExpanded ? "Shrink map (Esc)" : "Expand map fullscreen"}
              >
                {mapExpanded ? <ShrinkIcon /> : <ExpandIcon />}
                {mapExpanded ? "Close" : "Expand"}
              </button>
            </div>

            {/* Legend */}
            <div className="map-legend">
              <div className="legend-item">
                <span className="legend-dot fire" /> Active Fire Detection
              </div>
            </div>
          </div>

          {/* SIDEBAR */}
          <aside className="sidebar">

            {/* Quick Stats */}
            <div className="card">
              <div className="card-head"><h3>Live Stats</h3></div>
              <div className="card-body">
                <div className="mini-stats">
                  <div className="mini-stat">
                    <div className={`mini-stat-val${stats.fires > 0 ? " danger" : ""}`}>
                      {stats.fires}
                    </div>
                    <div className="mini-stat-lbl">🔥 Fires</div>
                  </div>
                  <div className="mini-stat">
                    <div className="mini-stat-val">{stats.n}</div>
                    <div className="mini-stat-lbl">Readings</div>
                  </div>
                  <div className="mini-stat">
                    <div className="mini-stat-val">{stats.maxTemp}°</div>
                    <div className="mini-stat-lbl">Max Temp</div>
                  </div>
                  <div className="mini-stat">
                    <div className="mini-stat-val">{stats.maxCO2}</div>
                    <div className="mini-stat-lbl">Peak CO₂</div>
                  </div>
                </div>
              </div>
            </div>

            {/* Fire History */}
            <div className="card">
              <div className="card-head">
                <h3>Fire History</h3>
                <span className="badge" style={{ fontSize: 11 }}>
                  {fireHistory.length} incident{fireHistory.length !== 1 ? "s" : ""}
                </span>
              </div>
              <div className="card-body" style={{ padding: 0 }}>
                {fireHistory.length === 0 ? (
                  <div style={{ padding: "24px 18px", textAlign: "center", color: "var(--ash)", fontSize: 13 }}>
                    No fire incidents recorded.
                  </div>
                ) : (
                  <div className="fire-history-list">
                    {fireHistory.map((f, i) => (
                      <button
                        key={f.created_at + "-" + i}
                        className="fh-card"
                        onClick={() => openFireDetail(f)}
                      >
                        <div className="fh-top">
                          <span className="fh-badge">🔥 Incident #{fireHistory.length - i}</span>
                          <span className="fh-arrow">View chart →</span>
                        </div>
                        <div className="fh-date">{fmt(f.created_at)}</div>
                        <div className="fh-grid">
                          <div className="fh-cell">
                            <span className="fh-cell-lbl">Temp</span>
                            <span className="fh-cell-val hot">{f.Temperature ?? "—"}°</span>
                          </div>
                          <div className="fh-cell">
                            <span className="fh-cell-lbl">CO₂</span>
                            <span className="fh-cell-val hot">{f.CO2 ?? "—"}</span>
                          </div>
                          <div className="fh-cell">
                            <span className="fh-cell-lbl">Humidity</span>
                            <span className="fh-cell-val">{f.Humidity ?? "—"}%</span>
                          </div>
                          <div className="fh-cell">
                            <span className="fh-cell-lbl">CO</span>
                            <span className="fh-cell-val">{f.CO ?? "—"}</span>
                          </div>
                        </div>
                        <div className="fh-location">
                          📍 {coord(f.Lat)}, {coord(f.Long)}
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Filters */}
            <div className="card">
              <div className="card-head"><h3>Filters</h3></div>
              <div className="card-body">

                <div className="fg">
                  <span className="fg-label">Location Bounds</span>
                  <div className="fg-row">
                    <input className="fg-input" placeholder="Lat min" value={latMin}
                      onChange={(e) => setLatMin(e.target.value)} />
                    <input className="fg-input" placeholder="Lat max" value={latMax}
                      onChange={(e) => setLatMax(e.target.value)} />
                  </div>
                  <div className="fg-row" style={{ marginTop: 7 }}>
                    <input className="fg-input" placeholder="Lng min" value={lngMin}
                      onChange={(e) => setLngMin(e.target.value)} />
                    <input className="fg-input" placeholder="Lng max" value={lngMax}
                      onChange={(e) => setLngMax(e.target.value)} />
                  </div>
                  <p style={{ fontSize: 11.5, color: "var(--smoke)", margin: "5px 0 0" }}>
                    CA: Lat 32–42 · Lng -125 to -114
                  </p>
                </div>

                <button className="btn-primary" onClick={loadData}>
                  Apply Filters
                </button>
                <button className="btn-ghost" onClick={() => { resetFilters(); setTimeout(loadData, 50); }}>
                  Reset All
                </button>

                <div className="showing-count">
                  Showing <strong>{rows.length}</strong> readings
                  {lastUpdated && (
                    <div style={{ fontSize: 11, color: "var(--smoke)", marginTop: 4, display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}>
                      <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--green)", display: "inline-block", animation: "pulse 2s infinite" }} />
                      Auto-updating · {lastUpdated.toLocaleTimeString()}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </aside>
        </div>

        {/* ── DATA TABLE ── */}
        <div className="table-card" id="data-table">
          <div className="table-top">
            <h2>All Sensor Readings</h2>
            <span className="badge">{rows.length} records</span>
          </div>

          <div className="table-scroll">
            {loading ? (
              <div className="empty-state">
                <div className="spinner" />
                <p>Loading sensor data…</p>
              </div>
            ) : rows.length === 0 ? (
              <div className="empty-state">No readings match current filters.</div>
            ) : (
              <table className="dtbl">
                <thead>
                  <tr>
                    <th>Status</th>
                    <th>Temp</th>
                    <th>Humidity</th>
                    <th>CO₂</th>
                    <th>CO</th>
                    <th>Pressure</th>
                    <th>Location</th>
                    <th>Date</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={r.created_at + "-" + i} onClick={() => setSelected(r)}>
                      <td>
                        {isFire(r.Fire) ? (
                          <span className="status-badge fire"><span className="pulse" /> FIRE</span>
                        ) : (
                          <span className="status-badge ok">Normal</span>
                        )}
                      </td>
                      <td>
                        <span className={`mono${Number(r.Temperature) > 50 ? " hot" : ""}`}>
                          {r.Temperature ?? "—"}
                        </span>
                      </td>
                      <td className="mono">{r.Humidity ?? "—"}</td>
                      <td>
                        <span className={`mono${Number(r.CO2) > 1000 ? " hot" : ""}`}>
                          {r.CO2 ?? "—"}
                        </span>
                      </td>
                      <td className="mono">{r.CO ?? "—"}</td>
                      <td className="mono">{r.Pressure ?? "—"}</td>
                      <td className="coord-cell">{coord(r.Lat)}, {coord(r.Long)}</td>
                      <td className="ts-cell">{fmt(r.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>

      {/* ───── FIRE DETAIL MODAL ───── */}
      {fireDetail && (
        <div className="modal-overlay" onClick={closeFireDetail}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <button className="modal-close" onClick={closeFireDetail}>✕</button>

            {/* Header */}
            <div className="modal-header">
              <div>
                <h2 className="modal-title">🔥 Fire Incident Detail</h2>
                <p className="modal-subtitle">
                  Location: {coord(fireDetail.Lat)}, {coord(fireDetail.Long)} · Detected: {fmt(fireDetail.created_at)}
                </p>
              </div>
            </div>

            {/* Sensor readings at time of fire */}
            <div className="modal-stats">
              <div className="modal-stat">
                <div className="modal-stat-val hot">{fireDetail.Temperature ?? "—"}°</div>
                <div className="modal-stat-lbl">Temperature</div>
              </div>
              <div className="modal-stat">
                <div className="modal-stat-val">{fireDetail.Humidity ?? "—"}%</div>
                <div className="modal-stat-lbl">Humidity</div>
              </div>
              <div className="modal-stat">
                <div className="modal-stat-val hot">{fireDetail.CO2 ?? "—"}</div>
                <div className="modal-stat-lbl">CO₂ ppm</div>
              </div>
              <div className="modal-stat">
                <div className="modal-stat-val">{fireDetail.CO ?? "—"}</div>
                <div className="modal-stat-lbl">CO</div>
              </div>
              <div className="modal-stat">
                <div className="modal-stat-val">{fireDetail.Pressure ?? "—"}</div>
                <div className="modal-stat-lbl">Pressure</div>
              </div>
            </div>

            {/* Time range filter for chart */}
            <div className="chart-time-filter">
              <span className="fg-label" style={{ margin: 0, whiteSpace: "nowrap" }}>Time Range</span>
              <input
                className="fg-input"
                type="datetime-local"
                value={chartFromDT}
                onChange={(e) => setChartFromDT(e.target.value)}
                style={{ flex: 1, minWidth: 170 }}
              />
              <span style={{ color: "var(--ash)", fontSize: 13 }}>to</span>
              <input
                className="fg-input"
                type="datetime-local"
                value={chartToDT}
                onChange={(e) => setChartToDT(e.target.value)}
                style={{ flex: 1, minWidth: 170 }}
              />
              <button className="btn-primary" onClick={refreshChart}
                style={{ width: "auto", padding: "9px 20px", whiteSpace: "nowrap" }}>
                Apply
              </button>
              {(chartFromDT || chartToDT) && (
                <button className="btn-ghost" onClick={() => { setChartFromDT(""); setChartToDT(""); setTimeout(() => { if (fireDetail) fetchChartData(fireDetail, "", ""); }, 50); }}
                  style={{ width: "auto", padding: "9px 14px", marginTop: 0 }}>
                  Clear
                </button>
              )}
            </div>

            {/* Chart tabs */}
            <div className="chart-tabs">
              {["Temperature", "CO2", "Humidity", "CO", "Pressure"].map((metric) => (
                <button
                  key={metric}
                  className={`chart-tab${activeChart === metric ? " active" : ""}`}
                  onClick={() => setActiveChart(metric)}
                >
                  {metric === "CO2" ? "CO₂" : metric}
                </button>
              ))}
            </div>

            {/* Chart area */}
            <div className="chart-area">
              {chartLoading ? (
                <div style={{ textAlign: "center", padding: 40 }}>
                  <div className="spinner" style={{ margin: "0 auto 12px" }} />
                  <p style={{ color: "var(--ash)" }}>Loading sensor history…</p>
                </div>
              ) : chartData.length < 2 ? (
                <div style={{ textAlign: "center", padding: 40, color: "var(--ash)" }}>
                  Not enough historical data to display a chart.
                </div>
              ) : (
                <MiniChart data={chartData} metric={activeChart} />
              )}
            </div>

            {/* Data count */}
            <p style={{ fontSize: 12, color: "var(--ash)", textAlign: "center", marginTop: 12 }}>
              Showing {chartData.length} readings from this sensor location
            </p>
          </div>
        </div>
      )}

      {/* ───── FOOTER ───── */}
      <footer className="site-footer">
        <div className="footer-inner">
          <span>EmberWatch · Wildfire Detection System · Built with Next.js</span>
          <div className="footer-links">
            <a href="#data-table">Data Table</a>
            <a href="https://www.fire.ca.gov/incidents" target="_blank" rel="noopener noreferrer">
              CAL FIRE
            </a>
          </div>
        </div>
      </footer>
    </>
  );
}

/* ═══════════════════════════════════════════════════════
   MINI CHART — pure canvas line chart (no libraries)
   ═══════════════════════════════════════════════════════ */
function MiniChart({ data, metric }) {
  const canvasRef = useCallback(
    (canvas) => {
      if (!canvas || !data || data.length < 2) return;
      const ctx = canvas.getContext("2d");
      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      ctx.scale(dpr, dpr);
      const W = rect.width;
      const H = rect.height;

      // Extract values
      const values = data.map((d) => Number(d[metric]) || 0);
      const times = data.map((d) => new Date(d.created_at));
      const firePoints = data.map((d) => Number(d.Fire) === 1);

      const minVal = Math.min(...values);
      const maxVal = Math.max(...values);
      const range = maxVal - minVal || 1;
      const pad = { top: 30, right: 20, bottom: 50, left: 60 };
      const chartW = W - pad.left - pad.right;
      const chartH = H - pad.top - pad.bottom;

      const x = (i) => pad.left + (i / (values.length - 1)) * chartW;
      const y = (v) => pad.top + chartH - ((v - minVal) / range) * chartH;

      // Clear
      ctx.clearRect(0, 0, W, H);

      // Background grid
      ctx.strokeStyle = "#e2e8f0";
      ctx.lineWidth = 0.5;
      const gridLines = 5;
      for (let i = 0; i <= gridLines; i++) {
        const gy = pad.top + (chartH / gridLines) * i;
        ctx.beginPath();
        ctx.moveTo(pad.left, gy);
        ctx.lineTo(W - pad.right, gy);
        ctx.stroke();

        // Y-axis labels
        const label = (maxVal - (range / gridLines) * i).toFixed(1);
        ctx.fillStyle = "#94a3b8";
        ctx.font = "11px JetBrains Mono, monospace";
        ctx.textAlign = "right";
        ctx.fillText(label, pad.left - 8, gy + 4);
      }

      // X-axis labels (show ~5 timestamps)
      ctx.fillStyle = "#94a3b8";
      ctx.font = "10px DM Sans, sans-serif";
      ctx.textAlign = "center";
      const step = Math.max(1, Math.floor(values.length / 5));
      for (let i = 0; i < values.length; i += step) {
        const t = times[i];
        const label = t.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
        ctx.fillText(label, x(i), H - pad.bottom + 20);
      }

      // Area fill
      ctx.beginPath();
      ctx.moveTo(x(0), y(values[0]));
      for (let i = 1; i < values.length; i++) {
        ctx.lineTo(x(i), y(values[i]));
      }
      ctx.lineTo(x(values.length - 1), pad.top + chartH);
      ctx.lineTo(x(0), pad.top + chartH);
      ctx.closePath();
      const grad = ctx.createLinearGradient(0, pad.top, 0, pad.top + chartH);
      grad.addColorStop(0, "rgba(232, 76, 48, 0.15)");
      grad.addColorStop(1, "rgba(232, 76, 48, 0.01)");
      ctx.fillStyle = grad;
      ctx.fill();

      // Line
      ctx.beginPath();
      ctx.moveTo(x(0), y(values[0]));
      for (let i = 1; i < values.length; i++) {
        ctx.lineTo(x(i), y(values[i]));
      }
      ctx.strokeStyle = "#e84c30";
      ctx.lineWidth = 2;
      ctx.lineJoin = "round";
      ctx.stroke();

      // Fire points — highlight where Fire=1
      for (let i = 0; i < values.length; i++) {
        if (firePoints[i]) {
          ctx.beginPath();
          ctx.arc(x(i), y(values[i]), 5, 0, Math.PI * 2);
          ctx.fillStyle = "#e84c30";
          ctx.fill();
          ctx.strokeStyle = "#fff";
          ctx.lineWidth = 2;
          ctx.stroke();
        }
      }

      // Title
      ctx.fillStyle = "#1a2332";
      ctx.font = "bold 13px DM Sans, sans-serif";
      ctx.textAlign = "left";
      ctx.fillText(
        `${metric === "CO2" ? "CO₂" : metric} Over Time`,
        pad.left,
        18
      );
    },
    [data, metric]
  );

  return (
    <canvas
      ref={canvasRef}
      style={{ width: "100%", height: 280, display: "block" }}
    />
  );
}