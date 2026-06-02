import React, { useState, useEffect, useRef } from 'react';

function App() {
  const [storeId, setStoreId] = useState('ST1008');
  const [serverStatus, setServerStatus] = useState('checking');
  const [metrics, setMetrics] = useState({
    store_id: 'ST1008',
    unique_visitors: 0,
    conversion_rate: 0.0,
    avg_dwell_by_zone: {},
    queue_depth: 0,
    abandonment_rate: 0.0
  });
  const [funnel, setFunnel] = useState({ store_id: 'ST1008', stages: [] });
  const [heatmap, setHeatmap] = useState([]);
  const [anomalies, setAnomalies] = useState([]);
  const [healthData, setHealthData] = useState(null);
  const [mockMode, setMockMode] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [isUpdating, setIsUpdating] = useState(false);

  // Animated number hook
  const useAnimatedNumber = (target, duration = 600) => {
    const [display, setDisplay] = useState(target);
    const ref = useRef(null);
    useEffect(() => {
      const start = display;
      const diff = target - start;
      if (diff === 0) return;
      const startTime = performance.now();
      const animate = (time) => {
        const elapsed = time - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        setDisplay(Math.round(start + diff * eased));
        if (progress < 1) ref.current = requestAnimationFrame(animate);
      };
      ref.current = requestAnimationFrame(animate);
      return () => cancelAnimationFrame(ref.current);
    }, [target]);
    return display;
  };

  const animatedVisitors = useAnimatedNumber(metrics.unique_visitors);
  const animatedQueueDepth = useAnimatedNumber(metrics.queue_depth);

  useEffect(() => {
    const fetchData = async () => {
      if (mockMode) {
        generateMockData();
        setServerStatus('mock');
        setLastUpdated(new Date());
        return;
      }

      try {
        setIsUpdating(true);
        const [healthRes, metricsRes, funnelRes, heatmapRes, anomaliesRes] = await Promise.all([
          fetch('http://localhost:8000/health'),
          fetch(`http://localhost:8000/stores/${storeId}/metrics`),
          fetch(`http://localhost:8000/stores/${storeId}/funnel`),
          fetch(`http://localhost:8000/stores/${storeId}/heatmap`),
          fetch(`http://localhost:8000/stores/${storeId}/anomalies`)
        ]);

        const [hData, mData, fData, hmapData, aData] = await Promise.all([
          healthRes.json(), metricsRes.json(), funnelRes.json(),
          heatmapRes.json(), anomaliesRes.json()
        ]);

        setHealthData(hData);
        setServerStatus(hData.status === 'healthy' ? 'online' : 'offline');
        setMetrics(mData);
        setFunnel(fData);
        setHeatmap(hmapData.heatmap || []);
        setAnomalies(aData.anomalies || []);
        setLastUpdated(new Date());
      } catch (err) {
        console.error("API Fetch Error:", err);
        setServerStatus('offline');
      } finally {
        setIsUpdating(false);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 3000);
    return () => clearInterval(interval);
  }, [storeId, mockMode]);

  const generateMockData = () => {
    setMetrics({
      store_id: storeId,
      unique_visitors: 245 + Math.floor(Math.random() * 10),
      conversion_rate: 0.1245 + (Math.random() * 0.02 - 0.01),
      avg_dwell_by_zone: {
        "FOH": 42500.0, "MAKEUP": 85600.0,
        "SKINCARE": 112000.0, "BILLING": 56000.0
      },
      queue_depth: Math.floor(Math.random() * 6),
      abandonment_rate: 0.0412
    });
    setFunnel({
      store_id: storeId,
      stages: [
        { stage_name: "Entry", count: 245, drop_off_pct: 0.0 },
        { stage_name: "Zone Visit", count: 182, drop_off_pct: 25.71 },
        { stage_name: "Billing Queue", count: 48, drop_off_pct: 73.63 },
        { stage_name: "Purchase", count: 31, drop_off_pct: 35.42 }
      ]
    });
    setHeatmap([
      { zone_id: "SKINCARE", visit_frequency: 182, avg_dwell_ms: 112000, normalized_score: 95.5 },
      { zone_id: "MAKEUP", visit_frequency: 145, avg_dwell_ms: 85600, normalized_score: 82.1 },
      { zone_id: "FOH", visit_frequency: 98, avg_dwell_ms: 42500, normalized_score: 48.0 },
      { zone_id: "BILLING", visit_frequency: 48, avg_dwell_ms: 56000, normalized_score: 35.6 }
    ]);
    setAnomalies([
      {
        type: "QUEUE_SPIKE", severity: "WARN",
        message: "Checkout queue depth exceeded 3 active visitors at Billing Counter.",
        suggested_action: "Open supplementary cash till and deploy additional checkout staff.",
        timestamp: new Date().toISOString()
      },
      {
        type: "CONVERSION_DROP", severity: "CRITICAL",
        message: "Conversion rate dropped below 7-day trailing average by 18%.",
        suggested_action: "Verify if promotional testers are fully stocked at Minimalist & Aqualogica shelves.",
        timestamp: new Date(Date.now() - 600000).toISOString()
      }
    ]);
  };

  const formatDwellTime = (ms) => {
    if (!ms) return "0s";
    const seconds = Math.round(ms / 1000);
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    const remainingSec = seconds % 60;
    return `${minutes}m ${remainingSec}s`;
  };

  const getZoneColor = (zoneId) => {
    const colors = {
      'FOH': { bg: 'rgba(99, 102, 241, 0.12)', border: 'rgba(99, 102, 241, 0.25)', text: '#818cf8' },
      'MAKEUP': { bg: 'rgba(236, 72, 153, 0.12)', border: 'rgba(236, 72, 153, 0.25)', text: '#f472b6' },
      'SKINCARE': { bg: 'rgba(16, 185, 129, 0.12)', border: 'rgba(16, 185, 129, 0.25)', text: '#34d399' },
      'BILLING': { bg: 'rgba(245, 158, 11, 0.12)', border: 'rgba(245, 158, 11, 0.25)', text: '#fbbf24' },
    };
    return colors[zoneId] || { bg: 'rgba(148,163,184,0.1)', border: 'rgba(148,163,184,0.2)', text: '#94a3b8' };
  };

  const getHeatIntensity = (score) => {
    if (score >= 80) return 'linear-gradient(135deg, rgba(239,68,68,0.15), rgba(249,115,22,0.1))';
    if (score >= 50) return 'linear-gradient(135deg, rgba(245,158,11,0.12), rgba(234,179,8,0.08))';
    if (score >= 20) return 'linear-gradient(135deg, rgba(34,197,94,0.1), rgba(16,185,129,0.06))';
    return 'linear-gradient(135deg, rgba(99,102,241,0.08), rgba(148,163,184,0.04))';
  };

  const cameras = [
    { id: 'CAM 1', name: 'Store Entrance', zone: 'ENTRY' },
    { id: 'CAM 2', name: 'Front of House', zone: 'FOH' },
    { id: 'CAM 3', name: 'Makeup Aisle', zone: 'MAKEUP' },
    { id: 'CAM 4', name: 'Skincare Section', zone: 'SKINCARE' },
    { id: 'CAM 5', name: 'Billing Counter', zone: 'BILLING' },
  ];

  const statusColor = serverStatus === 'online' ? '#10b981' : serverStatus === 'mock' ? '#f59e0b' : '#ef4444';

  return (
    <div style={{ minHeight: '100vh', padding: '20px 24px', boxSizing: 'border-box' }}>
      
      {/* ===== HEADER ===== */}
      <header style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: '20px', paddingBottom: '16px',
        borderBottom: '1px solid rgba(255,255,255,0.06)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{
            height: '42px', width: '42px', borderRadius: '12px',
            background: 'linear-gradient(135deg, #4f46e5 0%, #7c3aed 50%, #ec4899 100%)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontWeight: '900', fontSize: '18px', color: 'white',
            boxShadow: '0 4px 16px rgba(124, 58, 237, 0.35)',
            letterSpacing: '-0.02em'
          }}>
            A
          </div>
          <div>
            <h1 className="gradient-text" style={{ fontSize: '20px', margin: 0, letterSpacing: '0.04em' }}>
              APEX RETAIL INTELLIGENCE
            </h1>
            <p style={{ fontSize: '11px', color: '#64748b', margin: 0, letterSpacing: '0.02em' }}>
              Edge AI Video Analytics · Real-Time POS Correlation Platform
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <select 
            value={storeId} 
            onChange={(e) => setStoreId(e.target.value)}
            style={{
              background: '#0f172a', border: '1px solid rgba(255,255,255,0.08)',
              padding: '7px 14px', borderRadius: '10px', color: '#f8fafc',
              fontSize: '12px', fontWeight: 600, cursor: 'pointer',
              outline: 'none'
            }}
          >
            <option value="ST1008">ST1008 — Brigade Road, Bangalore</option>
            <option value="ST1002">ST1002 — Indiranagar, Bangalore</option>
            <option value="ST2005">ST2005 — Brigade Gateway</option>
          </select>

          <div style={{
            display: 'flex', alignItems: 'center', gap: '8px',
            background: 'rgba(15,23,42,0.6)', padding: '6px 14px',
            borderRadius: '20px', border: '1px solid rgba(255,255,255,0.05)'
          }}>
            <span style={{ fontSize: '10px', color: '#94a3b8', fontWeight: 600 }}>API</span>
            <span className="pulse-indicator" style={{
              backgroundColor: statusColor,
              boxShadow: `0 0 10px ${statusColor}`
            }} />
            <span style={{ fontSize: '10px', fontWeight: 800, textTransform: 'uppercase', color: '#f8fafc' }}>
              {serverStatus}
            </span>
          </div>

          <button onClick={() => setMockMode(!mockMode)} className="btn-secondary"
            style={{ fontSize: '11px', padding: '6px 14px', borderRadius: '20px' }}>
            {mockMode ? '◉ Live API' : '◎ Simulate'}
          </button>
        </div>
      </header>

      {/* ===== NORTH STAR KPI ===== */}
      <section style={{ marginBottom: '20px' }}>
        <div className="metric-card north-star" style={{
          padding: '20px 28px', display: 'flex', alignItems: 'center',
          justifyContent: 'space-between', gap: '32px'
        }}>
          <div>
            <div style={{
              fontSize: '10px', fontWeight: 800, color: '#a78bfa',
              textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '4px'
            }}>
              ★ North Star Metric
            </div>
            <div style={{ fontSize: '13px', color: '#94a3b8', lineHeight: 1.4 }}>
              Offline Store Conversion Rate — Visitors who purchased ÷ Total unique visitors
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div className="gradient-text" style={{ fontSize: '42px', fontWeight: 900, lineHeight: 1 }}>
              {metrics.conversion_rate ? `${(metrics.conversion_rate * 100).toFixed(1)}%` : '0.0%'}
            </div>
            <div style={{ fontSize: '10px', color: '#64748b', marginTop: '4px' }}>
              {lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString()}` : 'Waiting...'}
            </div>
          </div>
        </div>
      </section>

      {/* ===== METRIC CARDS ===== */}
      <section className="metrics-grid" style={{ marginBottom: '20px' }}>
        <div className="metric-card">
          <div className="metric-label">Unique Visitors</div>
          <div className="metric-value">{animatedVisitors}</div>
          <div className="metric-sub">Customers tracked (staff excluded)</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Conversion Rate</div>
          <div className="metric-value" style={{ color: '#a78bfa' }}>
            {metrics.conversion_rate ? `${(metrics.conversion_rate * 100).toFixed(2)}%` : '0.00%'}
          </div>
          <div className="metric-sub">POS correlated within 5m window</div>
        </div>

        <div className="metric-card" style={{
          borderColor: metrics.queue_depth > 3 ? 'rgba(239,68,68,0.25)' : undefined
        }}>
          <div className="metric-label">Queue Depth</div>
          <div className="metric-value" style={{
            color: metrics.queue_depth > 5 ? '#fca5a5' : metrics.queue_depth > 3 ? '#fbbf24' : '#ffffff'
          }}>
            {animatedQueueDepth}
          </div>
          <div className="metric-sub">Active shoppers at checkout</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Abandonment Rate</div>
          <div className="metric-value" style={{
            color: metrics.abandonment_rate > 0.1 ? '#f87171' : '#ffffff'
          }}>
            {metrics.abandonment_rate ? `${(metrics.abandonment_rate * 100).toFixed(1)}%` : '0.0%'}
          </div>
          <div className="metric-sub">Left checkout before purchase</div>
        </div>
      </section>

      {/* ===== MAIN GRID ===== */}
      <div className="dashboard-grid">
        
        {/* LEFT COLUMN */}
        <div className="col-7" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          
          {/* Conversion Funnel */}
          <div className="glass-panel" style={{ padding: '20px 24px' }}>
            <div className="section-title" style={{ color: '#818cf8' }}>
              <span className="icon">📊</span> Conversion Funnel
              {funnel.stages && funnel.stages.length > 0 && (
                <span className="live-badge" style={{ marginLeft: 'auto' }}>
                  <span className="dot" /><span>Live</span>
                </span>
              )}
            </div>
            <div className="funnel-chart">
              {funnel.stages && funnel.stages.map((stage, idx) => {
                const maxCount = funnel.stages[0]?.count || 1;
                const barWidth = Math.max(5, (stage.count / maxCount) * 100);
                return (
                  <div className="funnel-row" key={idx}>
                    <div className="funnel-label">{stage.stage_name}</div>
                    <div className="funnel-bar-container">
                      <div className="funnel-bar" style={{
                        width: `${barWidth}%`,
                        background: `linear-gradient(90deg, hsl(${240 - idx * 30}, 70%, 60%) 0%, hsl(${280 - idx * 25}, 60%, 55%) 100%)`
                      }} />
                      <div className="funnel-count">{stage.count} visitors</div>
                    </div>
                    <div className="funnel-pct">
                      {idx === 0 ? '—' : `−${stage.drop_off_pct.toFixed(1)}%`}
                    </div>
                  </div>
                );
              })}
              {(!funnel.stages || funnel.stages.length === 0) && (
                <div style={{ textAlign: 'center', padding: '40px 20px', color: '#475569', fontSize: '13px' }}>
                  <div style={{ fontSize: '28px', marginBottom: '8px', opacity: 0.5 }}>📊</div>
                  No funnel data. Run the pipeline to populate conversion data.
                </div>
              )}
            </div>
          </div>

          {/* Zone Heatmap as Floor Map */}
          <div className="glass-panel" style={{ padding: '20px 24px' }}>
            <div className="section-title" style={{ color: '#f472b6' }}>
              <span className="icon">🗺️</span> Store Zone Heatmap
            </div>
            
            {/* Visual Floor Map */}
            <div className="floor-map">
              {['FOH', 'MAKEUP', 'SKINCARE', 'BILLING'].map(zoneId => {
                const zoneData = heatmap.find(z => z.zone_id === zoneId);
                const colors = getZoneColor(zoneId);
                const score = zoneData?.normalized_score || 0;
                return (
                  <div key={zoneId} className="floor-zone" style={{
                    background: zoneData ? getHeatIntensity(score) : 'rgba(30,41,59,0.3)',
                    borderColor: colors.border,
                  }}>
                    <div className="floor-zone-name" style={{ color: colors.text }}>{zoneId}</div>
                    <div className="floor-zone-visitors" style={{ color: '#f8fafc' }}>
                      {zoneData?.visit_frequency || 0}
                    </div>
                    <div className="floor-zone-dwell">
                      {zoneData ? formatDwellTime(zoneData.avg_dwell_ms) : '—'}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Detailed Table */}
            <table className="heatmap-table" style={{ marginTop: '16px' }}>
              <thead>
                <tr>
                  <th>Zone</th>
                  <th>Visits</th>
                  <th>Avg Dwell</th>
                  <th>Popularity</th>
                </tr>
              </thead>
              <tbody>
                {heatmap.map((row, idx) => (
                  <tr key={idx}>
                    <td style={{ fontWeight: 700, color: getZoneColor(row.zone_id).text }}>
                      {row.zone_id}
                    </td>
                    <td style={{ fontVariantNumeric: 'tabular-nums' }}>{row.visit_frequency}</td>
                    <td>{formatDwellTime(row.avg_dwell_ms)}</td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <div className="heatmap-score-bar">
                          <div className="heatmap-score-fill" style={{
                            width: `${row.normalized_score}%`,
                            background: `linear-gradient(90deg, ${getZoneColor(row.zone_id).text}, #f43f5e)`
                          }} />
                        </div>
                        <span style={{ fontSize: '11px', fontWeight: 700, color: '#f43f5e', fontVariantNumeric: 'tabular-nums' }}>
                          {row.normalized_score.toFixed(0)}
                        </span>
                      </div>
                    </td>
                  </tr>
                ))}
                {heatmap.length === 0 && (
                  <tr>
                    <td colSpan="4" style={{ textAlign: 'center', padding: '30px', color: '#475569' }}>
                      No zone data tracked yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* RIGHT COLUMN */}
        <div className="col-5" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          
          {/* Anomalies */}
          <div className="glass-panel" style={{ padding: '20px 24px' }}>
            <div className="section-title" style={{ color: '#fbbf24' }}>
              <span className="icon">⚡</span> Operational Alerts
              {anomalies.length > 0 && (
                <span style={{
                  marginLeft: 'auto', fontSize: '11px', fontWeight: 700,
                  background: 'rgba(239,68,68,0.12)', color: '#f87171',
                  padding: '2px 8px', borderRadius: '10px'
                }}>
                  {anomalies.length} active
                </span>
              )}
            </div>
            <div className="alerts-list">
              {anomalies.map((a, idx) => (
                <div className={`alert-card ${
                  a.severity === 'CRITICAL' ? 'severity-critical' : 
                  a.severity === 'WARN' ? 'severity-warning' : 'severity-info'
                }`} key={idx}>
                  <div className="alert-header">
                    <span className="alert-title">{a.type.replace(/_/g, ' ')}</span>
                    <span className="alert-severity">{a.severity}</span>
                  </div>
                  <div className="alert-message">{a.message}</div>
                  {a.suggested_action && (
                    <div className="alert-action">
                      💡 {a.suggested_action}
                    </div>
                  )}
                </div>
              ))}
              {anomalies.length === 0 && (
                <div style={{
                  textAlign: 'center', padding: '32px 20px', color: '#475569', fontSize: '12px',
                  background: 'rgba(16,185,129,0.04)', borderRadius: '10px',
                  border: '1px solid rgba(16,185,129,0.1)'
                }}>
                  <div style={{ fontSize: '24px', marginBottom: '8px' }}>✅</div>
                  All systems nominal. No anomalies detected.
                </div>
              )}
            </div>
          </div>

          {/* Camera Feed Status */}
          <div className="glass-panel" style={{ padding: '20px 24px' }}>
            <div className="section-title" style={{ color: '#94a3b8' }}>
              <span className="icon">📹</span> CCTV Feed Status
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {cameras.map((cam) => {
                const isOnline = serverStatus !== 'offline';
                const color = isOnline ? '#10b981' : '#ef4444';
                return (
                  <div className="camera-row" key={cam.id}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <span className="pulse-indicator" style={{
                        backgroundColor: color,
                        boxShadow: `0 0 8px ${color}`
                      }} />
                      <div>
                        <span style={{ fontSize: '12px', fontWeight: 600 }}>{cam.id}</span>
                        <span style={{ fontSize: '11px', color: '#64748b', marginLeft: '8px' }}>
                          {cam.name}
                        </span>
                      </div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span style={{
                        fontSize: '9px', fontWeight: 700, color: getZoneColor(cam.zone).text,
                        background: getZoneColor(cam.zone).bg,
                        padding: '2px 6px', borderRadius: '4px',
                        border: `1px solid ${getZoneColor(cam.zone).border}`
                      }}>
                        {cam.zone}
                      </span>
                      <span style={{ fontSize: '10px', color: '#475569' }}>15fps</span>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Health Warning */}
            {healthData?.warning === 'STALE_FEED' && (
              <div style={{
                marginTop: '12px', padding: '10px 14px', borderRadius: '8px',
                background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.15)',
                fontSize: '11px', color: '#fbbf24', fontWeight: 600
              }}>
                ⚠️ STALE_FEED — Last event received &gt;10 minutes ago
              </div>
            )}
          </div>

          {/* Dwell Time by Zone */}
          <div className="glass-panel" style={{ padding: '20px 24px' }}>
            <div className="section-title" style={{ color: '#34d399' }}>
              <span className="icon">⏱️</span> Avg Dwell by Zone
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {Object.entries(metrics.avg_dwell_by_zone || {}).sort((a, b) => b[1] - a[1]).map(([zone, ms]) => {
                const maxDwell = Math.max(...Object.values(metrics.avg_dwell_by_zone || {}), 1);
                const pct = (ms / maxDwell) * 100;
                const colors = getZoneColor(zone);
                return (
                  <div key={zone}>
                    <div style={{
                      display: 'flex', justifyContent: 'space-between', marginBottom: '4px'
                    }}>
                      <span style={{ fontSize: '11px', fontWeight: 700, color: colors.text }}>{zone}</span>
                      <span style={{ fontSize: '11px', fontWeight: 600, color: '#cbd5e1', fontVariantNumeric: 'tabular-nums' }}>
                        {formatDwellTime(ms)}
                      </span>
                    </div>
                    <div style={{
                      height: '5px', background: 'rgba(255,255,255,0.04)',
                      borderRadius: '3px', overflow: 'hidden'
                    }}>
                      <div style={{
                        height: '100%', width: `${pct}%`,
                        background: `linear-gradient(90deg, ${colors.text}, ${colors.text}88)`,
                        borderRadius: '3px',
                        transition: 'width 1s cubic-bezier(0.4, 0, 0.2, 1)'
                      }} />
                    </div>
                  </div>
                );
              })}
              {Object.keys(metrics.avg_dwell_by_zone || {}).length === 0 && (
                <div style={{ textAlign: 'center', padding: '20px', color: '#475569', fontSize: '12px' }}>
                  No dwell data available.
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
