import React, { useEffect, useRef, useState } from 'react';
import g0 from '../assets/images/gallo/gallo-0.png';
import g1 from '../assets/images/gallo/gallo-1.png';
import g2 from '../assets/images/gallo/gallo-2.png';
import g3 from '../assets/images/gallo/gallo-3.png';
import g4 from '../assets/images/gallo/gallo-4.png';
import g5 from '../assets/images/gallo/gallo-5.png';
import g6 from '../assets/images/gallo/gallo-6.png';
import g7 from '../assets/images/gallo/gallo-7.png';

// Gallo BBB: 8 poses que rotan solas, con un globo corto. Solo el gallo (sin escenario) para no saturar el login.
const POSES = [
  { img: g0, say: '¡Hola!', alt: 'saludando', fx: 'wave' },
  { img: g1, say: '¡Todo bien!', alt: 'con el pulgar arriba', fx: 'nod' },
  { img: g2, say: '¡Al rescate!', alt: 'corriendo', fx: 'run' },
  { img: g3, say: '¡Siii!', alt: 'festejando', fx: 'jump' },
  { img: g4, say: '¿Mmm…?', alt: 'pensando', fx: 'tilt' },
  { img: g5, say: '¡Ta-dá!', alt: 'con las alas abiertas', fx: 'flap' },
  { img: g6, say: 'Aquí mando yo', alt: 'de brazos cruzados', fx: 'proud' },
  { img: g7, say: '¡Por allá!', alt: 'señalando', fx: 'point' },
];

const FX = {
  wave: [{ transform: 'rotate(0)' }, { transform: 'rotate(-5deg)' }, { transform: 'rotate(5deg)' }, { transform: 'rotate(-4deg)' }, { transform: 'rotate(0)' }],
  nod: [{ transform: 'scale(1)' }, { transform: 'scale(1.1)' }, { transform: 'scale(1)' }],
  run: [{ transform: 'translateY(0) rotate(-3deg)' }, { transform: 'translateY(-10px) rotate(3deg)' }, { transform: 'translateY(0) rotate(-3deg)' }],
  jump: [{ transform: 'translateY(0) scale(1.1,.9)' }, { transform: 'translateY(-50px) scale(.92,1.1)' }, { transform: 'translateY(0) scale(1.1,.9)' }, { transform: 'translateY(0) scale(1)' }],
  tilt: [{ transform: 'rotate(0)' }, { transform: 'rotate(-8deg)' }, { transform: 'rotate(-8deg)' }, { transform: 'rotate(4deg)' }, { transform: 'rotate(0)' }],
  flap: [{ transform: 'translateY(0)' }, { transform: 'translateY(-20px) scale(1.06)' }, { transform: 'translateY(0)' }, { transform: 'translateY(-12px) scale(1.03)' }, { transform: 'translateY(0)' }],
  proud: [{ transform: 'scale(1)' }, { transform: 'scale(1.08,1.1)' }, { transform: 'scale(1.08,1.1)' }, { transform: 'scale(1)' }],
  point: [{ transform: 'translateX(0)' }, { transform: 'translateX(14px) rotate(4deg)' }, { transform: 'translateX(0)' }, { transform: 'translateX(9px) rotate(2deg)' }, { transform: 'translateX(0)' }],
};
const FX_MS = { run: 1200, jump: 1200, tilt: 1400, flap: 1000, proud: 1100, wave: 900, nod: 500, point: 900 };

export default function Rooster() {
  const [i, setI] = useState(0);
  const body = useRef(null);
  const bubble = useRef(null);
  const timer = useRef(null);
  const reduce = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Cada pose: entrada con "squash & stretch", animación propia y globo; luego pasa a la siguiente sola
  useEffect(() => {
    const p = POSES[i];
    if (!reduce && body.current && body.current.animate) {
      body.current.animate(
        [{ transform: 'scale(.85,1.2) translateY(-16px)' }, { transform: 'scale(1.06,.95)' }, { transform: 'scale(1,1)' }],
        { duration: 360, easing: 'cubic-bezier(.3,1.6,.5,1)' }
      ).onfinish = () => body.current && body.current.animate(FX[p.fx], { duration: FX_MS[p.fx], easing: 'ease-in-out' });
      bubble.current.animate(
        [{ transform: 'scale(0) rotate(-12deg)', opacity: 0 }, { transform: 'scale(1.15) rotate(3deg)', opacity: 1, offset: 0.7 }, { transform: 'scale(1) rotate(0)', opacity: 1 }],
        { duration: 380, easing: 'ease-out' }
      );
    }
    timer.current = setTimeout(() => setI((n) => (n + 1) % POSES.length), 2600);
    return () => clearTimeout(timer.current);
  }, [i, reduce]);

  const p = POSES[i];
  return (
    <div className="rooster" role="button" tabIndex={0} aria-label="Gallo 3B, cambiar de pose"
      onClick={() => setI((n) => (n + 1) % POSES.length)}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setI((n) => (n + 1) % POSES.length); } }}>
      <span className="rooster-bubble" ref={bubble} aria-live="polite">{p.say}</span>
      <div className="rooster-body" ref={body}>
        <img src={p.img} alt={`Gallo 3B ${p.alt}`} draggable="false" />
      </div>
      <i className="rooster-shadow" />
    </div>
  );
}
