import React, { useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import tienda from '../assets/images/tienda-3b.png';

// Listado de tiendas 3B (public/data/tiendas-3b.json). Cuando exista backend, reemplazar por la consulta a la BD.
let cache;
const loadStores = () => cache || (cache = fetch('/data/tiendas-3b.json').then((r) => r.json()).catch(() => []));

const rad = (x) => (x * Math.PI) / 180;
export function distKm(a, b) {
  const dLat = rad(b.lat - a.lat);
  const dLng = rad(b.lng - a.lng);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 6371 * 2 * Math.asin(Math.sqrt(h));
}

const pinIcon = (cls, text, size) =>
  L.divIcon({ className: `pin ${cls}`, html: `<span>${text}</span>`, iconSize: [size, size], iconAnchor: [size / 2, size / 2] });

// Tienda 3B: la imagen de la tienda como marcador, con el número de cercanía
const storeIcon = (n) =>
  L.divIcon({ className: 'pin pin-logo', html: `<img src="${tienda}" alt="" /><b>${n}</b>`, iconSize: [60, 38], iconAnchor: [30, 19] });

// Tooltip construido con textContent (los datos externos nunca se insertan como HTML)
const tip = (title, sub) => {
  const el = document.createElement('div');
  const b = document.createElement('strong');
  b.textContent = title;
  el.appendChild(b);
  if (sub) {
    el.appendChild(document.createElement('br'));
    el.appendChild(document.createTextNode(sub));
  }
  return el;
};

export default function StoresMap({ item, count = 5 }) {
  const box = useRef(null);
  const map = useRef(null);
  const layer = useRef(null);
  const [stores, setStores] = useState([]);

  useEffect(() => { loadStores().then(setStores); }, []);

  const near = useMemo(
    () => stores.map((s) => ({ ...s, d: distKm(item, s) })).sort((a, b) => a.d - b.d).slice(0, count),
    [stores, item.lat, item.lng, count]
  );

  // Crear / destruir el mapa
  useEffect(() => {
    map.current = L.map(box.current, { scrollWheelZoom: false, attributionControl: true });
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap',
    }).addTo(map.current);
    layer.current = L.layerGroup().addTo(map.current);
    map.current.setView([item.lat, item.lng], 13);
    return () => { map.current.remove(); map.current = null; };
  }, []);

  // Dibujar el caso y las tiendas más cercanas
  useEffect(() => {
    if (!map.current) return;
    layer.current.clearLayers();
    const here = [item.lat, item.lng];
    const pts = [here];
    near.forEach((s, i) => {
      const p = [s.lat, s.lng];
      pts.push(p);
      L.polyline([here, p], { color: '#1c244b', weight: 1.5, opacity: 0.45, dashArray: '4 6' }).addTo(layer.current);
      L.marker(p, { icon: storeIcon(i + 1) })
        .bindTooltip(tip(s.nombre, `${s.d.toFixed(1)} km`))
        .addTo(layer.current);
    });
    L.marker(here, { icon: pinIcon('pin-case', '★', 36), zIndexOffset: 1000 })
      .bindTooltip(tip(item.name, 'Caso de prefactibilidad'))
      .addTo(layer.current);
    map.current.invalidateSize();
    map.current.fitBounds(L.latLngBounds(pts), { padding: [34, 34], maxZoom: 15 });
  }, [item.lat, item.lng, item.name, near]);

  return (
    <>
      <div ref={box} className="stores-map" />
      <div className="map-legend">
        <span><i className="pin-key pin-case" /> Caso en evaluación</span>
        <span><img className="key-logo" src={tienda} alt="" /> Tienda 3B</span>
      </div>
      <ol className="store-list">
        {near.map((s) => (
          <li key={s.id}>
            <img className="li-logo" src={tienda} alt="" />
            <b>{s.nombre}</b>
            <span>{s.calle || s.ciudad}</span>
            <em>{s.d.toFixed(1)} km</em>
          </li>
        ))}
        {stores.length === 0 && <li className="muted small">Cargando tiendas…</li>}
      </ol>
    </>
  );
}
