import React, { useState } from 'react';
import doorClosedImg from '@/assets/icons1_door_256.png';
import doorOpenImg from '@/assets/icons3_door_256.png';
import agentGifs from '@/assets/gifs';
import './Door.css';

interface DoorProps {
  name: string;
}

const primary = 'var(--ant-primary-color, #1677ff)';
const primaryDark = 'var(--ant-primary-6, #0958d9)';
const gold = '#E2B13C';
const goldDark = '#B07B3B';
const textColor = 'var(--ant-text-color, #222)';
const borderRadius = 24;

function getRandomGif() {
  const idx = Math.floor(Math.random() * agentGifs.length);
  return agentGifs[idx];
}

const Door: React.FC<DoorProps> = ({ name }) => {
  const [hovered, setHovered] = useState(false);
  const [gifUrl] = useState(getRandomGif());

  return (
    <div
      className={`door custom-door${hovered ? ' opening' : ''}`}
      style={{ position: 'static', zIndex: 2 }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div className="door-img-container">
        {/* 门内内容 */}
        <video
          src={gifUrl}
          className="door-inside-gif"
          autoPlay
          loop
          muted
          playsInline
          style={{ opacity: hovered ? 0.92 : 0, pointerEvents: 'none' }}
        />
        <img
          src={hovered ? doorOpenImg : doorClosedImg}
          alt="door"
          className="door-img-png"
        />
      </div>
      <div className="door-label-below">{name}</div>
    </div>
  );
};

export default Door; 